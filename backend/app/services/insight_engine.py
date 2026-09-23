from __future__ import annotations

import asyncio
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insight import Insight
from app.models.journal import Journal
from app.models.project import Goal
from app.repositories.insight_report_repository import InsightRepository
from app.services.journal_extractor import extract_statements
from app.services.memory_engine import (
    _CJK_STOPWORDS,
    _EN_STOPWORDS,
    _LATIN_RUN,
    _normalize,
    _topic_key,
)

#: An active goal with no journal mention for this long is flagged as stalled (§12).
STAGNATION_DAYS = 14
MIN_CONFIDENCE = 0.5
#: Moods that read as "under load" — used by the mood-trend rule.
NEGATIVE_MOODS = frozenset(
    {"tired", "exhausted", "stressed", "anxious", "low", "sad", "drained", "overwhelmed", "bad"}
)
POSITIVE_MOODS = frozenset(
    {"good", "happy", "proud", "great", "energised", "energized", "satisfied", "relieved", "calm", "excited"}
)
#: Minimum entries before a topic/mood rule is allowed to make a claim.
MIN_ENTRIES_FOR_TOPIC = 3
MIN_ENTRIES_FOR_MOOD = 4
#: Minimum accomplishment-flavoured entries before reporting the weekly tally.
MIN_ENTRIES_FOR_ACCOMPLISHMENT = 2

#: Per-user serialisation of the insight check-then-insert. Keyed by user so
#: two different users never block each other.
_LOCKS: dict[str, asyncio.Lock] = {}


def _lock_for(user_id: str) -> asyncio.Lock:
    lock = _LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[user_id] = lock
    return lock


def _when(journal: Journal) -> datetime | None:
    """Effective timestamp of an entry: ``occurred_at`` falls back to ``created_at``.

    Both columns are ``TZDateTime`` so they are always aware, but an entry the
    user back-dated is better represented by ``occurred_at``.
    """
    return journal.occurred_at or journal.created_at


