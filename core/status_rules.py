"""The single implementation of the terminal status rules (PRD §6.4, ARCH §5.4).

Counts are computed by deterministic code from verified claims and the registry. The writer never
chooses a count or a status.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.models import ClaimRecord, EvidenceMode, Facet, RunStatus, SourceRecord, Verdict
from core.settings import ModeConfig

MIN_SAFE_CLAIMS = 2


@dataclass(frozen=True)
class RunCounts:
    fatal_error: str | None
    supported_claims: int
    usable_groups: int
    domains: int
    supported_facets: int
    snippet_only_share: float
    timed_out: bool
    budget_stopped: bool


def evaluate(counts: RunCounts, cfg: ModeConfig) -> tuple[RunStatus, list[str]]:
    """Return the status and a reason code for every unmet threshold (PRD §6.4 decision order)."""
    if counts.fatal_error:
        return RunStatus.FAILED, [counts.fatal_error]
    if counts.supported_claims < MIN_SAFE_CLAIMS:
        return RunStatus.FAILED, ["INSUFFICIENT_CLAIMS"]
    if counts.usable_groups < 1:
        return RunStatus.FAILED, ["LOW_EVIDENCE_GROUPS"]

    reasons: list[str] = []
    if counts.usable_groups < cfg.min_groups:
        reasons.append("LOW_EVIDENCE_GROUPS")
    if counts.domains < cfg.min_domains:
        reasons.append("LOW_DOMAINS")
    if counts.supported_claims < cfg.min_claims:
        reasons.append("INSUFFICIENT_CLAIMS")
    if counts.supported_facets < cfg.min_facets:
        reasons.append("INCOMPLETE_FACETS")
    if counts.snippet_only_share > cfg.max_snippet_share:
        reasons.append("SNIPPET_HEAVY")
    if counts.timed_out:
        reasons.append("TIMEOUT")
    if counts.budget_stopped:
        reasons.append("BUDGET_STOP")
    return (RunStatus.COMPLETED, []) if not reasons else (RunStatus.PARTIAL, reasons)


def compute_counts(
    claims: Sequence[ClaimRecord],
    sources: Mapping[int, SourceRecord],
    facets: Sequence[Facet],
    *,
    fatal_error: str | None = None,
    timed_out: bool = False,
    budget_stopped: bool = False,
) -> RunCounts:
    """Counts over distinct supported claim IDs and the registry (PRD §6.4 counting rule)."""
    supported: dict[str, ClaimRecord] = {}
    for claim in claims:
        if claim.support_verdict is Verdict.SUPPORTED and claim.claim_id not in supported:
            supported[claim.claim_id] = claim

    planned = {f.facet_id for f in facets}
    covered_facets = {c.facet_id for c in supported.values() if c.facet_id in planned}

    snippet_only = 0
    for claim in supported.values():
        modes = [
            sources[r.citation_id].evidence_mode for r in claim.evidence if r.citation_id in sources
        ]
        if modes and all(m is EvidenceMode.SNIPPET for m in modes):
            snippet_only += 1
    share = snippet_only / len(supported) if supported else 0.0

    usable = [
        s
        for s in sources.values()
        if s.evidence_mode is not EvidenceMode.METADATA_ONLY and s.passages
    ]
    return RunCounts(
        fatal_error=fatal_error,
        supported_claims=len(supported),
        usable_groups=len({s.evidence_group_id for s in usable}),
        domains=len({s.registrable_domain for s in usable}),
        supported_facets=len(covered_facets),
        snippet_only_share=share,
        timed_out=timed_out,
        budget_stopped=budget_stopped,
    )
