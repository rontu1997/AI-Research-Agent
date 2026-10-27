from __future__ import annotations

import pytest

from adapters.fakes import FakeLLM
from core.capacity import check_call_graph
from core.errors import ErrorCode, PipelineFailure, ProviderServerError
from core.models import (
    ClaimRecord,
    EvidenceMode,
    EvidenceRef,
    Mode,
    Passage,
    SourceRecord,
    Verdict,
    VerifierItem,
    VerifierOutput,
)
from core.settings import mode_config
from pipeline.verifier import VerifierCache, build_batches, verify_claims
from tests.pipeline.conftest import SHEET

PASSAGE = (
    "The pilot launched in March 2024 with 120 bikes at 15 docking stations in the harbor district."
)


def _source(cid: int = 1, text: str = PASSAGE) -> SourceRecord:
    return SourceRecord(
        citation_id=cid,
        title=f"Source {cid}",
        url=f"https://s{cid}.example.org/a",
        canonical_url=f"https://s{cid}.example.org/a",
        registrable_domain=f"s{cid}.example.org",
        retrieved_at="2025-01-01T00:00:00Z",
        evidence_mode=EvidenceMode.EXTRACTED,
        passages=[Passage(passage_id=f"{cid}.1", text=text)],
        evidence_group_id=f"g{cid}",
    )


def _claim(cid: str, text: str = PASSAGE, quote: str = PASSAGE, citation: int = 1) -> ClaimRecord:
    return ClaimRecord(
        claim_id=cid,
        text=text,
        facet_id="f1",
        section="findings",
        evidence=[EvidenceRef(citation_id=citation, passage_id=f"{citation}.1", quote=quote)],
        quote_match_ok=True,
        numeric_guard_ok=True,
    )


def test_batches_respect_size_and_token_caps_and_keep_order() -> None:
    cfg = mode_config(Mode.QUICK)
    big = "x" * 1500
    src = {1: _source(1, big)}
    claims = [_claim(f"c{i}", quote="x" * 280) for i in range(1, 15)]
    batches = build_batches(claims, src, cfg)
    assert [c.claim_id for b in batches for c in b] == [c.claim_id for c in claims]
    assert all(len(b) <= cfg.verifier_batch_size for b in batches)


def test_worst_case_batch_count_matches_the_startup_check() -> None:
    for mode in Mode:
        cfg = mode_config(mode)
        big = "x" * 1500
        src = {i: _source(i, big) for i in range(1, cfg.max_quotes_per_claim + 1)}
        claims = []
        for n in range(cfg.max_claims):
            c = _claim(f"c{n}", quote="x" * 300)
            c.evidence = [
                EvidenceRef(citation_id=i, passage_id=f"{i}.1", quote="x" * 300)
                for i in range(1, cfg.max_quotes_per_claim + 1)
            ]
            claims.append(c)
        report = check_call_graph(cfg, SHEET, "fake-writer", "fake-verifier")
        assert len(build_batches(claims, src, cfg)) <= report.verifier_batches


def test_verbatim_claim_is_supported_and_altered_claim_is_not(make_ctx) -> None:
    ctx = make_ctx()
    good = _claim("c1")
    off = _claim("c2", text="The pilot was cancelled in 2024 amid a funding scandal.")
    verdicts = verify_claims(ctx, [good, off], {1: _source()})
    assert verdicts["c1"][0] is Verdict.SUPPORTED
    assert verdicts["c2"][0] is Verdict.UNSUPPORTED


def test_missing_verdict_fails_closed_and_unknown_ids_are_ignored(make_ctx) -> None:
    verifier = FakeLLM("fake-verifier")
    verifier.set_handler(
        VerifierOutput,
        lambda ctx: VerifierOutput(
            results=[
                VerifierItem(claim_id="c1", verdict=Verdict.SUPPORTED),
                VerifierItem(claim_id="ghost", verdict=Verdict.SUPPORTED),
            ]
        ),
    )
    ctx = make_ctx(verifier=verifier)
    verdicts = verify_claims(ctx, [_claim("c1"), _claim("c2")], {1: _source()})
    assert verdicts["c1"][0] is Verdict.SUPPORTED
    assert verdicts["c2"][0] is Verdict.UNSUPPORTED
    assert "ghost" not in verdicts


def test_conflicting_duplicate_verdicts_take_the_weaker_one(make_ctx) -> None:
    verifier = FakeLLM("fake-verifier")
    verifier.set_handler(
        VerifierOutput,
        lambda ctx: VerifierOutput(
            results=[
                VerifierItem(claim_id="c1", verdict=Verdict.SUPPORTED),
                VerifierItem(claim_id="c1", verdict=Verdict.UNCERTAIN),
            ]
        ),
    )
    ctx = make_ctx(verifier=verifier)
    assert verify_claims(ctx, [_claim("c1")], {1: _source()})["c1"][0] is Verdict.UNCERTAIN


def test_verifier_outage_is_a_fail_closed_pipeline_failure(make_ctx) -> None:
    verifier = FakeLLM("fake-verifier")

    def boom(ctx):  # noqa: ANN001
        raise ProviderServerError("down")

    verifier.set_handler(VerifierOutput, boom)
    ctx = make_ctx(verifier=verifier)
    with pytest.raises(PipelineFailure) as err:
        verify_claims(ctx, [_claim("c1")], {1: _source()})
    assert err.value.code is ErrorCode.VERIFIER_FAILED


def test_cache_prevents_a_second_call_for_identical_claims(make_ctx) -> None:
    verifier = FakeLLM("fake-verifier")
    ctx = make_ctx(verifier=verifier)
    cache = VerifierCache()
    verify_claims(ctx, [_claim("c1")], {1: _source()}, cache=cache)
    calls = len(verifier.calls)
    verify_claims(ctx, [_claim("c1")], {1: _source()}, cache=cache)
    assert len(verifier.calls) == calls


def test_verifier_sees_only_claim_quotes_and_passages(make_ctx) -> None:
    verifier = FakeLLM("fake-verifier")
    ctx = make_ctx(verifier=verifier)
    verify_claims(ctx, [_claim("c1")], {1: _source()})
    record = verifier.calls[0]
    assert record.block_labels == ("claims",)
    assert "untrusted" in record.system.lower()


def test_repair_reverification_draws_on_the_pool_not_the_verifier_base(make_ctx) -> None:
    ctx = make_ctx()
    ledger = ctx.guard.ledger
    base_before = ledger.base_remaining["verifier"]
    pool_before = ledger.pool_remaining
    verify_claims(ctx, [_claim("c1")], {1: _source()}, reservation_stage="repair_verify")
    assert ledger.base_remaining["verifier"] == base_before
    assert ledger.pool_remaining < pool_before