class InsightEngine:
    """Rule-based pattern detection over a user's journal history.

    Journals are the only user-authored input, so every rule reads journals.
    Events carried structured ``type`` / ``duration_minutes`` fields that made
    "time accounting" rules (investment shift, heavy-day anomaly) possible;
    journals carry none of that, so those rules are replaced by signals the
    journal *does* hold: free-text topics (via the memory engine's topic key),
    the optional ``mood`` field, goal-title mentions, and entry volume/cadence.

    The rule set is deterministic so local mode needs no model.
    """

    def __init__(self, repository: InsightRepository, bus: Any | None = None) -> None:
        self.repository = repository
        self.bus = bus
        #: Summary of the most recent run: ``{created, refreshed, evaluated}``.
        self.last_run: dict[str, int] = {}

    async def generate(self, session: AsyncSession, user_id: str, period_days: int = 14) -> list[Insight]:
        """Run every rule and persist the results.

        Returns the insights **created by this run** — an insight whose title
        already exists is refreshed in place and is not returned, so callers
        that want the full picture should query the insights endpoint instead.
        ``self.last_run`` breaks the counts down (``created`` / ``refreshed`` /
        ``evaluated``).

        The dispatcher runs one insight pass per journal write, and a burst of
        writes makes those passes overlap. Two passes can both read "no such
        insight" before either commits, which produced duplicate rows with
        byte-identical titles. A module-level per-user lock serialises the
        check-then-insert without needing a schema change — note the engine
        itself is constructed fresh per run, so an instance lock would not help.
        """
        async with _lock_for(user_id):
            return await self._generate_locked(session, user_id, period_days)

    async def _generate_locked(
        self, session: AsyncSession, user_id: str, period_days: int
    ) -> list[Insight]:
        # Journal timestamps are timezone-aware (stored as UTC), so the window
        # boundary must be aware too — comparing naive against aware datetimes
        # raises TypeError.
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=period_days)

        # Journals are queried over 2x the window so the week-over-week rules can
        # compare the recent half against the prior half.
        lookback_start = now - timedelta(days=period_days * 2)
        journals = [
            entry
            for entry in (
                await session.scalars(
                    select(Journal).where(Journal.user_id == user_id, Journal.created_at >= lookback_start)
                )
            ).unique()
            if _when(entry) is not None
        ]
        goals = list(
            (await session.scalars(select(Goal).where(Goal.user_id == user_id, Goal.status == "ACTIVE"))).unique()
        )

        in_window = [entry for entry in journals if _when(entry) >= window_start]

        candidates: list[dict[str, Any]] = []
        candidates.extend(self._detect_stagnant_goals(goals, in_window, now))
        candidates.extend(self._detect_journal_volume_change(journals, now))
        candidates.extend(self._detect_recurring_topics(in_window, now))
        candidates.extend(self._detect_mood_trend(in_window, now))
        candidates.extend(self._detect_goal_momentum(goals, in_window, now))
        candidates.extend(self._detect_achievements(in_window, now))
        candidates.extend(self._detect_suggestions(in_window, goals, now))

        persisted: list[Insight] = []
        created = 0
        refreshed = 0
        for candidate in candidates:
            if candidate["confidence"] < MIN_CONFIDENCE:
                continue
            # Titles are stable per rule so a rule firing repeatedly does not
            # stack near-identical rows. That means an existing row must be
            # *updated* rather than skipped: a stalled-goal insight written when
            # the user had 2 entries would otherwise keep claiming "your last 2
            # journal entries" forever.
            existing = await self._find_existing(session, user_id, candidate["title"])
            if existing is not None:
                if self._refresh(existing, candidate):
                    refreshed += 1
                continue
            insight = await self.repository.create(
                session,
                Insight(
                    user_id=user_id,
                    title=candidate["title"],
                    content=candidate["content"],
                    insight_type=candidate["insight_type"],
                    confidence=candidate["confidence"],
                    importance=candidate.get("importance", 0.5),
                    evidence=candidate.get("evidence", []),
                ),
            )
            persisted.append(insight)
            created += 1
            if self.bus is not None:
                # §80: publish InsightCreated for every persisted insight.
                await self.bus.publish("InsightCreated", {"insight_id": insight.id, "user_id": user_id})
        self.last_run = {"created": created, "refreshed": refreshed, "evaluated": len(candidates)}
        return persisted

    # -- shared helpers --------------------------------------------------

    @staticmethod
    async def _find_existing(session: AsyncSession, user_id: str, title: str) -> Insight | None:
        return await session.scalar(
            select(Insight).where(Insight.user_id == user_id, Insight.title == title).limit(1)
        )

    @staticmethod
    def _refresh(insight: Insight, candidate: dict[str, Any]) -> bool:
        """Bring an existing insight's body up to date. Returns True if changed."""
        changed = False
        for field, value in (
            ("content", candidate["content"]),
            ("insight_type", candidate["insight_type"]),
            ("confidence", candidate["confidence"]),
            ("importance", candidate.get("importance", 0.5)),
            ("evidence", candidate.get("evidence", [])),
        ):
            if getattr(insight, field) != value:
                setattr(insight, field, value)
                changed = True
        return changed

    @staticmethod
    def _mentions_goal(entry: Journal, goal: Goal) -> bool:
        """Whether an entry references a goal, by title or description keyword."""
        haystack = f"{entry.title or ''} {entry.content or ''}".lower()
        for term in (goal.title, goal.description):
            if not term:
                continue
            for token in _significant_terms(term):
                if token in haystack:
                    return True
        return False

    @staticmethod
    def _topics(entry: Journal) -> set[str]:
        """Every notable subject an entry contributes, not just its leading one.

        ``_topic_key`` is built for *bucketing statements into memories*, where
        collapsing a sentence to its single leading entity is exactly right — a
        bucket must be stable so evidence can accumulate. Topic *recurrence* asks
        a different question ("what does this author keep returning to?"), and
        the single-key reduction loses most of the answer: "I am learning Rust
        ownership." keys to ``learning``, so three Rust entries fragment across
        ``rust``/``learning``/``went`` and no topic ever reaches the threshold.

        So this reuses the memory engine's *vocabulary* (the same stopwords and
        the same idea of what counts as an entity) but keeps every candidate
        rather than picking one. Entity extraction is shared with the memory
        layer, which is what keeps the two consistent about what a "subject" is.
        """
        topics: set[str] = set()
        content = entry.content or ""
        statements = extract_statements(content)
        for statement in statements:
            topics.update(_topic_terms(statement))
        # Fall back to the raw text when the entry carries no cognitive
        # statement (e.g. a purely narrative day) so it can still contribute.
        if not topics and content.strip():
            topics.update(_topic_terms(content))
        return topics

    # -- rules -----------------------------------------------------------

    def _detect_stagnant_goals(
        self, goals: list[Goal], journals: list[Journal], now: datetime
    ) -> list[dict[str, Any]]:
        """RISK when an active goal is never mentioned in the window."""
        candidates: list[dict[str, Any]] = []
        for goal in goals:
            if not (goal.title or "").strip():
                continue
            if any(self._mentions_goal(entry, goal) for entry in journals):
                continue
            candidates.append(
                {
                    "title": f"Goal stalled: {goal.title}",
                    "content": (
                        f"'{goal.title}' is ACTIVE at {float(goal.progress or 0):.0f}% progress but none of your "
                        f"last {len(journals)} journal entries mention it in the past {STAGNATION_DAYS} days."
                    ),
                    "insight_type": "RISK",
                    "confidence": 0.8,
                    "importance": 0.8,
                    "evidence": [{"goal_id": goal.id, "window_days": STAGNATION_DAYS, "window_entries": len(journals)}],
                }
            )
        return candidates

    @staticmethod
    def _detect_journal_volume_change(journals: list[Journal], now: datetime) -> list[dict[str, Any]]:
        """BEHAVIOR_CHANGE when writing frequency moves sharply week over week.

        Journal *count* replaces the old event-minute volume: it is the only
        cadence signal a free-text entry reliably provides.
        """
        recent_start = now - timedelta(days=7)
        prior_start = now - timedelta(days=14)
        recent_count = sum(1 for e in journals if _when(e) and _when(e) >= recent_start)
        prior_count = sum(1 for e in journals if _when(e) and prior_start <= _when(e) < recent_start)
        if prior_count < 3:
            return []
        change = (recent_count - prior_count) / prior_count
        if abs(change) < 0.4:
            return []
        direction = "increased" if change > 0 else "decreased"
        return [
            {
                "title": f"Writing frequency {direction}",
                "content": (
                    f"You wrote {recent_count} journal entries this week versus {prior_count} last week "
                    f"({change:+.0%})."
                ),
                "insight_type": "BEHAVIOR_CHANGE",
                "confidence": 0.6,
                "importance": 0.55,
                "evidence": [{"recent": recent_count, "prior": prior_count}],
            }
        ]

    @staticmethod
    def _detect_recurring_topics(journals: list[Journal], now: datetime) -> list[dict[str, Any]]:
        """TREND when one subject keeps resurfacing across entries.

        This is the journal analogue of the old "investment shift": instead of
        measuring which *activity type* took more time, it measures which
        *subject* keeps occupying the author's attention.

        Note the day requirement is deliberately loose. A journal is written in
        sittings, so a genuine recurring focus ("Rust" three entries in one
        evening) legitimately lands on a single calendar day — requiring entries
        to span 2+ days silently dropped exactly the signal this rule exists to
        find. Breadth is instead enforced by ``MIN_ENTRIES_FOR_TOPIC`` plus the
        share gate below, which are the conditions that actually separate a
        recurring subject from incidental vocabulary.
        """
        if len(journals) < MIN_ENTRIES_FOR_TOPIC:
            return []
        by_topic: dict[str, list[Journal]] = {}
        for entry in journals:
            for topic in InsightEngine._topics(entry):
                by_topic.setdefault(topic, []).append(entry)

        candidates: list[dict[str, Any]] = []
        for topic, entries in by_topic.items():
            distinct_days = {_when(e).date() for e in entries if _when(e)}
            if len(entries) < MIN_ENTRIES_FOR_TOPIC:
                continue
            share = len(entries) / len(journals)
            # Only a topic that genuinely dominates the period is worth surfacing.
            # A single-day burst must clear a higher bar than a sustained one.
            if share < 0.25:
                continue
            if len(distinct_days) < 2 and share < 0.5:
                continue
            examples = ", ".join(sorted({(e.title or "").strip() for e in entries if (e.title or "").strip()})[:3])
            day_phrase = f"across {len(distinct_days)} days" if len(distinct_days) > 1 else "in one sitting"
            candidates.append(
                {
                    "title": f"Recurring focus: {topic}",
                    "content": (
                        f"'{topic}' comes up in {len(entries)} of your last {len(journals)} entries "
                        f"({share:.0%}) {day_phrase}"
                        + (f", including: {examples}." if examples else ".")
                    ),
                    "insight_type": "TREND",
                    "confidence": round(min(0.85, 0.6 + share * 0.3), 2),
                    "importance": 0.6,
                    "evidence": [
                        {
                            "topic": topic,
                            "entries": len(entries),
                            "distinct_days": len(distinct_days),
                            "share": round(share, 2),
                            "journal_ids": [e.id for e in entries],
                        }
                    ],
                }
            )
        # Keep only the strongest topic per run to avoid flooding the feed.
        candidates.sort(key=lambda c: c["confidence"], reverse=True)
        return candidates[:2]

    @staticmethod
    def _detect_mood_trend(journals: list[Journal], now: datetime) -> list[dict[str, Any]]:
        """RISK / ACHIEVEMENT when the optional ``mood`` field trends one way.

        Mood is the one structured field a journal carries, so it is the closest
        available substitute for the old numeric intensity signals.
        """
        tagged = [e for e in journals if (e.mood or "").strip()]
        if len(tagged) < MIN_ENTRIES_FOR_MOOD:
            return []
        negative = [e for e in tagged if (e.mood or "").strip().lower() in NEGATIVE_MOODS]
        mood_counts = Counter((e.mood or "").strip().lower() for e in tagged)
        most_common, most_common_count = mood_counts.most_common(1)[0]

        candidates: list[dict[str, Any]] = []
        share = len(negative) / len(tagged)
        if len(negative) >= 3 and share >= 0.5:
            candidates.append(
                {
                    "title": "Mood trending low",
                    "content": (
                        f"{len(negative)} of your last {len(tagged)} tagged entries read as low or draining "
                        f"({share:.0%}). Worth checking what is pulling your energy down."
                    ),
                    "insight_type": "RISK",
                    "confidence": round(min(0.8, 0.55 + share * 0.25), 2),
                    "importance": 0.75,
                    "evidence": [
                        {
                            "negative_entries": len(negative),
                            "tagged_entries": len(tagged),
                            "share": round(share, 2),
                            "moods": dict(mood_counts),
                        }
                    ],
                }
            )
        if most_common in POSITIVE_MOODS and most_common_count >= 3:
            candidates.append(
                {
                    "title": f"Consistently '{most_common}'",
                    "content": (
                        f"'{most_common}' is the mood you reached for most often — "
                        f"{most_common_count} of {len(tagged)} tagged entries."
                    ),
                    "insight_type": "ACHIEVEMENT",
                    "confidence": 0.65,
                    "importance": 0.6,
                    "evidence": [{"mood": most_common, "count": most_common_count, "tagged_entries": len(tagged)}],
                }
            )
        return candidates

    @staticmethod
    def _detect_goal_momentum(goals: list[Goal], journals: list[Journal], now: datetime) -> list[dict[str, Any]]:
        """GOAL_PROGRESS when a goal is advancing strongly or nearly complete."""
        window_start = now - timedelta(days=STAGNATION_DAYS)
        recent_entries = [e for e in journals if _when(e) and _when(e) >= window_start]
        candidates: list[dict[str, Any]] = []
        for goal in goals:
            progress = float(goal.progress or 0)
            if progress >= 90:
                candidates.append(
                    {
                        "title": f"Goal nearly complete: {goal.title}",
                        "content": f"'{goal.title}' is at {progress:.0f}% — close to completion.",
                        "insight_type": "GOAL_PROGRESS",
                        "confidence": 0.85,
                        "importance": 0.75,
                        "evidence": [{"goal_id": goal.id, "progress": progress}],
                    }
                )
                continue
            if progress > 20:
                continue
            mentions = sum(1 for entry in recent_entries if InsightEngine._mentions_goal(entry, goal))
            if mentions >= 3:
                candidates.append(
                    {
                        "title": f"Goal picking up: {goal.title}",
                        "content": (
                            f"'{goal.title}' is only at {progress:.0f}% but appeared in {mentions} journal entries "
                            f"in the last {STAGNATION_DAYS} days — momentum is building."
                        ),
                        "insight_type": "GOAL_PROGRESS",
                        "confidence": 0.6,
                        "importance": 0.6,
                        "evidence": [{"goal_id": goal.id, "progress": progress, "recent_entries": mentions}],
                    }
                )
        return candidates

    @staticmethod
    def _detect_achievements(journals: list[Journal], now: datetime) -> list[dict[str, Any]]:
        """ACHIEVEMENT when entries read as notable outcomes.

        There is no ``type`` field any more, so completion is inferred from the
        wording of the entry itself.

        The title is deliberately **constant** across runs. The engine fires on
        every journal write, so a title that embedded the live count ("4 notable
        outcomes", then "5 notable outcomes") would defeat ``_is_duplicate`` and
        stack one near-identical insight per write.
        """
        window_start = now - timedelta(days=7)
        recent = [e for e in journals if _when(e) and _when(e) >= window_start]
        accomplishments = [e for e in recent if _reads_like_accomplishment(f"{e.title or ''} {e.content or ''}")]
        if len(accomplishments) < MIN_ENTRIES_FOR_ACCOMPLISHMENT:
            return []
        labels = ", ".join((e.title or "").strip() for e in accomplishments[:3] if (e.title or "").strip())
        return [
            {
                "title": "Notable outcomes on the record",
                "content": (
                    f"{len(accomplishments)} of your entries this week describe outcomes worth noting"
                    + (f": {labels}." if labels else ".")
                ),
                "insight_type": "ACHIEVEMENT",
                "confidence": 0.7,
                "importance": 0.65,
                "evidence": [{"journal_ids": [e.id for e in accomplishments]}],
            }
        ]

    @staticmethod
    def _detect_suggestions(journals: list[Journal], goals: list[Goal], now: datetime) -> list[dict[str, Any]]:
        """SUGGESTION when the journal record implies a concrete next action."""
        window_start = now - timedelta(days=7)
        recent = [e for e in journals if _when(e) and _when(e) >= window_start]
        active_goals = [goal for goal in goals if goal.status == "ACTIVE"]
        candidates: list[dict[str, Any]] = []
        if active_goals and not recent:
            candidates.append(
                {
                    "title": "No journal entries this week",
                    "content": (
                        f"You have {len(active_goals)} active goals but wrote nothing in the last 7 days. "
                        "Consider reserving a few minutes to write."
                    ),
                    "insight_type": "SUGGESTION",
                    "confidence": 0.7,
                    "importance": 0.7,
                    "evidence": [{"active_goals": len(active_goals)}],
                }
            )
            return candidates

        # Balance check: journals reveal *what you think about*, so flag a week
        # where reflection never leaves execution work.
        topics = {topic for entry in recent for topic in InsightEngine._topics(entry)}
        has_learning = any(t in {"learn", "learning", "study", "studying", "read", "reading"} for t in topics)
        has_health = any(t in {"run", "running", "training", "gym", "sleep", "health", "walk"} for t in topics)
        if recent and not has_learning and not has_health:
            candidates.append(
                {
                    "title": "Broaden beyond execution work",
                    "content": (
                        "Recent entries stay inside execution. Consider adding learning or health "
                        "activities to keep the balance that drives longer-term progress."
                    ),
                    "insight_type": "SUGGESTION",
                    "confidence": 0.55,
                    "importance": 0.5,
                    "evidence": [{"recent_topics": sorted(topics)}],
                }
            )
        return candidates


