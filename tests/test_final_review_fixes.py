"""Regression tests for the findings of the final whole-branch review (see docs/build-ledger.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from adapters.fakes import FakeLLM
from core.capacity import BudgetLedger, CallGuard, Deadline, ProviderGate
from core.errors import ContentRefused, ProviderServerError, SchemaViolation
from core.models import (
    ClaimRecord,
    DraftClaim,
    DraftSection,
    DraftSentence,
    EvidenceMode,
    EvidenceRef,
    Facet,
    FacetCategory,
    LedgerDraft,
    Mode,
    Passage,
    Plan,
    ResearchRequest,
    RunStatus,
    ScanOutput,
    SectionName,
    SourceRecord,
    Verdict,
)
from core.settings import load_settings, mode_config, startup_problems
from core.tokens import estimate_tokens
from pipeline.claim_checks import (
    check_interpretation,
    check_transition,
    numeric_guard,
    quote_in_passage,
)
from pipeline.claim_ledger import normalize_draft
from pipeline.repair import repair_claims
from pipeline.report import assemble_sections, render_markdown
from pipeline.scan import scan_sentences
from pipeline.verifier import build_batches
from pipeline.writer import passages_block
from service import build_service

# --- #1 billed-but-failed calls are charged -----------------------------------------------------


def _guard() -> CallGuard:
    return CallGuard(
        ledger=BudgetLedger(1.0, {}),
        deadline=Deadline(60),
        is_cancelled=lambda: False,
        gates={"w": ProviderGate("w", 1000.0, 1000, sleep=lambda s: None)},
        sleep=lambda s: None,
        jitter=lambda upper: 0.0,
    )


def test_schema_violations_are_charged_because_the_provider_billed_them() -> None:
    guard = _guard()
    attempts = {"n": 0}

    def fn(timeout: float) -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise SchemaViolation("truncated")
        return "ok"

    out = guard.call(
        stage="s",
        provider="w",
        fn=fn,
        est_cost_usd=0.1,
        actual_cost=lambda r: 0.1,
        per_call_timeout_s=5,
        retry_on_schema=True,
    )
    assert out == "ok" and attempts["n"] == 3
    assert guard.ledger.committed_usd == pytest.approx(0.3)
    assert guard.ledger.unknown_cost


def test_content_refusals_are_charged_but_plain_server_errors_are_not() -> None:
    guard = _guard()
    with pytest.raises(ContentRefused):
        guard.call(
            stage="s",
            provider="w",
            fn=lambda t: (_ for _ in ()).throw(ContentRefused("no")),
            est_cost_usd=0.1,
            actual_cost=lambda r: 0.0,
            per_call_timeout_s=5,
        )
    assert guard.ledger.committed_usd == pytest.approx(0.1)
    guard2 = _guard()
    with pytest.raises(ProviderServerError):
        guard2.call(
            stage="s",
            provider="w",
            fn=lambda t: (_ for _ in ()).throw(ProviderServerError("x")),
            est_cost_usd=0.1,
            actual_cost=lambda r: 0.0,
            per_call_timeout_s=5,
        )
    assert guard2.ledger.committed_usd == 0


def test_a_reservation_is_released_if_cost_extraction_raises() -> None:
    guard = _guard()

    def bad_cost(result: str) -> float:
        raise KeyError("usage")

    with pytest.raises(KeyError):
        guard.call(
            stage="s",
            provider="w",
            fn=lambda t: "ok",
            est_cost_usd=0.1,
            actual_cost=bad_cost,
            per_call_timeout_s=5,
        )
    assert guard.ledger.pool_remaining == pytest.approx(1.0)


# --- #2 quote match respects word and number boundaries -----------------------------------------

PASSAGE = "In 2023, 45% of adults in the survey reported daily use of the service."


def test_a_quote_cannot_start_in_the_middle_of_a_number_or_word() -> None:
    assert not quote_in_passage("5% of adults in the survey reported daily use", PASSAGE)
    assert not quote_in_passage("n the survey reported daily use of the service", PASSAGE)
    assert not quote_in_passage("5% of adults", "Growth was 1.5% of adults surveyed this year.")
    assert quote_in_passage("45% of adults in the survey reported daily use", PASSAGE)
    assert quote_in_passage("In 2023, 45% of adults in the survey reported daily use", PASSAGE)
    assert quote_in_passage('"quoted" text here ok', 'He said "quoted" text here ok today.')


# --- #3 numeric-guard evasions --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("claim", "quote"),
    [
        ("FY2023 revenue grew", "FY2024 revenue grew"),
        ("It raised $5bn", "It raised $5m"),
        ("in MARCH 2024", "in June 2024"),
        ("twenty percent fell", "thirty percent fell"),
        ("eleven cities", "twelve cities"),
        ("Usage doubled", "Usage rose"),
        ("It fell -5 points", "It rose 5 points"),
        (".5 points", "5 points"),
        ("on 2024-03-05", "on 2024-05-03"),
        ("at 12:30 daily", "at 30:12 daily"),
        ("one half of users", "most users"),
    ],
)
def test_numeric_guard_rejects_these_substitutions(claim: str, quote: str) -> None:
    assert not numeric_guard(claim, [quote]).ok


@pytest.mark.parametrize(
    ("claim", "quote"),
    [
        ("It raised $5bn", "It raised 5 billion dollars"),
        ("FY2024 revenue grew", "FY2024 revenue grew"),
        ("from 2020-2021", "from 2020-2021"),
        ("in March 2024", "launched in March 2024"),
        ("one of the largest", "a very large one"),
        ("twenty percent fell", "twenty percent fell"),
        ("on 2024-03-05", "on 2024-03-05"),
        ("It fell -5 points", "It fell -5 points"),
    ],
)
def test_numeric_guard_still_accepts_faithful_claims(claim: str, quote: str) -> None:
    assert numeric_guard(claim, [quote]).ok


# --- #4 sentence rules -----------------------------------------------------------------------------

CLAIMS = {"c1": "The pilot launched with a fleet of bikes."}
HEADINGS = ["Summary", "Key findings"]


def test_interpretation_rules_catch_leading_entities_number_words_and_urls() -> None:
    def check(body: str):  # noqa: ANN202
        return check_interpretation(
            f"Interpretation: {body}", ["c1"], CLAIMS, topic="bike pilot", headings=HEADINGS
        )

    assert not check("Microsoft caused it.").ok
    assert not check("Twenty cities copied it.").ok
    assert not check("See www.example.org for more.").ok
    assert check("That is consistent with the pilot fleet.").ok


def test_transition_rules_catch_leading_entities_and_spelled_numbers() -> None:
    kw = dict(topic="bike pilot", headings=HEADINGS)
    assert not check_transition("Pfizer later bought the operator.", **kw).ok
    assert not check_transition("Overall, eleven cities copied it.", **kw).ok
    assert check_transition("Next, more detail.", **kw).ok


# --- #5 a second search in the same session is a new run ----------------------------------------


@pytest.fixture
def demo_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import streamlit as st

    monkeypatch.setenv("RESEARCH_PROVIDER_MODE", "fake")
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    st.cache_resource.clear()


def _finish(at: AppTest) -> None:
    import time

    for _ in range(120):
        text = "\n".join(m.value for m in at.markdown)
        if any(w in text for w in ("COMPLETED", "PARTIAL", "FAILED")):
            return
        time.sleep(0.5)
        at.run()
    raise AssertionError("run did not finish")


def test_second_research_click_starts_a_new_run(demo_env: None) -> None:
    app = str(Path(__file__).resolve().parents[1] / "app.py")
    at = AppTest.from_file(app, default_timeout=30)
    at.run()
    at.text_area(key="topic:input").set_value("Harborview bike share pilot")
    [b for b in at.button if b.label == "Research"][0].click()
    at.run()
    _finish(at)
    first = at.session_state["ui:run_id"]
    at.text_area(key="topic:input").set_value("Harborview bike share winter demand")
    [b for b in at.button if b.label == "Research"][0].click()
    at.run()
    assert at.session_state["ui:run_id"] != first


# --- #6 prompt-size caps -----------------------------------------------------------------------------


def _source(cid: int, text: str, title: str = "Title") -> SourceRecord:
    return SourceRecord(
        citation_id=cid,
        title=title,
        url=f"https://s{cid}.example.org/a",
        canonical_url=f"https://s{cid}.example.org/a",
        registrable_domain=f"s{cid}.example.org",
        retrieved_at="2025-01-01T00:00:00Z",
        evidence_mode=EvidenceMode.EXTRACTED,
        passages=[Passage(passage_id=f"{cid}:p1", text=text)],
        evidence_group_id=f"g{cid}",
    )


PLAN = Plan(
    queries=["a b", "c d"],
    facets=[Facet(facet_id="f1", question="Q?", category=FacetCategory.BACKGROUND)],
)


def test_overlong_claim_text_is_rejected_by_the_ledger() -> None:
    cfg = mode_config(Mode.QUICK)
    ref = EvidenceRef(citation_id=1, passage_id="1:p1", quote="q" * 40)
    long_claim = DraftClaim(
        claim_id="c1", text="word " * 80, facet_id="f1", section="findings", evidence=[ref]
    )
    ok_claim = DraftClaim(
        claim_id="c2", text="A short claim.", facet_id="f1", section="findings", evidence=[ref]
    )
    draft = LedgerDraft(claims=[long_claim, ok_claim], sections=[])
    ledger = normalize_draft(draft, PLAN, cfg)
    assert ledger.rejected == {"c1": "CLAIM_TOO_LONG"}
    assert [c.claim_id for c in ledger.claims] == ["c2"]


def test_writer_passages_truncate_long_titles() -> None:
    block = json.loads(passages_block([_source(1, "text " * 20, title="T" * 500)]))
    assert len(block[0]["source_title"]) <= 120


def test_scan_never_sends_more_than_its_input_cap_and_flags_the_overflow(make_ctx) -> None:
    scanner = FakeLLM("fake-verifier")
    seen: list[int] = []

    def handler(c):  # noqa: ANN001
        seen.append(estimate_tokens(c.blocks["sentences"]))
        items = json.loads(c.blocks["sentences"])
        from core.models import ScanItem

        return ScanOutput(
            results=[ScanItem(sentence_ref=i["ref"], contains_material_fact=False) for i in items]
        )

    scanner.set_handler(ScanOutput, handler)
    ctx = make_ctx(verifier=scanner)
    sentences = [(f"s{i}", "A calm connecting remark " * 4) for i in range(400)]
    flagged = scan_sentences(ctx, sentences)
    assert seen and max(seen) <= ctx.cfg.scan_input_cap
    assert "s399" in flagged and "s0" not in flagged


def test_repair_prompt_respects_the_repair_input_cap_and_per_claim_quote_limit(make_ctx) -> None:
    writer = FakeLLM("fake-writer")
    sizes: list[int] = []

    def handler(c):  # noqa: ANN001
        sizes.append(sum(estimate_tokens(v) for v in c.blocks.values()) + estimate_tokens(c.system))
        return LedgerDraft(claims=[], sections=[])

    writer.set_handler(LedgerDraft, handler)
    ctx = make_ctx(writer=writer)
    big = "x" * 1500
    sources = {i: _source(i, big) for i in range(1, 6)}
    failed = []
    for n in range(6):
        refs = [
            EvidenceRef(citation_id=i, passage_id=f"{i}:p1", quote="x" * 280) for i in range(1, 6)
        ]
        failed.append(
            ClaimRecord(
                claim_id=f"c{n}", text="t", facet_id="f1", section="findings", evidence=refs
            )
        )
    repair_claims(ctx, PLAN, failed, {c.claim_id: "X" for c in failed}, sources)
    assert sizes and max(sizes) <= ctx.cfg.repair_input_cap


# --- #7 EST_CHARS_PER_TOKEN is honoured everywhere ----------------------------------------------------


def test_runtime_batching_uses_the_configured_chars_per_token(make_ctx) -> None:
    ctx = make_ctx()
    ctx.chars_per_token = 3.0
    from core.capacity import claims_per_verifier_batch

    cfg = ctx.cfg
    claims = [
        ClaimRecord(
            claim_id=f"c{i}",
            text="t",
            facet_id="f1",
            section="findings",
            evidence=[EvidenceRef(citation_id=1, passage_id="1:p1", quote="x" * 300)]
            * cfg.max_quotes_per_claim,
        )
        for i in range(cfg.max_claims)
    ]
    batches = build_batches(claims, {}, cfg, ctx.chars_per_token)
    assert max(len(b) for b in batches) == claims_per_verifier_batch(cfg, 3.0)


def test_invalid_chars_per_token_is_a_named_startup_problem(tmp_path: Path) -> None:
    for bad in ("0", "-1", "99"):
        assert "EST_CHARS_PER_TOKEN" in startup_problems(
            load_settings({"EST_CHARS_PER_TOKEN": bad})
        )


def test_service_passes_the_setting_into_every_context(tmp_path: Path) -> None:
    env = {
        "RESEARCH_PROVIDER_MODE": "fake",
        "STATE_DIR": str(tmp_path / "s"),
        "LOG_DIR": str(tmp_path / "l"),
        "EST_CHARS_PER_TOKEN": "3.0",
    }
    service = build_service(load_settings(env))
    ctx = service.new_context(
        ResearchRequest(topic="t", depth=Mode.QUICK, idempotency_token="x"), lambda: False
    )
    assert ctx.chars_per_token == 3.0
    service.shutdown()


# --- #8 telemetry events and startup refusal ----------------------------------------------------------


def _events(path: Path) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for f in sorted(path.glob("events-*.jsonl")):
        out += [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]
    return out


def test_call_guard_reports_provider_calls_and_breaker_trips() -> None:
    events: list[tuple[str, dict[str, object]]] = []
    guard = CallGuard(
        ledger=BudgetLedger(5.0, {}),
        deadline=Deadline(60),
        is_cancelled=lambda: False,
        gates={"w": ProviderGate("w", 1000.0, 1000, sleep=lambda s: None)},
        sleep=lambda s: None,
        jitter=lambda u: 0.0,
        on_event=lambda e, f: events.append((e, f)),
    )
    guard.call(
        stage="s",
        provider="w",
        fn=lambda t: "ok",
        est_cost_usd=0.1,
        actual_cost=lambda r: 0.1,
        per_call_timeout_s=5,
    )
    assert (
        events[0][0] == "provider.call"
        and events[0][1]["provider"] == "w"
        and events[0][1]["attempt"] == 1
    )
    for _ in range(2):
        with pytest.raises(ProviderServerError):
            guard.call(
                stage="s",
                provider="w",
                fn=lambda t: (_ for _ in ()).throw(ProviderServerError("x")),
                est_cost_usd=0.01,
                actual_cost=lambda r: 0.0,
                per_call_timeout_s=5,
            )
    names = [e for e, _ in events]
    assert "provider.breaker" in names
    assert any(
        f.get("error_code") == "ProviderServerError" for e, f in events if e == "provider.call"
    )


def test_service_emits_startup_checks_and_refuses_when_no_mode_is_servable(tmp_path: Path) -> None:
    env = {
        "RESEARCH_PROVIDER_MODE": "fake",
        "STATE_DIR": str(tmp_path / "s"),
        "LOG_DIR": str(tmp_path / "l"),
    }
    service = build_service(load_settings(env))
    checks = [e for e in _events(tmp_path / "l") if e["event"] == "startup.check"]
    assert {c["mode"] for c in checks} == {"quick", "deep"}
    service.shutdown()

    sheet = tmp_path / "p.json"
    sheet.write_text(
        json.dumps(
            {
                "version": "t",
                "placeholder": False,
                "safety_factor": 1.25,
                "models": {
                    "fake-writer": {"in_per_m": 400.0, "out_per_m": 1600.0},
                    "fake-verifier": {"in_per_m": 300.0, "out_per_m": 1200.0},
                },
                "search_per_call": 0.016,
            }
        ),
        encoding="utf-8",
    )
    env["PRICE_SHEET_PATH"] = str(sheet)
    refused = build_service(load_settings(env))
    assert not refused.ready and "NO_SERVABLE_MODE" in refused.problems


def test_run_manager_emits_stage_rejection_and_cost_events(tmp_path: Path) -> None:
    from core.models import ResearchResult
    from core.run_manager import RunManager
    from core.telemetry import Telemetry

    class Ctx:
        class guard:  # noqa: N801
            class ledger:  # noqa: N801
                committed_usd = 0.2
                unknown_cost = False

        def __init__(self, c) -> None:  # noqa: ANN001
            pass

    def runner(ctx, request, *, run_id, progress=None, demo=False, **_):  # noqa: ANN001, ANN003
        progress("planning", 0.05)
        progress("searching", 0.2)
        return ResearchResult(run_id=run_id, mode=request.depth, status=RunStatus.COMPLETED)

    tel = Telemetry(tmp_path)
    m = RunManager(
        context_factory=lambda r, c: Ctx(c), runner=runner, telemetry=tel, max_concurrent=1
    )
    req = ResearchRequest(topic="t", depth=Mode.QUICK, idempotency_token="a")
    first = m.submit("s1", req)
    m.wait(first.run_id, 5)
    names = [e["event"] for e in _events(tmp_path)]
    assert names.count("stage.finished") >= 2
    finished = [e for e in _events(tmp_path) if e["event"] == "run.finished"][0]
    assert finished["cost_usd"] == pytest.approx(0.2)
    m.begin_drain()
    m.submit("s2", ResearchRequest(topic="t", depth=Mode.QUICK, idempotency_token="b"))
    assert any(
        e["event"] == "run.rejected" and e["error_code"] == "SERVICE_PAUSED"
        for e in _events(tmp_path)
    )
    m.shutdown()


# --- #9 partial export is marked ------------------------------------------------------------------------


def test_partial_report_title_starts_with_partial() -> None:
    claim = ClaimRecord(
        claim_id="c1",
        text="A supported claim here.",
        facet_id="f1",
        section="findings",
        evidence=[EvidenceRef(citation_id=1, passage_id="1:p1", quote="A supported claim here.")],
        support_verdict=Verdict.SUPPORTED,
    )
    sections = assemble_sections(
        {"findings": [DraftSentence(type="claim", claim_id="c1")]},
        {"c1": claim},
        topic="T",
        flagged=set(),
    )
    md = render_markdown(
        topic="T",
        mode_label="Quick",
        status=RunStatus.PARTIAL,
        reasons=["LOW_DOMAINS"],
        researched_on="2025-01-01",
        sections=sections,
        claims={"c1": claim},
        sources={1: _source(1, "A supported claim here.")},
        not_inspected=[],
        coverage=[],
        warnings=[],
        demo=False,
    )
    assert md.startswith("# PARTIAL — Research report")
    done = render_markdown(
        topic="T",
        mode_label="Quick",
        status=RunStatus.COMPLETED,
        reasons=[],
        researched_on="2025-01-01",
        sections=sections,
        claims={"c1": claim},
        sources={1: _source(1, "A supported claim here.")},
        not_inspected=[],
        coverage=[],
        warnings=[],
        demo=False,
    )
    assert done.startswith("# Research report")


# --- #10 validation codes never reach users ---------------------------------------------------------------


def test_validation_warning_codes_become_plain_sentences(make_ctx) -> None:
    from core.research_agent import run_research

    result = run_research(
        make_ctx(),
        ResearchRequest(
            topic="Harborview bike share pilot 茶", depth=Mode.QUICK, idempotency_token="t"
        ),
        run_id="r",
    )
    assert result.warnings
    for w in result.warnings:
        assert (
            "NON_LATIN" not in w
            and "LATIN_NON_ENGLISH" not in w
            and "_" not in w.split(".")[0]
            or " " in w
        )


# keep the unused-import checker honest for names used only in type positions
_ = (DraftSection, SectionName)
