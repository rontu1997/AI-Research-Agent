"""Pydantic domain models (PRD §9, ARCH §5.6 and §7.3). No I/O lives here."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Mode(str, Enum):
    QUICK = "quick"
    DEEP = "deep"


class EvidenceMode(str, Enum):
    SNIPPET = "snippet"
    EXTRACTED = "extracted"
    METADATA_ONLY = "metadata-only"


class RunStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class Verdict(str, Enum):
    SUPPORTED = "supported"
    UNCERTAIN = "uncertain"
    UNSUPPORTED = "unsupported"


class FacetCategory(str, Enum):
    BACKGROUND = "background"
    DRIVERS_MECHANISMS = "drivers_mechanisms"
    EVIDENCE_TRENDS = "evidence_trends"
    IMPACTS_RISKS = "impacts_risks"
    PERSPECTIVES_DISPUTES = "perspectives_disputes"
    CURRENT_STATE = "current_state"
    CONTEXT_REGIONAL = "context_regional"
    OTHER = "other"


SectionName = Literal["summary", "findings", "data", "competing", "conclusion"]
SECTION_ORDER: tuple[SectionName, ...] = ("summary", "findings", "data", "competing", "conclusion")
SECTION_TITLES: dict[SectionName, str] = {
    "summary": "Summary",
    "findings": "Key findings",
    "data": "Data and figures",
    "competing": "Competing views",
    "conclusion": "Conclusion",
}


# --- request ---------------------------------------------------------------------------------


class ResearchRequest(_Strict):
    topic: str
    depth: Mode
    idempotency_token: str


# --- provider contracts (ARCH §6.5) ------------------------------------------------------------


class RawResult(_Strict):
    provider_result_id: str | None = None
    title: str
    url: str
    snippet: str = ""
    extracted_text: str | None = None
    score: float | None = None
    published_at: str | None = None


class SearchResponse(_Strict):
    results: list[RawResult]
    billed_units: float | None = None
    request_meta: dict[str, str] = Field(default_factory=dict)


# --- evidence registry (PRD §9.2) --------------------------------------------------------------


class Passage(_Strict):
    passage_id: str
    text: str
    truncated: bool = False
    lexical_score: float = 0.0


class SourceRecord(_Strict):
    citation_id: int
    provider_result_id: str | None = None
    title: str
    url: str
    canonical_url: str
    registrable_domain: str
    published_at: str | None = None
    retrieved_at: str
    evidence_mode: EvidenceMode
    passages: list[Passage]
    evidence_group_id: str
    primary_evidence_verified: bool = False
    provider_rank: int | None = None
    score: float = 0.0
    retrieval_warning: str | None = None


# --- plan and ledger (ARCH §5.6) ---------------------------------------------------------------


class Facet(_Strict):
    facet_id: str
    question: str
    category: FacetCategory


class Plan(_Strict):
    queries: list[str]
    facets: list[Facet]


class EvidenceRef(_Strict):
    citation_id: int
    passage_id: str
    quote: str


class DraftClaim(_Strict):
    claim_id: str
    text: str
    facet_id: str
    section: SectionName
    evidence: list[EvidenceRef]


class DraftSentence(_Strict):
    type: Literal["claim", "interpretation", "transition"]
    claim_id: str | None = None
    text: str | None = None
    refs: list[str] = Field(default_factory=list)


class DraftSection(_Strict):
    section: SectionName
    sentences: list[DraftSentence]


class LedgerDraft(_Strict):
    claims: list[DraftClaim]
    sections: list[DraftSection]


class VerifierItem(_Strict):
    claim_id: str
    verdict: Verdict
    reason: str = ""


class VerifierOutput(_Strict):
    results: list[VerifierItem]


class ScanItem(_Strict):
    sentence_ref: str
    contains_material_fact: bool
    reason: str = ""


class ScanOutput(_Strict):
    results: list[ScanItem]


# --- checked claims and results ---------------------------------------------------------------


class ClaimRecord(_Strict):
    claim_id: str
    text: str
    facet_id: str
    section: SectionName
    evidence: list[EvidenceRef]
    quote_match_ok: bool = False
    numeric_guard_ok: bool = False
    support_verdict: Verdict | None = None
    support_reason: str = ""
    reject_reason: str | None = None


class RenderedItem(_Strict):
    kind: Literal["claim", "interpretation", "transition"]
    claim_id: str | None = None
    claim_number: int | None = None
    text: str
    citation_ids: list[int] = Field(default_factory=list)


class RenderedSection(_Strict):
    section: SectionName
    items: list[RenderedItem]


class FacetCoverage(_Strict):
    facet_id: str
    question: str
    category: FacetCategory
    supported_claims: int


class RunMetrics(_Strict):
    query_count: int = 0
    usable_sources: int = 0
    unique_domains: int = 0
    supported_claims: int = 0
    supported_facets: int = 0
    planned_facets: int = 0
    snippet_only_claim_share: float = 0.0
    elapsed_ms: int = 0
    modeled_spend_ceiling_usd: float = 0.0
    estimated_actual_cost_usd: float | None = None
    drafted_claims: int = 0
    removed_claims: int = 0
    dropped_passages: int = 0
    replan_used: bool = False
    repair_used: bool = False


class ResearchResult(_Strict):
    run_id: str
    mode: Mode
    status: RunStatus
    reason_codes: list[str] = Field(default_factory=list)
    error_code: str | None = None
    detail: str | None = None  # an exception class name, never a message
    researched_on: str = Field(default_factory=lambda: date.today().isoformat())
    report_markdown: str | None = None
    sections: list[RenderedSection] = Field(default_factory=list)
    facet_coverage: list[FacetCoverage] = Field(default_factory=list)
    claims: list[ClaimRecord] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    unused_source_ids: list[int] = Field(default_factory=list)
    source_ids: list[int] = Field(default_factory=list)
    validated_claim_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    finished_at: datetime | None = None
