"""Deterministic source selection and the evidence registry (PRD §6.2, ARCH §3.3).

Pipeline: canonicalize and merge, score, drop syndicated copies, select with domain diversity,
chunk into passages, trim to the writer input cap, then assign contiguous citation IDs.
Everything here is a pure function of its inputs, so the same input always gives the same registry.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import tldextract

from core.models import EvidenceMode, Passage, RawResult, SourceRecord
from core.settings import ModeConfig
from core.tokens import DEFAULT_CHARS_PER_TOKEN, MAX_PASSAGE_CHARS, estimate_tokens
from pipeline.claim_checks import normalize_for_match

CHUNK_MAX_CHARS = 800
MIN_USABLE_CHARS = 30
RECENCY_WINDOW_DAYS = 365

# Versioned allowlist of registrable-domain suffixes treated as primary evidence (placeholder).
PRIMARY_SUFFIXES_VERSION = "primary-v1-placeholder"
DEFAULT_PRIMARY_SUFFIXES: frozenset[str] = frozenset(
    {"gov", "edu", "int", "gov.in", "nic.in", "ac.in", "gov.uk", "ac.uk"}
)

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref_src",
}
_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "were", "has", "have",
    "into", "about", "what", "how", "why", "who", "their", "its", "can", "will", "not", "but",
}  # fmt: skip
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


# --- urls, domains, text -----------------------------------------------------------------------


def canonicalize_url(url: str) -> str | None:
    """Normalize an http(s) URL, or return None if it is unsafe or invalid."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"}:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    host = (parts.hostname or "").lower()
    if not host or " " in host:
        return None
    if host.startswith("www."):
        host = host[4:]
    scheme = parts.scheme.lower()
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    query_pairs = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    )
    return urlunsplit((scheme, netloc, path, urlencode(query_pairs), ""))


def registrable_domain(url: str) -> str:
    """Registrable domain from the bundled public suffix snapshot (no network)."""
    ext = _EXTRACTOR(url)
    domain = ext.top_domain_under_public_suffix or ext.top_domain_under_registry_suffix
    if domain:
        return str(domain)
    return (urlsplit(url).hostname or ext.domain or "").lower()


def usable_text(text: str | None) -> bool:
    if not text:
        return False
    return sum(1 for c in text if not c.isspace()) >= MIN_USABLE_CHARS


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS}


def _lexical_overlap(passage: str, query_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    return len(_tokens(passage) & query_tokens) / len(query_tokens)


def chunk_extracted(text: str) -> list[str]:
    """Split extracted text at sentence boundaries into non-overlapping chunks (max 800 chars)."""
    boundaries = [m.end() for m in re.finditer(r"[.!?]\s+", text)]
    sentences: list[str] = []
    start = 0
    for end in [*boundaries, len(text)]:
        if end > start:
            sentences.append(text[start:end])
            start = end
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > CHUNK_MAX_CHARS:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:CHUNK_MAX_CHARS])
            sentence = sentence[CHUNK_MAX_CHARS:]
        if len(current) + len(sentence) > CHUNK_MAX_CHARS and current:
            chunks.append(current)
            current = ""
        current += sentence
    if current:
        chunks.append(current)
    return [c.strip() for c in chunks if c.strip()]


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).replace(tzinfo=UTC)
    except ValueError:
        return None


# --- registry build ----------------------------------------------------------------------------


@dataclass
class _Candidate:
    result: RawResult
    canonical: str
    domain: str
    text: str
    mode: EvidenceMode
    rank: int
    score: float
    primary: bool
    group_id: str
    passages: list[tuple[str, float, bool]] = field(
        default_factory=list
    )  # text, overlap, truncated


@dataclass(frozen=True)
class NotInspected:
    title: str
    url: str
    canonical_url: str
    reason: str = "metadata-only"


@dataclass
class RegistryStats:
    candidates: int = 0
    invalid_urls: int = 0
    merged_duplicates: int = 0
    syndicated_dropped: int = 0
    dropped_passages: int = 0
    dropped_sources: int = 0


@dataclass
class RegistryBuild:
    sources: list[SourceRecord]
    not_inspected: list[NotInspected]
    stats: RegistryStats


def _candidate_key(c: _Candidate) -> tuple[float, int, int, str]:
    return (c.score, 1 if c.mode is EvidenceMode.EXTRACTED else 0, len(c.text), c.text)


