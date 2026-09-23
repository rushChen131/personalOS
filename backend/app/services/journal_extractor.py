"""Extract durable, memory-worthy statements from a journal entry.

Journals are free-form prose, so the structured "title" heuristic the old
event pipeline relied on does not apply. Instead we look for **first-person
cognitive statements** — the sentences where a person reveals a fact, a
preference, a habit, or a decision about themselves. Those are the sentences
worth remembering; a sentence about what the weather was like is not.

This module is deliberately rule-based and deterministic: it runs as the
default path with no API key, and its output must be stable across runs so
that accumulated evidence never shifts underneath an existing candidate.
"""

from __future__ import annotations

import re

# --- Statement markers ------------------------------------------------------
# A sentence only counts if it *asserts something about the author*. Both
# languages are handled because the app is bilingual and users mix freely.
_ZH_MARKERS = (
    "我是", "我在", "我的", "我喜欢", "我不喜欢", "我讨厌", "我偏好", "我更喜欢",
    "我习惯", "我通常", "我倾向", "我决定", "我意识到", "我发现", "我擅长",
    "我不擅长", "我想要", "我希望", "我计划", "我认为", "我觉得", "我需要",
    "我正在学", "我一直",
)
_EN_MARKERS = (
    "i am", "i'm", "i like", "i love", "i dislike", "i hate", "i prefer",
    "i usually", "i often", "i tend to", "i decided", "i realized", "i realised",
    "i found", "i'm good at", "i am good at", "i want", "i hope", "i plan",
    "i think", "i believe", "i need", "i have been", "i've been",
)

# Sentences that look like a statement but carry no durable meaning.
_NOISE_PATTERNS = (
    re.compile(r"^\s*(?:今天|昨天|明天|早上|晚上|中午)"),
)

# Chinese sentence terminators plus newlines. Journals are often written as a
# bullet list, so a line break is a legitimate boundary too. A bare "." is
# included for English, but is handled separately below so that decimals
# ("3.5 hours") and common abbreviations don't create false boundaries.
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;\n\u2063])")

# An English full stop only ends a sentence when followed by whitespace then a
# capital letter (or end of text) — this keeps "3.5" and "e.g." intact. The
# preceding character may be a letter, digit or closing quote.
_EN_STOP = re.compile(r"(?<=[A-Za-z0-9)\"'])\.[\s]")

# Private-use sentinel marking a sentence-final *English* period. Using a
# non-linguistic codepoint means genuine CJK terminators are never rewritten.
_EN_STOP_SENTINEL = "\u2063"

# Leading list decoration / time preamble to strip before keeping the sentence.
_LEAD_STRIP = re.compile(r"^\s*(?:[-*•\d]+[.、)]?\s*|#+\s*)")


def _split_sentences(text: str) -> list[str]:
    """Split prose into trimmed sentences, dropping empties.

    Sentence-final English periods are first replaced by a private-use
    sentinel so a single pass over the shared terminator set splits both
    languages correctly; the sentinel is then restored to a real period.
    """
    if not text:
        return []
    marked = _EN_STOP.sub(_EN_STOP_SENTINEL + " ", text)
    parts = _SENTENCE_SPLIT.split(marked)
    cleaned = []
    for part in parts:
        if not part or not part.strip():
            continue
        sentence = part.replace(_EN_STOP_SENTINEL, ".").strip()
        if sentence:
            cleaned.append(sentence)
    return cleaned


def _matches_marker(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(marker in sentence for marker in _ZH_MARKERS) or any(
        marker in lowered for marker in _EN_MARKERS
    )


def extract_statements(content: str, *, max_statements: int = 10) -> list[str]:
    """Return the memory-worthy sentences of a journal entry.

    Preserves author order and de-duplicates, so re-running on the same entry
    is idempotent. ``max_statements`` guards against a single rambling entry
    flooding the candidate table.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in _split_sentences(content):
        sentence = _LEAD_STRIP.sub("", raw).strip()
        if not sentence:
            continue
        if not _matches_marker(sentence):
            continue
        if any(pattern.search(sentence) for pattern in _NOISE_PATTERNS) and len(sentence) < 12:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(sentence)
        if len(out) >= max_statements:
            break
    return out
