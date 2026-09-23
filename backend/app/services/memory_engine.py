from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import CandidateStatus
from app.models.journal import Journal
from app.models.memory import Memory, MemoryCandidate, MemorySource
from app.services.journal_extractor import extract_statements

# --- Promotion policy (技术设计.md §83) -------------------------------------
# A single journal entry must never become a Memory. We require repeated,
# *distinct* evidence before a bucket is promoted, and derive confidence from
# that evidence rather than hard-coding it.
#
# Calibration follows the spec's own example: scattered single mentions stay
# far below the bar, ~3 related entries form a weak signal, and the spec's
# "~5 converging entries" case reaches 0.75 and promotes. Sustained attention
# (10+) saturates at 1.0.
EVIDENCE_WINDOW_DAYS = 90
MIN_EVIDENCE_COUNT = 3
MIN_DISTINCT_TITLES = 3
PROMOTION_THRESHOLD = 0.75
CONFIDENCE_BASE = 0.5

# Topic bucketing: the bucket must be the *entity* the statement is about
# ("rust"), never the sentence opener. Two shapes need handling:
#
#   "我喜欢用 Rust 写后端"  -> "rust"
#   "I prefer Rust"          -> "rust"
#
# Trailing qualifier words must never enter the key, otherwise every statement
# becomes its own bucket and nothing ever accumulates the evidence needed to
# promote (§83).
_TOPIC_MAX_CHARS = 12

# Sentence openers: cognitive markers about the *speaker* plus the particles
# that glue them onto the real subject. Longest-first so "我不喜欢" wins over
# "我". Applied repeatedly (see `_strip_lead`) to peel stacked markers.
_CJK_OPENERS = (
    "我不喜欢", "我不擅长", "我更喜欢", "我意识到", "我正在学",
    "我喜欢", "我讨厌", "我偏好", "我习惯", "我通常", "我倾向", "我决定",
    "我发现", "我擅长", "我想要", "我希望", "我计划", "我认为", "我觉得",
    "我需要", "我一直", "我是", "我在", "我的", "我",
    "不喜欢", "不擅长", "讨厌", "偏好", "习惯", "通常", "倾向", "决定",
    "意识到", "发现", "擅长", "想要", "希望", "计划", "认为", "觉得",
    "需要", "一直", "正在",
)
# Particles that may separate an opener from the real subject ("我喜欢**用**rust").
_CJK_PARTICLES = "用在从对给和跟把"
# Time-of-day / calendar qualifiers: "我通常在**周末**读书" should bucket on
# what the statement is about, not on when it happens.
_CJK_TIME_QUALIFIERS = (
    "周末", "工作日", "早上", "上午", "中午", "下午", "晚上", "夜里", "深夜",
    "每天", "每周", "每月", "每年", "平时", "空闲时", "有空时",
)

_EN_STOPWORDS = {
    "i", "am", "im", "a", "an", "and", "or", "of", "for", "to", "in", "on",
    "with", "the", "my", "me", "is", "are", "was", "were", "be", "been",
    "like", "love", "prefer", "usually", "often", "tend", "tends", "decided",
    "realized", "realised", "found", "want", "hope", "plan", "think",
    "believe", "need", "have", "has", "had", "good", "at", "using", "use",
}
# CJK stopwords are handled as prefixes by `_strip_lead`, but a handful also
# arrive as whole tokens and must not become the topic on their own.
_CJK_STOPWORDS = {
    "我", "我的", "是", "在", "了", "的", "和", "与", "用", "喜欢", "讨厌",
    "习惯", "通常", "倾向", "决定", "意识到", "发现", "擅长", "想要", "希望",
    "计划", "认为", "觉得", "需要", "一直", "正在", "学",
}

_LEAD_STOP_PATTERN = re.compile(
    r"^(?:" + "|".join(re.escape(m) for m in _CJK_OPENERS) + r")+"
)
_LEAD_PARTICLE_PATTERN = re.compile(r"^[" + _CJK_PARTICLES + r"]+")
_LEAD_TIME_PATTERN = re.compile(
    r"^(?:" + "|".join(re.escape(q) for q in _CJK_TIME_QUALIFIERS) + r")+"
)


def _normalize(text: str | None) -> str:
    """Lowercase, strip punctuation, and collapse whitespace.

    English contractions are folded so "I'm good at X" normalises to
    "i am good at x" — otherwise the apostrophe split leaves a stray "m"
    token that becomes a bogus topic key.
    """
    if not text:
        return ""
    folded = re.sub(r"\b(i|you|we|they|he|she|it)'([a-z]+)\b", r"\1 \2", text.lower())
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", folded)
    return " ".join(cleaned.split())