#: Terms too generic to identify a goal by.
_GOAL_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "my", "this", "that",
        "read", "run", "learn", "ship", "get", "make", "build", "year", "day",
        "目标", "计划", "完成", "今年", "这个", "一个", "我的",
    }
)
#: Wording that marks an entry as describing a completed outcome.
_ACCOMPLISHMENT_MARKERS = (
    "shipped", "finished", "completed", "achieved", "launched", "merged", "published",
    "decided", "made progress", "broke through", "finally",
    "完成", "上线", "发布", "搞定", "搞定", "终于", "决定", "突破", "交付", "合并",
)
#: Common verbs/adverbs that survive the memory engine's stopwords but are not
#: subjects. Topic *recurrence* counts raw mentions, so an unfiltered "spent"
#: or "today" would make ordinary narrative prose look like a recurring focus.
#: Kept deliberately small — a broad list would start eating real entities.
_TOPIC_NOISE = frozenset(
    {
        "spent", "went", "got", "today", "tomorrow", "yesterday", "tonight",
        "clicked", "started", "tried", "kept", "still", "again", "about", "into",
        "over", "after", "before", "when", "then", "than", "them", "they", "there",
        "here", "what", "where", "which", "while", "would", "could", "should",
        "been", "being", "very", "much", "more", "most", "some", "just", "only",
        "also", "even", "well", "back", "down", "through", "first", "next", "last",
    }
)


