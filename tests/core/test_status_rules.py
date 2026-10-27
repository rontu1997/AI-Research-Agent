import dataclasses

import pytest

from core.models import (
    ClaimRecord,
    EvidenceMode,
    EvidenceRef,
    Facet,
    FacetCategory,
    Mode,
    Passage,
    RunStatus,
    SourceRecord,
    Verdict,
)
from core.settings import mode_config
from core.status_rules import RunCounts, compute_counts, evaluate


def _counts(mode: Mode, **over: object) -> RunCounts:
    cfg = mode_config(mode)
    base = dict(
        fatal_error=None,
        supported_claims=cfg.min_claims,
        usable_groups=cfg.min_groups,
        domains=cfg.min_domains,
        supported_facets=cfg.min_facets,
        snippet_only_share=cfg.max_snippet_share,
        timed_out=False,
        budget_stopped=False,
    )
    base.update(over)
    return RunCounts(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", [Mode.QUICK, Mode.DEEP])
def test_exactly_at_every_threshold_is_completed(mode: Mode) -> None:
    status, reasons = evaluate(_counts(mode), mode_config(mode))
    assert status is RunStatus.COMPLETED
    assert reasons == []


@pytest.mark.parametrize("mode", [Mode.QUICK, Mode.DEEP])
@pytest.mark.parametrize(
    ("field", "delta", "code"),
    [
        ("usable_groups", -1, "LOW_EVIDENCE_GROUPS"),
        ("domains", -1, "LOW_DOMAINS"),
        ("supported_claims", -1, "INSUFFICIENT_CLAIMS"),
        ("supported_facets", -1, "INCOMPLETE_FACETS"),
    ],
)
def test_one_below_a_threshold_is_partial_with_its_reason(
    mode: Mode, field: str, delta: int, code: str
) -> None:
    cfg = mode_config(mode)
    counts = _counts(mode)
    counts = dataclasses.replace(counts, **{field: getattr(counts, field) + delta})
    status, reasons = evaluate(counts, cfg)
    assert status is RunStatus.PARTIAL
    assert reasons == [code]


@pytest.mark.parametrize("mode", [Mode.QUICK, Mode.DEEP])
def test_one_above_a_threshold_stays_completed(mode: Mode) -> None:
    cfg = mode_config(mode)
    counts = _counts(
        mode,
        usable_groups=cfg.min_groups + 1,
        domains=cfg.min_domains + 1,
        supported_claims=cfg.min_claims + 1,
        supported_facets=cfg.min_facets + 1,
    )
    assert evaluate(counts, cfg)[0] is RunStatus.COMPLETED


@pytest.mark.parametrize("mode", [Mode.QUICK, Mode.DEEP])
def test_snippet_share_boundary(mode: Mode) -> None:
    cfg = mode_config(mode)
    just_over = cfg.max_snippet_share + 0.01
    status, reasons = evaluate(_counts(mode, snippet_only_share=just_over), cfg)
    assert status is RunStatus.PARTIAL
    assert reasons == ["SNIPPET_HEAVY"]


def test_all_snippet_but_otherwise_rich_run_is_partial() -> None:
    cfg = mode_config(Mode.QUICK)
    counts = _counts(
        Mode.QUICK, supported_claims=12, usable_groups=8, domains=6, snippet_only_share=1.0
    )
    assert evaluate(counts, cfg) == (RunStatus.PARTIAL, ["SNIPPET_HEAVY"])


def test_timeout_and_budget_stop_prevent_completed() -> None:
    cfg = mode_config(Mode.QUICK)
    assert evaluate(_counts(Mode.QUICK, timed_out=True), cfg) == (RunStatus.PARTIAL, ["TIMEOUT"])
    assert evaluate(_counts(Mode.QUICK, budget_stopped=True), cfg) == (
        RunStatus.PARTIAL,
        ["BUDGET_STOP"],
    )


def test_every_unmet_threshold_is_listed() -> None:
    cfg = mode_config(Mode.DEEP)
    counts = _counts(
        Mode.DEEP,
        usable_groups=1,
        domains=1,
        supported_claims=2,
        supported_facets=1,
        snippet_only_share=1.0,
    )
    status, reasons = evaluate(counts, cfg)
    assert status is RunStatus.PARTIAL
    assert reasons == [
        "LOW_EVIDENCE_GROUPS",
        "LOW_DOMAINS",
        "INSUFFICIENT_CLAIMS",
        "INCOMPLETE_FACETS",
        "SNIPPET_HEAVY",
    ]


def test_fewer_than_two_supported_claims_is_failed() -> None:
    cfg = mode_config(Mode.QUICK)
    assert evaluate(_counts(Mode.QUICK, supported_claims=1), cfg) == (
        RunStatus.FAILED,
        ["INSUFFICIENT_CLAIMS"],
    )
    assert (
        evaluate(_counts(Mode.QUICK, supported_claims=0, snippet_only_share=0.0), cfg)[0]
        is RunStatus.FAILED
    )


def test_two_claims_with_no_usable_group_is_failed() -> None:
    cfg = mode_config(Mode.QUICK)
    assert (
        evaluate(_counts(Mode.QUICK, supported_claims=2, usable_groups=0), cfg)[0]
        is RunStatus.FAILED
    )


def test_two_safe_claims_is_the_minimum_partial() -> None:
    cfg = mode_config(Mode.DEEP)
    counts = _counts(Mode.DEEP, supported_claims=2, usable_groups=1, domains=1, supported_facets=1)
    assert evaluate(counts, cfg)[0] is RunStatus.PARTIAL


def test_a_fatal_error_is_failed_with_its_code() -> None:
    cfg = mode_config(Mode.QUICK)
    assert evaluate(_counts(Mode.QUICK, fatal_error="NO_EVIDENCE"), cfg) == (
        RunStatus.FAILED,
        ["NO_EVIDENCE"],
    )


# --- compute_counts -----------------------------------------------------------------------------


def _src(cid: int, domain: str, mode: EvidenceMode, group: str | None = None) -> SourceRecord:
    return SourceRecord(
        citation_id=cid,
        title="T",
        url=f"https://{domain}/{cid}",
        canonical_url=f"https://{domain}/{cid}",
        registrable_domain=domain,
        retrieved_at="2026-10-21T00:00:00Z",
        evidence_mode=mode,
        passages=[Passage(passage_id=f"{cid}:p1", text="x" * 40)],
        evidence_group_id=group or f"g{cid}",
    )


def _claim(
    cid: str, facet: str, cites: list[int], verdict: Verdict | None = Verdict.SUPPORTED
) -> ClaimRecord:
    return ClaimRecord(
        claim_id=cid,
        text="t",
        facet_id=facet,
        section="findings",
        evidence=[EvidenceRef(citation_id=c, passage_id=f"{c}:p1", quote="q" * 30) for c in cites],
        support_verdict=verdict,
    )


FACETS = [
    Facet(facet_id="f1", question="a", category=FacetCategory.BACKGROUND),
    Facet(facet_id="f2", question="b", category=FacetCategory.IMPACTS_RISKS),
    Facet(facet_id="f3", question="c", category=FacetCategory.CURRENT_STATE),
]


def test_compute_counts_uses_distinct_supported_claims_only() -> None:
    sources = {
        1: _src(1, "a.org", EvidenceMode.EXTRACTED),
        2: _src(2, "b.org", EvidenceMode.SNIPPET),
    }
    claims = [
        _claim("c1", "f1", [1]),
        _claim("c2", "f1", [2]),
        _claim("c3", "f2", [2], verdict=Verdict.UNSUPPORTED),
    ]
    counts = compute_counts(claims, sources, FACETS)
    assert counts.supported_claims == 2
    assert counts.supported_facets == 1
    assert counts.domains == 2
    assert counts.usable_groups == 2


def test_snippet_only_share_counts_claims_whose_evidence_is_all_snippet() -> None:
    sources = {
        1: _src(1, "a.org", EvidenceMode.EXTRACTED),
        2: _src(2, "b.org", EvidenceMode.SNIPPET),
    }
    claims = [
        _claim("c1", "f1", [2]),  # snippet only
        _claim("c2", "f1", [1]),  # extracted
        _claim("c3", "f2", [1, 2]),  # mixed counts as not snippet-only
        _claim("c4", "f2", [2]),  # snippet only
    ]
    assert compute_counts(claims, sources, FACETS).snippet_only_share == pytest.approx(0.5)


def test_snippet_share_is_zero_when_there_are_no_supported_claims() -> None:
    assert compute_counts([], {}, FACETS).snippet_only_share == 0.0


def test_syndicated_group_counts_once_and_unknown_facets_do_not_count() -> None:
    sources = {
        1: _src(1, "a.org", EvidenceMode.EXTRACTED, group="same"),
        2: _src(2, "b.org", EvidenceMode.EXTRACTED, group="same"),
    }
    claims = [_claim("c1", "f1", [1]), _claim("c2", "zzz", [2])]
    counts = compute_counts(claims, sources, FACETS)
    assert counts.usable_groups == 1
    assert counts.supported_facets == 1