def _strip_lead(fragment: str) -> str:
    """Peel sentence openers, particles and time qualifiers off a fragment.

    Order matters: openers -> particles -> time qualifiers -> particles again.
    "我通常在周末读书" therefore resolves to "读书" rather than "周末读书".
    Latin characters are never touched, so "rust写后端" survives intact.
    """
    previous = None
    while fragment and fragment != previous:
        previous = fragment
        fragment = _LEAD_STOP_PATTERN.sub("", fragment)
        fragment = _LEAD_PARTICLE_PATTERN.sub("", fragment)
        fragment = _LEAD_TIME_PATTERN.sub("", fragment)
        fragment = _LEAD_PARTICLE_PATTERN.sub("", fragment)
    return fragment


# An embedded Latin word ("rust写后端") marks the statement's real subject.
_LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9_+#.-]*")
# Nothing but Latin letters — used to tell a real entity from a file suffix
# accidentally captured by the run pattern ("app.py" -> "py").
_LATIN_ONLY = re.compile(r"^[A-Za-z]+$")


def _latin_entity(fragment: str) -> Optional[str]:
    """Return the Latin word embedded in a mostly-CJK fragment, if any.

    On the space-separated path the whitespace tokeniser already hands us the
    entity. When a journal sentence has no space at all ("我喜欢用rust写后端")
    the whole clause is one token, so the entity has to be dug out — otherwise
    that statement lands in its own bucket and can never cluster with the
    spaced variants of the same topic.
    """
    match = _LATIN_RUN.search(fragment)
    if not match:
        return None
    word = match.group(0).rstrip(".")
    if not word or len(word) < 2:
        return None
    if "." in word:
        # Only accept a suffix when the word is all letters ("app.py" loses
        # "py"; "node.js" keeps "node").
        if not _LATIN_ONLY.match(word):
            return None
        return word
    return word


def _topic_key(normalized: str) -> str:
    """Reduce a normalised statement to a stable topic bucket.

    Prefers the Latin entity — the subject in mixed CJK+Latin statements such
    as "我喜欢用 Rust 写后端" — then falls back to the leading entity run of the
    CJK text after openers, particles and time qualifiers are peeled.
    """
    tokens = [t for t in normalized.split() if t and t not in _EN_STOPWORDS]

    # Latin entity wins: "我喜欢用 Rust 写后端" -> "rust".
    for token in tokens:
        if token.isascii() and token.isalpha() and len(token) > 1:
            return token

    # The first CJK-bearing token (or the whole string when unsegmented).
    candidate = ""
    for token in tokens:
        if token not in _CJK_STOPWORDS:
            candidate = token
            break
    if not candidate:
        candidate = normalized

    stripped = _strip_lead(candidate)
    if not stripped:
        # Everything was an opener ("我喜欢"): fall back to the raw token so we
        # still get a stable bucket rather than dropping the statement.
        stripped = candidate

    embedded = _latin_entity(stripped)
    if embedded:
        return embedded
    return stripped[:_TOPIC_MAX_CHARS]


