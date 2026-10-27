"""Topic validation and the English-only script heuristic (PRD FR-01, FR-30, §6.7)."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from core.errors import ErrorCode

MAX_TOPIC_CHARS = 500
_SCRIPT_CHECK_MIN_LETTERS = 20
_NON_LATIN_SHARE_LIMIT = 0.70


@dataclass(frozen=True)
class TopicCheck:
    ok: bool
    topic: str
    error: ErrorCode | None = None
    warnings: list[str] = field(default_factory=list)


def _is_latin_letter(ch: str) -> bool:
    return unicodedata.name(ch, "").startswith("LATIN")


WARNING_TEXT = {
    "NON_LATIN_SHORT": "Part of the topic is not in English. Results may be limited.",
    "LATIN_NON_ENGLISH_POSSIBLE": "The topic may not be in English. Results may be limited.",
}


def describe_warnings(codes: list[str]) -> list[str]:
    """Plain sentences for validation warning codes; unknown codes are dropped."""
    return [WARNING_TEXT[c] for c in codes if c in WARNING_TEXT]


def validate_topic(raw: str) -> TopicCheck:
    """Trim and validate a topic. This is a cheap script heuristic, not language detection."""
    topic = raw.strip()
    if not topic:
        return TopicCheck(False, topic, ErrorCode.INPUT_INVALID)
    if len(topic) > MAX_TOPIC_CHARS:
        return TopicCheck(False, topic, ErrorCode.INPUT_INVALID)

    letters = [c for c in topic if c.isalpha()]
    latin = [c for c in letters if _is_latin_letter(c)]
    non_latin = len(letters) - len(latin)

    warnings: list[str] = []
    if (
        len(letters) >= _SCRIPT_CHECK_MIN_LETTERS
        and non_latin / len(letters) > _NON_LATIN_SHARE_LIMIT
    ):
        return TopicCheck(False, topic, ErrorCode.LANGUAGE_UNSUPPORTED)
    if non_latin > 0:
        warnings.append("NON_LATIN_SHORT")
    if any(ord(c) > 127 for c in latin):
        warnings.append("LATIN_NON_ENGLISH_POSSIBLE")
    return TopicCheck(True, topic, None, warnings)
