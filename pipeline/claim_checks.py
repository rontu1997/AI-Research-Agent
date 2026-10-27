"""Deterministic claim checks (PRD FR-33, FR-34; ARCH §5.7). Pure functions, no I/O.

Quote match: the quote must lie inside one stored passage after ``normalize_for_match``.
Numeric guard: every number, percent, currency, magnitude word and month in a claim must also
appear in the claim's quotes, so derived or invented figures are rejected before any model call.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from core.models import ClaimRecord, EvidenceMode, SourceRecord
from core.tokens import QUOTE_MAX_CHARS, QUOTE_MIN_CHARS

INTERPRETATION_MAX_WORDS = 40
TRANSITION_MAX_WORDS = 15
INTERPRETATION_LABEL = "Interpretation:"

# --- normalization ---------------------------------------------------------------------------

_QUOTE_MAP = {
    ord("“"): '"',
    ord("”"): '"',
    ord("„"): '"',
    ord("‟"): '"',
    ord("‘"): "'",
    ord("’"): "'",
    ord("‚"): "'",
    ord("‛"): "'",
    ord("–"): "-",
    ord("—"): "-",
    ord("−"): "-",
    ord("‑"): "-",
}
_WS_RE = re.compile(r"\s+")


def _normalize_once(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTE_MAP)
    return _WS_RE.sub(" ", text).strip().casefold()


def normalize_for_match(text: str) -> str:
    """NFKC, quote and dash unification, whitespace collapse, case-insensitive. Idempotent."""
    current = _normalize_once(text)
    for _ in range(4):
        nxt = _normalize_once(current)
        if nxt == current:
            break
        current = nxt
    return current


def _boundaries_ok(haystack: str, start: int, end: int) -> bool:
    """A quote must begin and end on a word or number boundary, never inside one."""
    first, last = haystack[start], haystack[end - 1]
    if start > 0:
        before = haystack[start - 1]
        if first.isalnum() and before.isalnum():
            return False
        if first.isdigit() and before in ".," and start > 1 and haystack[start - 2].isdigit():
            return False
    if end < len(haystack):
        after = haystack[end]
        if last.isalnum() and after.isalnum():
            return False
        if (
            last.isdigit()
            and after in ".,"
            and end + 1 < len(haystack)
            and haystack[end + 1].isdigit()
        ):
            return False
    return True


def quote_in_passage(quote: str, passage_text: str) -> bool:
    needle = normalize_for_match(quote)
    if not needle:
        return False
    haystack = normalize_for_match(passage_text)
    position = haystack.find(needle)
    while position >= 0:
        if _boundaries_ok(haystack, position, position + len(needle)):
            return True
        position = haystack.find(needle, position + 1)
    return False


# --- numeric guard ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"(?<!\d)(?:\d[\d,]*(?:\.\d+)?|\.\d+)")
_ABBREV_MAGNITUDE_RE = re.compile(r"\d\s?(bn|mn|tn|k|m|b)\b", re.IGNORECASE)
_ABBREV_MAGNITUDES = {
    "k": "thousand",
    "m": "million",
    "mn": "million",
    "b": "billion",
    "bn": "billion",
    "tn": "trillion",
}
_DATE_RE = re.compile(r"\b\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}\b")
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
_QUANT_WORDS = {
    "half": "half",
    "halves": "half",
    "quarter": "quarter",
    "quarters": "quarter",
    "third": "third",
    "thirds": "third",
    "twice": "twice",
    "double": "double",
    "doubled": "double",
    "doubling": "double",
    "triple": "triple",
    "tripled": "triple",
    "tripling": "triple",
    "quadruple": "quadruple",
    "quadrupled": "quadruple",
}
_NUMBER_WORDS = {
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
    "hundred": "100",
    "dozen": "12",
}
_MAGNITUDES = ("thousand", "million", "billion", "trillion", "lakh", "crore")
_MONTHS = {
    "january": "jan",
    "february": "feb",
    "march": "mar",
    "april": "apr",
    "june": "jun",
    "july": "jul",
    "august": "aug",
    "september": "sep",
    "october": "oct",
    "november": "nov",
    "december": "dec",
}
_MONTH_ABBREV = {
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
}
_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}
_CURRENCY_WORDS = {
    "dollar": "USD",
    "dollars": "USD",
    "usd": "USD",
    "euro": "EUR",
    "euros": "EUR",
    "eur": "EUR",
    "pound": "GBP",
    "pounds": "GBP",
    "gbp": "GBP",
    "rupee": "INR",
    "rupees": "INR",
    "inr": "INR",
}
_PERCENT_RE = re.compile(r"%|\bper\s?cent\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z]+")


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    missing: list[str] = field(default_factory=list)


def _canonical_number(raw: str) -> str | None:
    cleaned = raw.replace(",", "").rstrip(".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return format(value.normalize(), "f")


def numeric_tokens(text: str) -> set[str]:
    """Numbers and number-like markers in ``text``, canonicalized for comparison."""
    tokens: set[str] = set()
    for match in _NUMBER_RE.finditer(text):
        canon = _canonical_number(match.group(0))
        if canon is None:
            continue
        start = match.start()
        if (
            start > 0
            and text[start - 1] in "-\u2212"
            and (start == 1 or not text[start - 2].isalnum())
        ):
            canon = "-" + canon  # a sign, not a hyphen or a range dash
        tokens.add(canon)
    for abbrev in _ABBREV_MAGNITUDE_RE.finditer(text):
        tokens.add(f"mag:{_ABBREV_MAGNITUDES[abbrev.group(1).lower()]}")
    for date in _DATE_RE.finditer(text):
        tokens.add("dt:" + re.sub(r"[/.]", "-", date.group(0)))
    for clock in _TIME_RE.finditer(text):
        tokens.add("tm:" + clock.group(0))
    lowered = text.lower()
    for word in _WORD_RE.findall(lowered):
        if word in _NUMBER_WORDS:
            tokens.add(_NUMBER_WORDS[word])
        elif word in _MAGNITUDES:
            tokens.add(f"mag:{word}")
        elif word in _QUANT_WORDS:
            tokens.add(f"q:{_QUANT_WORDS[word]}")
        elif word in _CURRENCY_WORDS:
            tokens.add(f"cur:{_CURRENCY_WORDS[word]}")
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in text:
            tokens.add(f"cur:{code}")
    if _PERCENT_RE.search(text):
        tokens.add("pct")
    # ALL-CAPS month names ("MARCH 2024"); "MAY" only next to a day or year.
    for word in re.findall(r"\b[A-Z]{3,9}\b", text):
        key = word.lower()
        if key in _MONTHS:
            tokens.add(f"mon:{_MONTHS[key]}")
        elif key == "may" and re.search(r"\bMAY\b\s+\d|\d\s+MAY\b", text):
            tokens.add("mon:may")
    # Capitalized month names (case-sensitive so the modal verb "may" is not a date).
    for word in re.findall(r"\b[A-Z][a-z]+\b\.?", text):
        key = word.rstrip(".").lower()
        if key in _MONTHS:
            tokens.add(f"mon:{_MONTHS[key]}")
        elif key == "may" and re.search(r"\bMay\b\s+\d|\d\s+May\b", text):
            tokens.add("mon:may")
        elif key in _MONTH_ABBREV and word.rstrip(".") != key:
            tokens.add(f"mon:{key[:3]}")
    return tokens


def numeric_guard(claim_text: str, quotes: Sequence[str]) -> GuardResult:
    """Every numeric token in the claim must appear in the joined quotes."""
    claim_tokens = numeric_tokens(claim_text)
    quote_tokens = numeric_tokens(" ".join(quotes))
    missing = sorted(t for t in claim_tokens if t not in quote_tokens)
    return GuardResult(ok=not missing, missing=missing)


# --- whole-claim checks ----------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimCheck:
    ok: bool
    reason: str | None = None
    quote_match_ok: bool = False
    numeric_guard_ok: bool = False


def check_claim(
    claim: ClaimRecord,
    sources: Mapping[int, SourceRecord],
    max_quotes: int,
) -> ClaimCheck:
    """Run the deterministic checks of PRD FR-33. A failure marks the claim unsupported."""
    if not claim.evidence:
        return ClaimCheck(False, "NO_EVIDENCE")
    if len(claim.evidence) > max_quotes:
        return ClaimCheck(False, "TOO_MANY_QUOTES")

    quotes: list[str] = []
    for ref in claim.evidence:
        source = sources.get(ref.citation_id)
        if source is None:
            return ClaimCheck(False, "UNKNOWN_CITATION")
        if source.evidence_mode is EvidenceMode.METADATA_ONLY:
            return ClaimCheck(False, "METADATA_ONLY")
        passage = next((p for p in source.passages if p.passage_id == ref.passage_id), None)
        if passage is None:
            return ClaimCheck(False, "UNKNOWN_PASSAGE")
        stripped = ref.quote.strip()
        if not QUOTE_MIN_CHARS <= len(stripped) <= QUOTE_MAX_CHARS:
            return ClaimCheck(False, "QUOTE_LENGTH")
        if not quote_in_passage(stripped, passage.text):
            return ClaimCheck(False, "QUOTE_NOT_IN_PASSAGE")
        quotes.append(stripped)

    guard = numeric_guard(claim.text, quotes)
    if not guard.ok:
        return ClaimCheck(False, "NUMERIC_MISMATCH", quote_match_ok=True, numeric_guard_ok=False)
    return ClaimCheck(True, None, quote_match_ok=True, numeric_guard_ok=True)


# --- sentence rules (PRD FR-34, ARCH §5.7) -----------------------------------------------------

_URL_RE = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|org|net|gov|edu|io|in|co)\b", re.IGNORECASE)
_CAPITALIZED_RE = re.compile(r"\b[A-Z][A-Za-z]*\b")


@dataclass(frozen=True)
class RuleCheck:
    ok: bool
    reason: str | None = None


def _vocabulary(texts: Iterable[str]) -> set[str]:
    words: set[str] = set()
    for text in texts:
        words.update(w.lower() for w in _WORD_RE.findall(text))
    return words


_STARTERS = frozenset(
    "a an the this that these those it its they there here next then finally overall however "
    "meanwhile also additionally moreover similarly further still yet but and or so thus taken "
    "together in on at as by with for from to of after before now first second while although "
    "because since if when what which who some many most both each such more less another other "
    "one".split()
)


def _new_capitalized_word(body: str, allowed: set[str]) -> bool:
    """True if a capitalized word is neither known vocabulary nor (for the first word) a starter."""
    first = True
    for match in re.finditer(r"\S+", body):
        token = match.group(0)
        for cap in _CAPITALIZED_RE.findall(token):
            word = cap.lower()
            if word in allowed or (first and word in _STARTERS):
                continue
            return True
        first = False
    return False


def check_interpretation(
    text: str,
    refs: Sequence[str],
    claim_texts: Mapping[str, str],
    *,
    topic: str,
    headings: Sequence[str],
) -> RuleCheck:
    """Interpretation sentences may add no new fact, number or named entity."""
    if not text.startswith(INTERPRETATION_LABEL):
        return RuleCheck(False, "NO_LABEL")
    valid = [r for r in refs if r in claim_texts]
    if not valid:
        return RuleCheck(False, "NO_VALID_REF")
    body = text[len(INTERPRETATION_LABEL) :].strip()
    if len(body.split()) > INTERPRETATION_MAX_WORDS:
        return RuleCheck(False, "TOO_LONG")
    sources = [claim_texts[r] for r in valid] + [topic, *headings]
    allowed_words = _vocabulary(sources)
    allowed_numbers = numeric_tokens(" ".join(sources))
    if any(t not in allowed_numbers for t in numeric_tokens(body)):
        return RuleCheck(False, "NEW_TOKEN")
    if _URL_RE.search(body):
        return RuleCheck(False, "NEW_TOKEN")
    if _new_capitalized_word(body, allowed_words):
        return RuleCheck(False, "NEW_TOKEN")
    return RuleCheck(True)


def check_transition(text: str, *, topic: str, headings: Sequence[str]) -> RuleCheck:
    """Transitions are short connective text: no digits, URLs or new named entities."""
    if len(text.split()) > TRANSITION_MAX_WORDS:
        return RuleCheck(False, "TOO_LONG")
    if any(ch.isdigit() for ch in text) or numeric_tokens(text):
        return RuleCheck(False, "HAS_DIGIT")
    if _URL_RE.search(text):
        return RuleCheck(False, "HAS_URL")
    if _new_capitalized_word(text, _vocabulary([topic, *headings])):
        return RuleCheck(False, "NEW_TOKEN")
    return RuleCheck(True)
