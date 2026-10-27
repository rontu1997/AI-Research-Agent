from __future__ import annotations

import pytest

from adapters.fakes import FakeLLM
from core.errors import ErrorCode, PipelineFailure, ProviderServerError
from core.models import (
    ClaimRecord,
    DraftClaim,
    EvidenceMode,
    EvidenceRef,
    Facet,
    FacetCategory,
    LedgerDraft,
    Passage,
    Plan,
    ScanItem,
    ScanOutput,
    SourceRecord,
)
from pipeline.repair import repair_claims
from pipeline.scan import scan_sentences
from pipeline.writer import draft_ledger

PASSAGE = (
    "The pilot launched in March 2024 with 120 bikes at 15 docking stations in the harbor district."
)
PLAN = Plan(
    queries=["a b", "c d"],
    facets=[Facet(facet_id="f1", question="What is it?", category=FacetCategory.BACKGROUND)],
)


def _source(
    cid: int, mode: EvidenceMode = EvidenceMode.EXTRACTED, text: str = PASSAGE
) -> SourceRecord:
    passages = (
        [] if mode is EvidenceMode.METADATA_ONLY else [Passage(passage_id=f"{cid}:p1", text=text)]
    )
    return SourceRecord(
        citation_id=cid,
        title=f"Source {cid}",
        url=f"https://s{cid}.example.org/a",
        canonical_url=f"https://s{cid}.example.org/a",
        registrable_domain=f"s{cid}.example.org",
        retrieved_at="2025-01-01T00:00:00Z",
        evidence_mode=mode,
        passages=passages,
        evidence_group_id=f"g{cid}",
    )


def _record(cid: str, quote: str = PASSAGE, text: str = PASSAGE) -> ClaimRecord:
    return ClaimRecord(
        claim_id=cid,
        text=text,
        facet_id="f1",
        section="findings",
        evidence=[EvidenceRef(citation_id=1, passage_id="1:p1", quote=quote)],
    )


# --- writer ------------------------------------------------------------------------------------


def test_writer_gets_plan_passages_and_limits_but_not_metadata_only_sources(make_ctx) -> None:
    writer = FakeLLM("fake-writer")
    ctx = make_ctx(writer=writer)
    draft = draft_ledger(ctx, PLAN, [_source(1), _source(2, EvidenceMode.METADATA_ONLY)])
    assert isinstance(draft, LedgerDraft)
    record = writer.calls[0]
    assert record.block_labels == ("plan", "passages", "limits")
    assert "2:p1" not in str(record)


def test_writer_failure_is_a_model_failed_pipeline_failure(make_ctx) -> None:
    writer = FakeLLM("fake-writer")

    def boom(ctx):  # noqa: ANN001
        raise ProviderServerError("down")

    writer.set_handler(LedgerDraft, boom)
    ctx = make_ctx(writer=writer)
    with pytest.raises(PipelineFailure) as err:
        draft_ledger(ctx, PLAN, [_source(1)])
    assert err.value.code is ErrorCode.MODEL_FAILED


# --- scan --------------------------------------------------------------------------------------


def test_scan_flags_material_facts_and_fails_closed_on_missing_results(make_ctx) -> None:
    scanner = FakeLLM("fake-verifier")
    scanner.set_handler(
        ScanOutput,
        lambda c: ScanOutput(results=[ScanItem(sentence_ref="s1", contains_material_fact=False)]),
    )
    ctx = make_ctx(verifier=scanner)
    flagged = scan_sentences(
        ctx, [("s1", "Interpretation: a calm remark."), ("s2", "Another remark.")]
    )
    assert flagged == {"s2"}


def test_scan_default_fake_flags_numbers(make_ctx) -> None:
    ctx = make_ctx()
    flagged = scan_sentences(ctx, [("s1", "It grew 40 percent."), ("s2", "Next, the detail.")])
    assert flagged == {"s1"}


def test_scan_with_nothing_to_scan_makes_no_call(make_ctx) -> None:
    scanner = FakeLLM("fake-verifier")
    ctx = make_ctx(verifier=scanner)
    assert scan_sentences(ctx, []) == set()
    assert scanner.calls == []


# --- repair ------------------------------------------------------------------------------------


def _repair_handler(replacements: list[DraftClaim]):
    return lambda c: LedgerDraft(claims=replacements, sections=[])


def test_repair_replaces_only_failed_claims_and_ignores_new_ids(make_ctx) -> None:
    writer = FakeLLM("fake-writer")
    fixed = DraftClaim(
        claim_id="c1",
        text=PASSAGE,
        facet_id="f1",
        section="findings",
        evidence=[EvidenceRef(citation_id=1, passage_id="1:p1", quote=PASSAGE)],
    )
    invented = fixed.model_copy(update={"claim_id": "c99"})
    writer.set_handler(LedgerDraft, _repair_handler([fixed, invented]))
    ctx = make_ctx(writer=writer)
    failed = [_record("c1", text="The pilot launched in 1999.")]
    out = repair_claims(ctx, PLAN, failed, {"c1": "NUMERIC_MISMATCH"}, {1: _source(1)})
    assert [c.claim_id for c in out] == ["c1"]
    assert out[0].text == PASSAGE


def test_repair_is_limited_to_the_mode_cap_in_drafted_order(make_ctx) -> None:
    writer = FakeLLM("fake-writer")
    seen: list[int] = []

    def handler(c):  # noqa: ANN001
        import json

        seen.append(len(json.loads(c.blocks["failed_claims"])))
        return LedgerDraft(claims=[], sections=[])

    writer.set_handler(LedgerDraft, handler)
    ctx = make_ctx(writer=writer)
    failed = [_record(f"c{i}") for i in range(1, 11)]
    repair_claims(ctx, PLAN, failed, {c.claim_id: "X" for c in failed}, {1: _source(1)})
    assert seen == [ctx.cfg.repair_max_claims]


def test_repair_with_nothing_failed_makes_no_call(make_ctx) -> None:
    writer = FakeLLM("fake-writer")
    ctx = make_ctx(writer=writer)
    assert repair_claims(ctx, PLAN, [], {}, {1: _source(1)}) == []
    assert writer.calls == []


def test_repair_cannot_cite_a_source_the_failed_claim_did_not_cite(make_ctx) -> None:
    writer = FakeLLM("fake-writer")
    wandering = DraftClaim(
        claim_id="c1",
        text=PASSAGE,
        facet_id="f1",
        section="findings",
        evidence=[EvidenceRef(citation_id=2, passage_id="2:p1", quote=PASSAGE)],
    )
    writer.set_handler(LedgerDraft, _repair_handler([wandering]))
    ctx = make_ctx(writer=writer)
    out = repair_claims(
        ctx, PLAN, [_record("c1", text="bad")], {"c1": "X"}, {1: _source(1), 2: _source(2)}
    )
    assert out == []