def build_registry(
    results_by_query: Sequence[Sequence[RawResult]],
    queries: Sequence[str],
    topic: str,
    cfg: ModeConfig,
    now: datetime,
    *,
    time_sensitive: bool = False,
    primary_suffixes: Collection[str] = DEFAULT_PRIMARY_SUFFIXES,
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
    recency_window_days: int = RECENCY_WINDOW_DAYS,
) -> RegistryBuild:
    stats = RegistryStats()
    not_inspected: dict[str, NotInspected] = {}
    best: dict[str, _Candidate] = {}

    for results in results_by_query:
        for rank, raw in enumerate(results):
            stats.candidates += 1
            canonical = canonicalize_url(raw.url)
            if canonical is None:
                stats.invalid_urls += 1
                continue
            if usable_text(raw.extracted_text):
                text, mode = (raw.extracted_text or "").strip(), EvidenceMode.EXTRACTED
            elif usable_text(raw.snippet):
                text, mode = raw.snippet.strip(), EvidenceMode.SNIPPET
            else:
                not_inspected.setdefault(canonical, NotInspected(raw.title, raw.url, canonical))
                continue
            relevance = min(max(raw.score, 0.0), 1.0) if raw.score is not None else 1.0 / (1 + rank)
            domain = registrable_domain(canonical)
            primary = any(domain == s or domain.endswith("." + s) for s in primary_suffixes)
            recency = 0.0
            published = _parse_date(raw.published_at)
            if time_sensitive and published is not None:
                if (
                    now - timedelta(days=recency_window_days)
                    <= published
                    <= now + timedelta(days=1)
                ):
                    recency = 1.0
            score = (
                4 * relevance
                + (2 if mode is EvidenceMode.EXTRACTED else 0)
                + (1 if primary else 0)
                + recency
            )
            group = hashlib.sha1(normalize_for_match(text)[:400].encode("utf-8")).hexdigest()[:16]
            cand = _Candidate(raw, canonical, domain, text, mode, rank, score, primary, group)
            existing = best.get(canonical)
            if existing is None:
                best[canonical] = cand
            else:
                stats.merged_duplicates += 1
                if _candidate_key(cand) > _candidate_key(existing):
                    best[canonical] = cand

    ranked = sorted(best.values(), key=lambda c: (-c.score, c.canonical))

    # Syndicated copies share an evidence group; only the best-ranked one is selected.
    seen_groups: set[str] = set()
    unique: list[_Candidate] = []
    for cand in ranked:
        if cand.group_id in seen_groups:
            stats.syndicated_dropped += 1
            continue
        seen_groups.add(cand.group_id)
        unique.append(cand)

    selected = _select_diverse(unique, cfg.max_sources)
    selected.sort(key=lambda c: (-c.score, c.canonical))

    query_tokens = _tokens(" ".join([topic, *queries]))
    for cand in selected:
        _build_passages(cand, query_tokens, cfg.max_passages_per_source)

    selected = _trim_to_cap(selected, cfg, chars_per_token, stats)

    sources: list[SourceRecord] = []
    for cid, cand in enumerate(selected, start=1):
        passages = [
            Passage(passage_id=f"{cid}:p{i}", text=text, truncated=truncated, lexical_score=overlap)
            for i, (text, overlap, truncated) in enumerate(cand.passages, start=1)
        ]
        sources.append(
            SourceRecord(
                citation_id=cid,
                provider_result_id=cand.result.provider_result_id,
                title=cand.result.title,
                url=cand.result.url,
                canonical_url=cand.canonical,
                registrable_domain=cand.domain,
                published_at=cand.result.published_at,
                retrieved_at=now.isoformat().replace("+00:00", "Z"),
                evidence_mode=cand.mode,
                passages=passages,
                evidence_group_id=cand.group_id,
                primary_evidence_verified=cand.primary,
                provider_rank=cand.rank,
                score=cand.score,
            )
        )
    return RegistryBuild(
        sources, sorted(not_inspected.values(), key=lambda n: n.canonical_url), stats
    )


def _select_diverse(candidates: list[_Candidate], cap: int) -> list[_Candidate]:
    """Round-robin by registrable domain so every domain is used before any gets a second source."""
    by_domain: dict[str, list[_Candidate]] = defaultdict(list)
    order: list[str] = []
    for cand in candidates:  # already sorted best-first
        if cand.domain not in by_domain:
            order.append(cand.domain)
        by_domain[cand.domain].append(cand)
    chosen: list[_Candidate] = []
    round_index = 0
    while len(chosen) < cap:
        progressed = False
        for domain in order:
            bucket = by_domain[domain]
            if round_index < len(bucket):
                chosen.append(bucket[round_index])
                progressed = True
                if len(chosen) >= cap:
                    break
        if not progressed:
            break
        round_index += 1
    return chosen


def _build_passages(cand: _Candidate, query_tokens: set[str], per_source_cap: int) -> None:
    if cand.mode is EvidenceMode.SNIPPET:
        text = cand.text
        truncated = len(text) > MAX_PASSAGE_CHARS
        cand.passages = [
            (text[:MAX_PASSAGE_CHARS], _lexical_overlap(text, query_tokens), truncated)
        ]
        return
    chunks = chunk_extracted(cand.text)
    scored = [(i, c, _lexical_overlap(c, query_tokens)) for i, c in enumerate(chunks)]
    kept = sorted(scored, key=lambda t: (-t[2], t[0]))[:per_source_cap]
    dropped_any = len(kept) < len(scored)
    kept.sort(key=lambda t: t[0])
    cand.passages = [(c, o, dropped_any) for _, c, o in kept]


def _trim_to_cap(
    selected: list[_Candidate], cfg: ModeConfig, chars_per_token: float, stats: RegistryStats
) -> list[_Candidate]:
    """Drop lowest-value evidence until the writer input estimate fits the cap (PRD §6.2 step 7)."""

    def total() -> int:
        return cfg.prompt_allowance + sum(
            estimate_tokens(text, chars_per_token) for c in selected for text, _, _ in c.passages
        )

    if total() <= cfg.writer_input_cap:
        return selected
    # Step 1: lowest-scoring source first, drop its lowest-overlap non-top passages.
    for cand in sorted(selected, key=lambda c: (c.score, c.canonical)):
        while total() > cfg.writer_input_cap and len(cand.passages) > 1:
            top_index = max(range(len(cand.passages)), key=lambda i: (cand.passages[i][1], -i))
            droppable = [i for i in range(len(cand.passages)) if i != top_index]
            victim = min(droppable, key=lambda i: (cand.passages[i][1], -i))
            del cand.passages[victim]
            stats.dropped_passages += 1
        if total() <= cfg.writer_input_cap:
            return selected
    # Step 2: drop whole sources from the lowest score upward, never the last one.
    for cand in sorted(selected, key=lambda c: (c.score, c.canonical)):
        if total() <= cfg.writer_input_cap or len(selected) <= 1:
            break
        selected.remove(cand)
        stats.dropped_sources += 1
        stats.dropped_passages += len(cand.passages)
    return selected
