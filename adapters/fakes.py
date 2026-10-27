"""Scripted fake providers for tests and demo mode (ARCH §6.5, §13.4).

DEMO MODE USES SYNTHETIC DATA. The corpus below describes a fictional topic on reserved example
domains. It is not real research and must always be labeled as a demo in the UI.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from pydantic import BaseModel

from adapters.base import Block, LLMResult, T
from core.demo import DEMO_NOTICE  # noqa: F401  (re-exported for callers)
from core.models import (
    DraftClaim,
    DraftSection,
    DraftSentence,
    EvidenceRef,
    Facet,
    FacetCategory,
    LedgerDraft,
    Plan,
    RawResult,
    ScanItem,
    ScanOutput,
    SearchResponse,
    Verdict,
    VerifierItem,
    VerifierOutput,
)
from core.tokens import estimate_tokens

DEMO_TOPIC = "The Harborview Bike-Share Pilot (synthetic demo topic)"

_WORD = re.compile(r"[a-z0-9]{3,}")


@dataclass(frozen=True)
class _Doc:
    url: str
    title: str
    published: str | None
    snippet: str
    extracted: str | None


_DOCS: tuple[_Doc, ...] = (
    _Doc(
        "https://city.example.org/harborview/bike-share-pilot",
        "Harborview Bike-Share Pilot: program overview",
        "2024-03-04",
        "The Harborview Bike-Share Pilot launched in March 2024 with 120 bikes at 15 docking stations in the harbor district.",
        "The Harborview Bike-Share Pilot launched in March 2024 with 120 bikes at 15 docking stations in the harbor district. "
        "The city council approved a pilot budget of 1.2 million dollars for the first two years. "
        "Riders pay a flat fee per trip, and the city subsidizes 0.80 dollars of each trip. "
        "The program aims to reduce short car trips in the harbor district. "
        "Docking stations were placed within 400 meters of ferry and bus stops. "
        "A public dashboard reports trips, bike availability and incidents every month. "
        "The council will review the pilot after 24 months before deciding on a permanent service.",
    ),
    _Doc(
        "https://news.example.net/2024/09/bike-share-expands",
        "Bike-share pilot expands to a second district",
        "2024-09-18",
        "By September 2024 the pilot fleet had grown to 180 bikes and 24 docking stations after an expansion into the old market district.",
        "By September 2024 the pilot fleet had grown to 180 bikes and 24 docking stations after an expansion into the old market district. "
        "Officials said demand in the first six months exceeded early forecasts. "
        "The expansion added 60 bikes and 9 stations without raising the pilot budget. "
        "Residents in the market district asked for more stations near the covered market. "
        "The operator said rebalancing bikes between stations is the hardest operational task.",
    ),
    _Doc(
        "https://data.example.com/open/harborview-ridership",
        "Harborview ridership open data summary",
        "2024-10-02",
        "Riders took 41,000 trips in the first six months, with an average trip length of 14 minutes.",
        "Riders took 41,000 trips in the first six months, with an average trip length of 14 minutes. "
        "Weekday ridership peaked at the commuting hours between 7 and 9 in the morning. "
        "Ridership dropped by 35 percent in the winter months compared with the summer months. "
        "About 22 percent of trips started in lower-income neighborhoods according to a survey of 1,200 riders. "
        "The data are published monthly under an open license.",
    ),
    _Doc(
        "https://research.example.org/reports/micromobility-safety",
        "Micromobility safety review for harbor cities",
        "2025-01-15",
        "Nine minor incidents were reported during the first year of the pilot, and none required hospital treatment.",
        "Nine minor incidents were reported during the first year of the pilot, and none required hospital treatment. "
        "The city distributed 800 free helmets during the first year. "
        "Researchers recommended protected lanes on the two busiest streets near the harbor. "
        "Reported incidents were more common on streets without a dedicated bike lane. "
        "The review noted that incident reporting relies on voluntary reports from riders.",
    ),
    _Doc(
        "https://blog.example.com/posts/vandalism-and-replacement",
        "What vandalism costs a bike-share system",
        "2024-12-05",
        "About 6 percent of the bikes were replaced during the first year because of vandalism or damage.",
        None,
    ),
    _Doc(
        "https://harborview.example/press/fleet-update",
        "Fleet update from the pilot operator",
        "2024-09-20",
        "The operator reported a fleet of 175 bikes on the day of the expansion announcement.",
        None,
    ),
    _Doc(
        "https://wire.demo-press.test/stories/bike-share-pilot",
        "Wire story: bike-share pilot expands",
        "2024-09-18",
        "By September 2024 the pilot fleet had grown to 180 bikes and 24 docking stations after an expansion into the old market district.",
        None,
    ),
    _Doc(
        "https://tidewatch.example/analysis/winter-demand",
        "Analysis: how weather shapes bike-share demand",
        "2025-02-11",
        "Cold and wet weather reduced daily trips sharply, and the pilot saw 35 percent fewer trips in winter.",
        "Cold and wet weather reduced daily trips sharply, and the pilot saw 35 percent fewer trips in winter. "
        "Analysts suggested heated docking hubs and winter pricing as ways to hold demand. "
        "The operator said it had not decided whether to change prices.",
    ),
    _Doc(
        "https://example.org/opinion/is-the-subsidy-worth-it",
        "Opinion: is the per-trip subsidy worth it?",
        "2025-03-01",
        "Critics argue that the subsidy of 0.80 dollars per trip is hard to justify while bus service is being cut.",
        "Critics argue that the subsidy of 0.80 dollars per trip is hard to justify while bus service is being cut. "
        "Supporters respond that bike-share trips replace short car trips near the ferry terminal. "
        "Neither side has published a full cost-benefit study of the pilot.",
    ),
    _Doc(
        "https://example.net/features/equity-and-access",
        "Equity and access in the Harborview pilot",
        "2025-04-09",
        "Station placement in the old market district increased access for lower-income riders, according to the city survey.",
        "Station placement in the old market district increased access for lower-income riders, according to the city survey. "
        "The survey covered 1,200 riders and was run by the city in the second quarter. "
        "Riders without smartphones can unlock bikes with a prepaid card at the stations.",
    ),
    _Doc(
        "https://example.com/metadata-only-listing",
        "Listing: bike-share documents",
        None,
        "",
        None,
    ),
)


MIN_RELEVANCE = 0.3  # share of a query's content words a document must contain
_STOPWORDS = frozenset(
    "and the for with from that this are was were has have into over about".split()
)


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _content_tokens(text: str) -> set[str]:
    return _tokens(text) - _STOPWORDS


@dataclass
class FakeSearch:
    """Serves the synthetic corpus. Failures and call records are scriptable."""

    fail_with: Exception | None = None
    calls: list[str] = field(default_factory=list)

    def search(
        self, query: str, *, max_results: int, want_extracted: bool, timeout_s: float
    ) -> SearchResponse:
        self.calls.append(query)
        if self.fail_with is not None:
            raise self.fail_with
        q = _content_tokens(query)
        scored: list[tuple[float, int, _Doc]] = []
        for index, doc in enumerate(_DOCS):
            doc_tokens = _tokens(doc.title + " " + doc.snippet + " " + (doc.extracted or ""))
            overlap = len(q & doc_tokens) / len(q) if q else 0.0
            if overlap >= MIN_RELEVANCE:
                scored.append((overlap, -index, doc))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        results: list[RawResult] = []
        for position, (overlap, _, doc) in enumerate(scored[:max_results]):
            results.append(
                RawResult(
                    provider_result_id=f"demo-{position}",
                    title=doc.title,
                    url=doc.url,
                    snippet=doc.snippet,
                    extracted_text=doc.extracted if want_extracted else None,
                    score=round(max(0.2, min(0.99, 0.35 + overlap)), 3),
                    published_at=doc.published,
                )
            )
        return SearchResponse(results=results, billed_units=1.0)


# --- fake LLM --------------------------------------------------------------------------------


@dataclass(frozen=True)
class CallContext:
    system: str
    blocks: dict[str, str]
    max_output_tokens: int


@dataclass(frozen=True)
class CallRecord:
    schema_name: str
    system: str
    block_labels: tuple[str, ...]


Handler = Callable[[CallContext], BaseModel]

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _json_block(ctx: CallContext, label: str, default: Any) -> Any:
    raw = ctx.blocks.get(label)
    return json.loads(raw) if raw else default


def _plan_handler(ctx: CallContext) -> Plan:
    topic = ctx.blocks.get("topic", "the topic").strip()
    limits = _json_block(ctx, "limits", {})
    n_queries = int(limits.get("planned_queries", 3))
    n_facets = int(limits.get("facets", 4))
    suffixes = [
        "",
        " overview and history",
        " evidence and numbers",
        " risks and criticism",
        " current status",
        " perspectives",
        " causes and drivers",
        " regional context",
    ]
    queries = [f"{topic}{s}".strip() for s in suffixes[: max(2, n_queries)]]
    categories = [
        (FacetCategory.BACKGROUND, "What is it and how did it start?"),
        (FacetCategory.EVIDENCE_TRENDS, "What do the numbers show over time?"),
        (FacetCategory.IMPACTS_RISKS, "What are the benefits and the risks?"),
        (FacetCategory.CURRENT_STATE, "What is the current state?"),
        (FacetCategory.PERSPECTIVES_DISPUTES, "Where do sources disagree?"),
        (FacetCategory.CONTEXT_REGIONAL, "What is the local context?"),
    ]
    facets = [
        Facet(facet_id=f"f{i}", question=q, category=c)
        for i, (c, q) in enumerate(categories[: max(3, n_facets)], 1)
    ]
    return Plan(queries=queries, facets=facets)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text) if 40 <= len(s.strip()) <= 200]


def _writer_handler(ctx: CallContext) -> LedgerDraft:
    plan = _json_block(ctx, "plan", {"facets": [{"facet_id": "f1"}]})
    passages = _json_block(ctx, "passages", [])
    limits = _json_block(ctx, "limits", {})
    facets = [f["facet_id"] for f in plan.get("facets", [])] or ["f1"]
    max_claims = min(int(limits.get("max_claims", 8)), 12)

    picks: list[tuple[dict[str, Any], str]] = []
    seen: set[str] = set()
    for passage in passages:
        candidates = sorted(
            _sentences(str(passage["text"])), key=lambda s: (not any(c.isdigit() for c in s), s)
        )
        for sentence in candidates[:2]:
            if sentence not in seen:
                seen.add(sentence)
                picks.append((passage, sentence))
    picks = picks[:max_claims]

    claims: list[DraftClaim] = []
    for index, (passage, sentence) in enumerate(picks):
        section = (
            "summary"
            if index == 0
            else ("conclusion" if index == len(picks) - 1 and index > 1 else "findings")
        )
        claims.append(
            DraftClaim(
                claim_id=f"c{index + 1}",
                text=sentence,
                facet_id=facets[index % len(facets)],
                section=section,
                evidence=[
                    EvidenceRef(
                        citation_id=int(passage["citation_id"]),
                        passage_id=str(passage["passage_id"]),
                        quote=sentence,
                    )
                ],
            )
        )
    by_section: dict[str, list[DraftSentence]] = {}
    for claim in claims:
        by_section.setdefault(claim.section, []).append(
            DraftSentence(type="claim", claim_id=claim.claim_id)
        )
    findings = by_section.setdefault("findings", [])
    if claims and len(findings) >= 2:
        findings.insert(1, DraftSentence(type="transition", text="Next, the supporting detail."))
        findings.append(
            DraftSentence(
                type="interpretation",
                text="Interpretation: the evidence points in the same direction.",
                refs=[claims[0].claim_id],
            )
        )
    sections = [
        DraftSection(section=name, sentences=sentences) for name, sentences in by_section.items()
    ]
    return LedgerDraft(claims=claims, sections=sections)


def _strip(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d[\d,.]*", text.replace(",", "")))


def _verifier_handler(ctx: CallContext) -> VerifierOutput:
    items = _json_block(ctx, "claims", [])
    results: list[VerifierItem] = []
    for item in items:
        claim = str(item["claim"])
        evidence = item.get("evidence", [])
        verdict = Verdict.UNSUPPORTED
        reason = "Quote does not entail the claim."
        quotes = " ".join(str(e["quote"]) for e in evidence)
        quote_ok = all(
            _strip(str(e["quote"])) in _strip(str(e["passage_text"])) for e in evidence
        ) and bool(evidence)
        if quote_ok:
            if _numbers(claim) - _numbers(quotes):
                reason = "A number in the claim is not in the quote."
            elif _strip(claim) in _strip(quotes):
                verdict, reason = Verdict.SUPPORTED, "The quote states the claim."
            else:
                claim_words, quote_words = _tokens(claim), _tokens(quotes)
                if claim_words and len(claim_words & quote_words) / len(claim_words) >= 0.7:
                    verdict, reason = Verdict.UNCERTAIN, "Partial overlap only."
        results.append(VerifierItem(claim_id=str(item["claim_id"]), verdict=verdict, reason=reason))
    return VerifierOutput(results=results)


def _scan_handler(ctx: CallContext) -> ScanOutput:
    items = _json_block(ctx, "sentences", [])
    results = []
    for item in items:
        text = str(item["text"])
        body_words = text.split()[1:]
        flagged = any(c.isdigit() for c in text) or any(w[:1].isupper() for w in body_words)
        results.append(
            ScanItem(
                sentence_ref=str(item["ref"]),
                contains_material_fact=flagged,
                reason="Contains a number or named entity." if flagged else "",
            )
        )
    return ScanOutput(results=results)


class FakeLLM:
    """Scripted model. Defaults produce valid, checkable output from the data blocks it is given."""

    def __init__(self, model_id: str = "fake-writer") -> None:
        self.model_id = model_id
        self.calls: list[CallRecord] = []
        self._handlers: dict[type[BaseModel], Handler] = {
            Plan: _plan_handler,
            LedgerDraft: _writer_handler,
            VerifierOutput: _verifier_handler,
            ScanOutput: _scan_handler,
        }

    def set_handler(self, schema: type[BaseModel], handler: Handler) -> None:
        self._handlers[schema] = handler

    def generate(
        self,
        *,
        system: str,
        blocks: Sequence[Block],
        schema: type[T],
        max_output_tokens: int,
        temperature: float,
        timeout_s: float,
    ) -> LLMResult[T]:
        handler = self._handlers.get(schema)
        if handler is None:
            raise NotImplementedError(f"No fake handler for {schema.__name__}")
        self.calls.append(CallRecord(schema.__name__, system, tuple(b.label for b in blocks)))
        ctx = CallContext(system, {b.label: b.content for b in blocks}, max_output_tokens)
        parsed = handler(ctx)
        input_tokens = estimate_tokens(system + "".join(b.content for b in blocks))
        output_tokens = estimate_tokens(parsed.model_dump_json())
        return LLMResult(
            parsed=cast(T, parsed),
            model_id=self.model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