class MemoryEngine:
    """Implements the Journal -> Candidate -> Memory pipeline of §83.

    Called from ``MemoryAnalysisJob`` on every ``JournalCreated``. Instead of
    writing a Memory per journal entry, it splits the entry into cognitive
    statements, folds each into a candidate bucket, recomputes confidence from
    accumulated evidence, and promotes a bucket only once thresholds are met.
    """

    async def ingest_journal(
        self, session: AsyncSession, user_id: str, journal: Journal
    ) -> dict[str, Any]:
        statements = extract_statements(journal.content or "")
        if not statements:
            return {"skipped": "no memory-worthy statements", "journal_id": journal.id}

        promoted: list[str] = []
        updated = 0
        for statement in statements:
            result = await self._ingest_statement(session, user_id, journal, statement)
            if result.get("promoted_memory_id"):
                promoted.append(result["promoted_memory_id"])
            if result.get("candidate_id"):
                updated += 1

        await session.flush()
        return {
            "journal_id": journal.id,
            "statements": len(statements),
            "candidates_touched": updated,
            "promoted_memory_ids": promoted,
        }

    async def _ingest_statement(
        self,
        session: AsyncSession,
        user_id: str,
        journal: Journal,
        statement: str,
    ) -> dict[str, Any]:
        normalized = _normalize(statement)
        if not normalized:
            return {"skipped": "empty statement"}

        topic = _topic_key(normalized)
        if not topic:
            return {"skipped": "no topic"}

        # The bucket type is a PATTERN: "the user repeatedly says this about
        # themselves". Type refinement can happen at promotion time later.
        signature = f"{topic}|PATTERN"
        candidate = await session.scalar(
            select(MemoryCandidate).where(
                MemoryCandidate.user_id == user_id,
                MemoryCandidate.signature == signature,
            )
        )
        if candidate is None:
            candidate = MemoryCandidate(
                user_id=user_id,
                signature=signature,
                type="PATTERN",
                topic=topic,
                content=statement,
                evidence={},
                evidence_count=0,
                confidence=0.0,
                status=CandidateStatus.PENDING.value,
            )
            session.add(candidate)
            await session.flush()
        elif candidate.status == CandidateStatus.PROMOTED.value:
            # Already a memory; keep refreshing recency/evidence silently.
            candidate.last_seen_at = datetime.now(timezone.utc)
            candidate.content = statement

        since = datetime.now(timezone.utc) - timedelta(days=EVIDENCE_WINDOW_DAYS)
        window_journals = (
            await session.scalars(
                select(Journal).where(
                    Journal.user_id == user_id,
                    Journal.created_at >= since,
                )
            )
        ).all()

        distinct_statements: set[str] = set()
        source_ids: list[str] = []
        matched = 0
        for other in window_journals:
            for other_statement in extract_statements(other.content or ""):
                other_normalized = _normalize(other_statement)
                if not other_normalized:
                    continue
                if _topic_key(other_normalized) != topic:
                    continue
                matched += 1
                distinct_statements.add(other_normalized)
                if other.id not in source_ids:
                    source_ids.append(other.id)

        candidate.evidence_count = matched
        candidate.evidence = {
            "statements": sorted(distinct_statements),
            "source_journal_ids": source_ids,
        }
        candidate.confidence = self._confidence(matched, len(distinct_statements))
        candidate.last_seen_at = datetime.now(timezone.utc)

        if (
            candidate.status == CandidateStatus.PENDING.value
            and matched >= MIN_EVIDENCE_COUNT
            and len(distinct_statements) >= MIN_DISTINCT_TITLES
            and float(candidate.confidence) >= PROMOTION_THRESHOLD
        ):
            memory = await self._promote(session, candidate)
            return {
                "candidate_id": candidate.id,
                "promoted_memory_id": memory.id,
                "evidence_count": matched,
                "confidence": float(candidate.confidence),
            }

        await session.flush()
        return {
            "candidate_id": candidate.id,
            "status": candidate.status,
            "evidence_count": matched,
            "confidence": float(candidate.confidence),
        }

    @staticmethod
    def _confidence(evidence_count: int, distinct_titles: int) -> float:
        """Confidence gated on both volume and *variety* of evidence.

        Volume saturates at 20 statements (the spec's sustained-attention
        case), variety at 5 distinct statements. A single repeated sentence is
        capped below the promotion threshold no matter how often it recurs, so
        only a genuine recurring pattern with multiple facets can promote."""
        volume = min(1.0, evidence_count / 20)
        variety = min(1.0, distinct_titles / 5)
        base = CONFIDENCE_BASE + (1 - CONFIDENCE_BASE) * (0.5 * volume + 0.5 * variety)
        # Variety gate: a single repeated statement can never promote.
        if distinct_titles < MIN_DISTINCT_TITLES:
            base = min(base, 0.5)
        return round(base, 2)

    async def _promote(self, session: AsyncSession, candidate: MemoryCandidate) -> Memory:
        memory = Memory(
            user_id=candidate.user_id,
            type=candidate.type,
            content=candidate.content,
            summary=candidate.topic,
            confidence=float(candidate.confidence),
            importance=min(1.0, 0.5 + candidate.evidence_count * 0.02),
            source_count=candidate.evidence_count,
            metadata={
                "source": "MEMORY_ENGINE",
                "candidate_id": candidate.id,
                "signature": candidate.signature,
            },
        )
        session.add(memory)
        await session.flush()

        # Traceability (§19): every memory points back at the journals it was
        # distilled from. Falls back to the most recent journals when the
        # candidate predates source tracking.
        source_ids = (candidate.evidence or {}).get("source_journal_ids") or []
        if not source_ids:
            recent_ids = (
                await session.scalars(
                    select(Journal.id)
                    .where(Journal.user_id == candidate.user_id)
                    .order_by(Journal.created_at.desc())
                    .limit(candidate.evidence_count)
                )
            ).all()
            source_ids = list(recent_ids)
        for source_id in source_ids:
            session.add(
                MemorySource(
                    memory_id=memory.id,
                    source_type="JOURNAL",
                    source_id=str(source_id),
                    relevance=1,
                )
            )

        candidate.status = CandidateStatus.PROMOTED.value
        candidate.promoted_memory_id = memory.id
        await session.flush()
        return memory
