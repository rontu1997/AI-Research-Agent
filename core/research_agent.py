"""The research run: plan, search, register, draft, check, verify, repair, scan, report.

Fail-closed: a claim reaches the report only after the deterministic checks and the independent
verifier both pass. Status comes from ``core.status_rules`` and nothing else (PRD §6.4).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from core.errors import (
    BudgetStop,
    DeadlineExceeded,
    ErrorCode,
    PipelineFailure,
    ProviderError,
    RunCancelled,
)
from core.models import (
    SECTION_ORDER,
    ClaimRecord,
    DraftSentence,
    EvidenceMode,
    FacetCoverage,
    Mode,
    RawResult,
    ResearchRequest,
    ResearchResult,
    RunMetrics,
    RunStatus,
    SectionName,
    SourceRecord,
    Verdict,
)
from core.status_rules import compute_counts, evaluate
from core.validation import describe_warnings, validate_topic
from pipeline.claim_checks import check_claim
from pipeline.claim_ledger import normalize_draft
from pipeline.context import RunContext
from pipeline.planner import make_plan
from pipeline.repair import repair_claims
from pipeline.report import assemble_sections, render_markdown, sentence_ref
from pipeline.scan import scan_sentences
from pipeline.source_processing import NotInspected, build_registry
from pipeline.verifier import VerifierCache, verify_claims
from pipeline.writer import draft_ledger

Progress = Callable[[str, float], None]

RESULTS_PER_QUERY = 10
SEARCH_PARALLEL = 4
_TIME_WORDS = re.compile(
    r"\b(latest|current|currently|recent|recently|today|now|news|this year|this month|20[2-9]\d)\b",
    re.IGNORECASE,
)

STAGES: tuple[tuple[str, str, float], ...] = (
    ("planning", "Planning the research", 0.05),
    ("searching", "Searching for sources", 0.20),
    ("reading", "Reading and ranking sources", 0.40),
    ("drafting", "Drafting claims", 0.55),
    ("verifying", "Checking every claim against its source", 0.75),
    ("repairing", "Repairing claims that failed a check", 0.85),
    ("finishing", "Writing the report", 0.95),
)
_STAGE_FRACTION = {name: frac for name, _, frac in STAGES}


def is_time_sensitive(topic: str) -> bool:
    return bool(_TIME_WORDS.search(topic))


def _failure(
    request: ResearchRequest,
    run_id: str,
    code: str,
    started: float,
    ctx: RunContext | None,
    warnings: Sequence[str] = (),
    reasons: Sequence[str] | None = None,
    replan_used: bool = False,
    detail: str | None = None,
) -> ResearchResult:
    return ResearchResult(
        run_id=run_id,
        mode=request.depth,
        status=RunStatus.FAILED,
        reason_codes=list(reasons) if reasons is not None else [code],
        error_code=code,
        detail=detail or None,
        warnings=list(warnings),
        metrics=RunMetrics(
            elapsed_ms=int((time.monotonic() - started) * 1000),
            modeled_spend_ceiling_usd=ctx.cfg.cost_cap_usd if ctx else 0.0,
            estimated_actual_cost_usd=_actual_cost(ctx),
            replan_used=replan_used,
        ),
        finished_at=datetime.now(UTC),
    )


def _actual_cost(ctx: RunContext | None) -> float | None:
    if ctx is None:
        return None
    ledger = ctx.guard.ledger
    return None if ledger.unknown_cost else round(ledger.committed_usd, 6)


def run_research(
    ctx: RunContext,
    request: ResearchRequest,
    *,
    run_id: str,
    now: datetime | None = None,
    progress: Progress | None = None,
    demo: bool = False,
) -> ResearchResult:
    started = time.monotonic()
    state = _State()
    check = validate_topic(request.topic)
    described = describe_warnings(check.warnings)
    if not check.ok:
        code = (
            (check.error or ErrorCode.INPUT_INVALID).value
            if hasattr(check.error, "value")
            else str(check.error)
        )
        return _failure(
            request, run_id, code or ErrorCode.INPUT_INVALID.value, started, None, described
        )
    try:
        return _run(
            ctx,
            request,
            check.topic,
            list(described),
            run_id,
            now or datetime.now(UTC),
            progress or (lambda stage, frac: None),
            demo,
            started,
            state,
        )
    except PipelineFailure as err:
        return _failure(
            request,
            run_id,
            err.code.value,
            started,
            ctx,
            described,
            replan_used=state.replan_used,
            detail=err.detail,
        )
    except BudgetStop:
        return _failure(
            request,
            run_id,
            ErrorCode.BUDGET_STOP.value,
            started,
            ctx,
            described,
            replan_used=state.replan_used,
        )
    except DeadlineExceeded:
        return _failure(
            request,
            run_id,
            ErrorCode.TIMEOUT.value,
            started,
            ctx,
            described,
            replan_used=state.replan_used,
        )
    except RunCancelled:
        return _failure(
            request,
            run_id,
            ErrorCode.ABANDONED.value,
            started,
            ctx,
            described,
            replan_used=state.replan_used,
        )


class _State:
    def __init__(self) -> None:
        self.replan_used = False


def _search_all(ctx: RunContext, queries: Sequence[str]) -> list[list[RawResult]]:
    queries = list(queries)[: ctx.cfg.search_query_cap]

    def one(query: str) -> list[RawResult] | ProviderError:
        try:
            return ctx.search_call(
                query, max_results=RESULTS_PER_QUERY, want_extracted=True
            ).results
        except ProviderError as err:
            return err

    with ThreadPoolExecutor(max_workers=min(SEARCH_PARALLEL, len(queries))) as pool:
        outcomes = list(pool.map(_guarded(one), queries))
    good = [o for o in outcomes if isinstance(o, list)]
    if not good:
        raise PipelineFailure(ErrorCode.SEARCH_FAILED)
    return good


def _guarded(
    fn: Callable[[str], list[RawResult] | ProviderError],
) -> Callable[[str], list[RawResult] | ProviderError]:
    return (
        fn  # BudgetStop, DeadlineExceeded and RunCancelled intentionally propagate out of the pool
    )


def _apply_checks(
    claims: list[ClaimRecord], sources: Mapping[int, SourceRecord], max_quotes: int
) -> None:
    for claim in claims:
        result = check_claim(claim, sources, max_quotes)
        claim.quote_match_ok = result.quote_match_ok
        claim.numeric_guard_ok = result.numeric_guard_ok
        claim.reject_reason = None if result.ok else result.reason


def _verify(
    ctx: RunContext,
    claims: list[ClaimRecord],
    sources: Mapping[int, SourceRecord],
    cache: VerifierCache,
    reservation_stage: str | None = None,
) -> None:
    passing = [c for c in claims if c.reject_reason is None]
    verdicts = verify_claims(
        ctx, passing, sources, cache=cache, reservation_stage=reservation_stage
    )
    for claim in passing:
        verdict, reason = verdicts[claim.claim_id]
        claim.support_verdict = verdict
        claim.support_reason = reason
        if verdict is not Verdict.SUPPORTED:
            claim.reject_reason = f"VERIFIER_{verdict.value.upper()}"


def _run(
    ctx: RunContext,
    request: ResearchRequest,
    topic: str,
    warnings: list[str],
    run_id: str,
    now: datetime,
    progress: Progress,
    demo: bool,
    started: float,
    state: _State,
) -> ResearchResult:
    cfg = ctx.cfg

    def stage(name: str) -> None:
        ctx.guard.check()
        progress(name, _STAGE_FRACTION[name])

    stage("planning")
    outcome = make_plan(ctx, topic)
    plan, state.replan_used = outcome.plan, outcome.replan_used

    stage("searching")
    results_by_query = _search_all(ctx, plan.queries)

    stage("reading")
    registry = build_registry(
        results_by_query,
        plan.queries,
        topic,
        cfg,
        now,
        time_sensitive=is_time_sensitive(topic),
        chars_per_token=ctx.chars_per_token,
    )
    usable = [
        s
        for s in registry.sources
        if s.evidence_mode is not EvidenceMode.METADATA_ONLY and s.passages
    ]
    if not usable:
        raise PipelineFailure(ErrorCode.NO_EVIDENCE)
    sources = {s.citation_id: s for s in registry.sources}

    stage("drafting")
    draft = draft_ledger(ctx, plan, registry.sources)
    ledger = normalize_draft(draft, plan, cfg)
    claims = ledger.claims

    stage("verifying")
    cache = VerifierCache()
    _apply_checks(claims, sources, cfg.max_quotes_per_claim)
    _verify(ctx, claims, sources, cache)

    timed_out = budget_stopped = repair_used = False

    def counts() -> object:
        return compute_counts(
            claims, sources, plan.facets, timed_out=timed_out, budget_stopped=budget_stopped
        )

    status, _ = evaluate(counts(), cfg)  # type: ignore[arg-type]
    failed = [c for c in claims if c.support_verdict is not Verdict.SUPPORTED]
    if status is not RunStatus.COMPLETED and failed:
        repair_used = True
        stage("repairing")
        try:
            failure_reasons = {c.claim_id: c.reject_reason or "FAILED" for c in failed}
            repaired = repair_claims(ctx, plan, failed, failure_reasons, sources)
            if repaired:
                _apply_checks(repaired, sources, cfg.max_quotes_per_claim)
                _verify(ctx, repaired, sources, cache, reservation_stage="repair_verify")
                by_id = {c.claim_id: c for c in repaired}
                claims[:] = [
                    by_id.get(c.claim_id, c) if by_id.get(c.claim_id) else c for c in claims
                ]
        except BudgetStop:
            budget_stopped = True
        except DeadlineExceeded:
            timed_out = True
        except PipelineFailure:
            pass  # repair is optional: keep the first-pass result

    supported = {c.claim_id: c for c in claims if c.support_verdict is Verdict.SUPPORTED}

    # Scan non-claim sentences once, over the final claim set. A scan that cannot run drops them.
    non_claim: list[tuple[str, str]] = [
        (sentence_ref(name, i), s.text or "")
        for name in SECTION_ORDER
        for i, s in enumerate(ledger.sections.get(name, []))
        if s.type != "claim"
    ]
    flagged: set[str]
    try:
        stage("finishing")
        flagged = scan_sentences(ctx, non_claim)
    except BudgetStop:
        flagged, budget_stopped = {ref for ref, _ in non_claim}, True
    except DeadlineExceeded:
        flagged, timed_out = {ref for ref, _ in non_claim}, True
    except PipelineFailure:
        flagged = {ref for ref, _ in non_claim}
        warnings.append("Some connecting text was removed because it could not be checked.")

    final_counts = compute_counts(
        claims, sources, plan.facets, timed_out=timed_out, budget_stopped=budget_stopped
    )
    status, reasons = evaluate(final_counts, cfg)
    if status is RunStatus.FAILED:
        return _failure(
            request, run_id, reasons[0], started, ctx, warnings, reasons, state.replan_used
        )

    section_map: dict[SectionName, list[DraftSentence]] = {
        n: list(v) for n, v in ledger.sections.items()
    }
    sections = assemble_sections(section_map, supported, topic=topic, flagged=flagged)
    displayed_ids = [
        i.claim_id for s in sections for i in s.items if i.kind == "claim" and i.claim_id
    ]
    cited = sorted({cid for s in sections for i in s.items for cid in i.citation_ids})
    coverage = [
        FacetCoverage(
            facet_id=f.facet_id,
            question=f.question,
            category=f.category,
            supported_claims=sum(
                1 for cid in displayed_ids if supported[cid].facet_id == f.facet_id
            ),
        )
        for f in plan.facets
    ]
    if any(
        s.evidence_mode is EvidenceMode.SNIPPET for s in registry.sources if s.citation_id in cited
    ):
        warnings.append("Some sources were read only as search-result snippets, not full pages.")
    if registry.not_inspected:
        warnings.append(f"{len(registry.not_inspected)} found source(s) could not be inspected.")

    researched_on = now.date().isoformat()
    markdown = render_markdown(
        topic=topic,
        mode_label="Quick" if request.depth is Mode.QUICK else "Deep",
        status=status,
        reasons=reasons,
        researched_on=researched_on,
        sections=sections,
        claims=supported,
        sources=sources,
        not_inspected=registry.not_inspected,
        coverage=coverage,
        warnings=warnings,
        demo=demo,
    )
    covered = {f.facet_id for f in coverage if f.supported_claims}
    metrics = RunMetrics(
        query_count=len(results_by_query),
        usable_sources=len(usable),
        unique_domains=final_counts.domains,
        supported_claims=final_counts.supported_claims,
        supported_facets=len(covered),
        planned_facets=len(plan.facets),
        snippet_only_claim_share=round(final_counts.snippet_only_share, 4),
        elapsed_ms=int((time.monotonic() - started) * 1000),
        modeled_spend_ceiling_usd=cfg.cost_cap_usd,
        estimated_actual_cost_usd=_actual_cost(ctx),
        drafted_claims=len(draft.claims),
        removed_claims=len(claims) - len(supported) + len(ledger.rejected),
        dropped_passages=registry.stats.dropped_passages,
        replan_used=state.replan_used,
        repair_used=repair_used,
    )
    unused = [s.citation_id for s in registry.sources if s.citation_id not in cited]
    return ResearchResult(
        run_id=run_id,
        mode=request.depth,
        status=status,
        reason_codes=reasons,
        researched_on=researched_on,
        report_markdown=markdown,
        sections=sections,
        facet_coverage=coverage,
        claims=claims,
        sources=registry.sources,
        unused_source_ids=unused,
        source_ids=cited,
        validated_claim_ids=displayed_ids,
        warnings=warnings,
        metrics=metrics,
        finished_at=datetime.now(UTC),
    )


__all__ = ["STAGES", "NotInspected", "is_time_sensitive", "run_research"]