def _topic_terms(text: str) -> set[str]:
    """All notable subjects mentioned in one statement.

    Two sources, mirroring the memory engine's two paths:

    * **Latin runs** — every ``_LATIN_RUN`` match ("Rust", "AgentScope"), which
      is the entity signal the memory engine trusts most. All of them are kept,
      so "I am learning Rust ownership" contributes ``rust`` *and* ``learning``.
    * **Leading CJK entity** — CJK has no word boundaries, so the memory
      engine's ``_topic_key`` is the only reliable reducer; it is used as an
      additional term rather than the sole one.

    Stopwords come from the memory engine so the two layers agree on which
    words are content-free.
    """
    normalized = _normalize(text)
    if not normalized:
        return set()

    terms: set[str] = set()
    for match in _LATIN_RUN.finditer(normalized):
        word = match.group(0).rstrip(".")
        if len(word) < 3 or word in _EN_STOPWORDS or word in _TOPIC_NOISE:
            continue
        terms.add(word)

    # The CJK path: `_topic_key` yields the leading entity once openers and
    # particles are peeled ("我喜欢用 rust 写后端" -> "rust"). It is added even
    # when Latin terms were found, because for a mostly-CJK sentence it is the
    # subject while the Latin run may only be a tool name.
    leading = _topic_key(normalized)
    if len(leading) >= 2 and leading not in _EN_STOPWORDS and leading not in _CJK_STOPWORDS:
        terms.add(leading)
    return terms


def _significant_terms(text: str) -> list[str]:
    """Extract the distinctive words of a goal title/description.

    A whole goal title rarely appears verbatim in prose, so matching is done on
    its significant tokens instead. Latin tokens are matched lowercase; CJK has
    no word boundaries, so contiguous CJK runs are used as-is.
    """
    tokens: list[str] = []
    for raw in re.split(r"[^\w\u4e00-\u9fff]+", text.lower()):
        token = raw.strip()
        if len(token) < 2 or token in _GOAL_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _reads_like_accomplishment(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _ACCOMPLISHMENT_MARKERS)
