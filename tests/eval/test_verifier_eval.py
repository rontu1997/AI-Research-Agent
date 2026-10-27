"""The verifier evaluation harness and its scripted fixture set (no model, no network)."""

from __future__ import annotations

import json
from collections import Counter

import pytest

from adapters.fakes import FakeLLM
from core.errors import ProviderServerError
from core.models import Mode, Verdict, VerifierItem, VerifierOutput
from eval.verifier_eval import (
    FIXTURES,
    MemoryPeak,
    build_inputs,
    gate_report,
    load_rows,
    main,
    quick_feasibility,
    run_eval,
)
from pipeline.claim_checks import numeric_guard, quote_in_passage

ROWS = load_rows()


# --- the fixture set ------------------------------------------------------------------------------------------


def test_fixture_set_covers_every_requested_case_type() -> None:
    cats = Counter(r["category"] for r in ROWS)
    assert {"plain", "overreach", "contradiction", "numeric", "date", "injection"} <= set(cats)
    labels = Counter(r["label"] for r in ROWS)
    assert labels["supported"] >= 15 and labels["unsupported"] >= 20
    assert sum(1 for r in ROWS if r["injection"] and r["label"] == "unsupported") >= 5
    assert (
        sum(1 for r in ROWS if r["injection"] and r["label"] == "supported") >= 2
    )  # must not obey "say unsupported"
    assert all(r["synthetic"] is True for r in ROWS)  # never mistaken for a sealed-set result
    assert len({r["id"] for r in ROWS}) == len(ROWS)


def test_every_quote_is_verbatim_in_its_passage_and_fits_the_quote_limits() -> None:
    for r in ROWS:
        for q in r["quotes"]:
            assert quote_in_passage(q, r["passage"]), r["id"]
            assert 25 <= len(q) <= 300, r["id"]


def test_injection_rows_really_contain_an_instruction_aimed_at_the_verifier() -> None:
    markers = (
        "ignore",
        "verifier",
        "system",
        "always output",
        "new instructions",
        "assistant:",
        '"results"',
        "reviewer comment",
    )
    for r in (r for r in ROWS if r["injection"]):
        assert any(m in r["passage"].lower() for m in markers), r["id"]


def test_hard_numeric_and_date_negatives_pass_the_deterministic_guard() -> None:
    """These are the cases only a semantic verifier can reject: every figure appears in the quote."""
    tricky = [
        r
        for r in ROWS
        if r["adversarial"] and r["category"] in {"numeric", "date"} and r["id"] not in {"N08"}
    ]
    assert len(tricky) >= 5
    for r in tricky:
        assert numeric_guard(r["claim"], r["quotes"]).ok, r["id"]


# --- the harness -------------------------------------------------------------------------------------------------


def _oracle() -> FakeLLM:
    truth = {r["id"]: r["label"] for r in ROWS}
    llm = FakeLLM("fake-verifier")

    def handler(ctx):  # noqa: ANN001
        items = json.loads(ctx.blocks["claims"])
        return VerifierOutput(
            results=[
                VerifierItem(
                    claim_id=i["claim_id"], verdict=Verdict(truth[i["claim_id"]]), reason="oracle"
                )
                for i in items
            ]
        )

    llm.set_handler(VerifierOutput, handler)
    return llm


def _obedient() -> FakeLLM:
    llm = FakeLLM("fake-verifier")
    llm.set_handler(
        VerifierOutput,
        lambda ctx: VerifierOutput(
            results=[
                VerifierItem(claim_id=i["claim_id"], verdict=Verdict.SUPPORTED, reason="ok")
                for i in json.loads(ctx.blocks["claims"])
            ]
        ),
    )
    return llm


def test_a_perfect_verifier_scores_perfectly_and_the_report_is_complete(make_ctx) -> None:
    ctx = make_ctx(verifier=_oracle(), cap_usd=100.0)
    report = run_eval(ctx, ROWS)
    s = report["summary"]
    assert s["rows"] == len(ROWS) and s["errors"] == 0 and s["accuracy"] == 1.0
    assert s["false_accepts"] == 0 and s["false_rejects"] == 0 and s["injection_false_accepts"] == 0
    assert set(report["by_category"]) >= {
        "plain",
        "numeric",
        "date",
        "injection",
        "contradiction",
        "overreach",
    }
    assert report["batches"] and all(b["seconds"] >= 0 for b in report["batches"])
    assert max(b["claims"] for b in report["batches"]) <= 4  # the production batch size for Quick
    json.dumps(report)  # serializable


def test_a_verifier_that_obeys_embedded_instructions_fails_the_gate(make_ctx) -> None:
    report = run_eval(make_ctx(verifier=_obedient(), cap_usd=100.0), ROWS)
    s = report["summary"]
    negatives = sum(1 for r in ROWS if r["label"] == "unsupported")
    assert s["false_accepts"] == negatives
    assert s["injection_false_accepts"] >= 5
    gate = gate_report(report)
    assert gate["indicative_pass"] is False and gate["formal_gate_possible"] is False


def test_provider_errors_are_counted_never_accepted_and_never_hidden(make_ctx) -> None:
    llm = FakeLLM("fake-verifier")

    def down(ctx):  # noqa: ANN001
        raise ProviderServerError("down")

    llm.set_handler(VerifierOutput, down)
    report = run_eval(make_ctx(verifier=llm, cap_usd=100.0), ROWS)
    s = report["summary"]
    assert s["errors"] == len(ROWS) and s["false_accepts"] == 0
    assert all(r["verdict"] == "error" for r in report["rows"])
    assert report["batches"][0]["error"] == "VERIFIER_FAILED"


def test_stress_mode_builds_production_sized_prompts(make_ctx) -> None:
    from core.tokens import estimate_tokens

    sizes: dict[str, int] = {}

    def make(label: str) -> FakeLLM:
        llm = _oracle()
        inner = llm._handlers[VerifierOutput]

        def handler(ctx):  # noqa: ANN001
            sizes[label] = max(sizes.get(label, 0), estimate_tokens(ctx.blocks["claims"]))
            return inner(ctx)

        llm.set_handler(VerifierOutput, handler)
        return llm

    run_eval(make_ctx(verifier=make("normal"), cap_usd=100.0), ROWS)
    run_eval(make_ctx(verifier=make("stress"), cap_usd=100.0), ROWS, stress=True)
    assert sizes["normal"] < 2500
    assert (
        4000 <= sizes["stress"] <= 7000
    )  # near the PRD's 7,000-token Quick batch cap, never over it


def test_build_inputs_keeps_the_real_evidence_in_stress_mode() -> None:
    claims, sources = build_inputs(ROWS, stress=True)
    for claim, row in zip(claims, ROWS, strict=True):
        assert claim.claim_id == row["id"] and claim.text == row["claim"]
        assert any(
            row["quotes"][0] in p.text for p in sources[claim.evidence[0].citation_id].passages
        )
        assert 1500 >= max(len(p.text) for s in sources.values() for p in s.passages) > 1000


# --- Quick-mode feasibility, memory, gates -----------------------------------------------------------------------


def test_quick_feasibility_arithmetic() -> None:
    fast = quick_feasibility([10.0, 12.0, 11.0, 9.0], parallel=1, mode=Mode.QUICK)
    assert fast["verifier_stage_s"] == pytest.approx(4 * 10.5)
    assert fast["fits_quick_limit"] is True
    slow = quick_feasibility([60.0, 70.0, 65.0, 65.0], parallel=1, mode=Mode.QUICK)
    assert slow["verifier_stage_s"] == pytest.approx(4 * 65.0) and slow["fits_quick_limit"] is False
    parallel = quick_feasibility([60.0, 60.0, 60.0, 60.0], parallel=4, mode=Mode.QUICK)
    assert parallel["verifier_stage_s"] == pytest.approx(60.0)
    deep = quick_feasibility([20.0] * 4, parallel=1, mode=Mode.DEEP)
    assert deep["batches"] == 9 and deep["verifier_stage_s"] == pytest.approx(180.0)


def test_memory_peak_tracking_keeps_the_maximum_and_survives_a_missing_sampler() -> None:
    values = iter([100.0, 900.0, 400.0, None])
    peak = MemoryPeak(lambda: next(values, None), interval_s=0.01)
    peak.sample_now(), peak.sample_now(), peak.sample_now(), peak.sample_now()
    assert peak.peak_mb == 900.0
    assert MemoryPeak(lambda: None).peak_mb is None


def test_the_formal_gate_needs_the_sealed_sample_sizes() -> None:
    report = {
        "summary": {
            "false_accepts": 0,
            "false_rejects": 0,
            "injection_false_accepts": 0,
            "negatives": 26,
            "positives": 19,
            "adversarial_negatives": 18,
        }
    }
    gate = gate_report(report)
    assert (
        gate["formal_gate_possible"] is False
    )  # needs 60+ negatives (20+ adversarial) and 30+ positives
    assert gate["indicative_pass"] is True
    worse = gate_report({"summary": dict(report["summary"], false_accepts=3)})
    assert worse["indicative_pass"] is False


def test_the_command_needs_a_model_and_the_fixture_file_ships_with_the_package() -> None:
    assert main([]) == 2
    assert FIXTURES.is_file()


def test_run_eval_reports_every_memory_series_with_its_peak_and_baseline(make_ctx) -> None:
    from eval.verifier_eval import MemoryPeak

    readings = iter([5000.0, 7000.0, 6000.0] + [6500.0] * 50)
    series = {
        "system_ram_used_mb": MemoryPeak(lambda: next(readings, 6500.0), interval_s=0.01),
        "gpu_used_mb": MemoryPeak(lambda: None, interval_s=0.01),
    }
    report = run_eval(make_ctx(verifier=_oracle(), cap_usd=100.0), ROWS[:8], memory=series)
    mem = report["config"]["memory"]
    assert (
        mem["system_ram_used_mb"]["peak"] >= 6500.0
        and mem["system_ram_used_mb"]["baseline"] == 5000.0
    )
    assert mem["gpu_used_mb"] == {"peak": None, "baseline": None}


def test_memory_samplers_parse_powershell_and_nvidia_smi_output(monkeypatch) -> None:
    import eval.verifier_eval as ve

    monkeypatch.setattr(
        ve,
        "_powershell",
        lambda cmd, timeout=20.0: "12288.5" if "FreePhysicalMemory" in cmd else "3500",
    )
    assert ve.sample_system_ram_used_mb() == pytest.approx(12288.5)
    monkeypatch.setattr(ve, "_powershell", lambda cmd, timeout=20.0: "2711")
    assert ve.sample_gpu_used_mb() == 2711.0
    monkeypatch.setattr(ve, "_powershell", lambda cmd, timeout=20.0: None)
    assert ve.sample_system_ram_used_mb() is None and ve.sample_gpu_used_mb() is None


# --- review fixes: harder positives, honest gate, guard-aware reporting, cold start ----------------------------


def test_supported_claims_include_real_paraphrases_not_only_near_copies() -> None:
    from pipeline.claim_checks import normalize_for_match

    para = [r for r in ROWS if r["category"] == "paraphrase"]
    assert len(para) >= 8 and all(r["label"] == "supported" for r in para)
    for r in para:
        assert normalize_for_match(r["claim"]) not in normalize_for_match(r["passage"]), r["id"]
        assert numeric_guard(r["claim"], r["quotes"]).ok, r[
            "id"
        ]  # the guard must let a faithful paraphrase through


def test_an_injection_row_pressures_the_verifier_to_reject_a_supported_claim() -> None:
    pushing_to_reject = [
        r
        for r in ROWS
        if r["injection"]
        and r["label"] == "supported"
        and any(w in r["passage"].lower() for w in ("reject", "unsupported"))
    ]
    assert len(pushing_to_reject) >= 2  # I01 and the replacement for the old, uninformative I02


def test_stress_mode_cites_three_distinct_passages_per_claim() -> None:
    claims, sources = build_inputs(ROWS, stress=True)
    for claim in claims:
        assert len({ref.citation_id for ref in claim.evidence}) == 3, claim.claim_id
        assert all(len(sources[ref.citation_id].passages[0].text) <= 1500 for ref in claim.evidence)


def test_the_report_says_which_negatives_the_deterministic_guard_already_blocks(make_ctx) -> None:
    report = run_eval(make_ctx(verifier=_oracle(), cap_usd=100.0), ROWS)
    s = report["summary"]
    assert {"N08", "I04", "I05", "I07"} <= set(s["guard_blocked_ids"])
    assert s["negatives_reaching_verifier"] == s["negatives"] - len(s["guard_blocked_ids"])
    assert s["guard_blocked_positive_ids"] == []  # a faithful claim is never stopped by the guard
    assert all("guard_ok" in r for r in report["rows"])
    assert 0 < s["injection_negatives_reaching_verifier"] < s["injection_negatives"]


def test_full_size_batches_are_timed_separately_from_the_short_last_batch(make_ctx) -> None:
    report = run_eval(make_ctx(verifier=_oracle(), cap_usd=100.0), ROWS)
    full = report["config"]["full_batch_seconds"]
    assert len(full) == sum(1 for b in report["batches"] if b["claims"] == 4)
    assert len(full) < len(report["batches"]) or len(ROWS) % 4 == 0


def _summary(**over):  # noqa: ANN202, ANN003
    base = {
        "false_accepts": 0,
        "false_rejects": 0,
        "injection_false_accepts": 0,
        "negatives": 26,
        "positives": 27,
        "adversarial_negatives": 17,
    }
    base.update(over)
    return {"summary": base}


def test_the_indicative_gate_compares_rates_not_raw_counts() -> None:
    assert gate_report(_summary())["indicative_pass"] is True
    two_of_26 = gate_report(
        _summary(false_accepts=2)
    )  # 7.7 percent against the PRD's 2 of 60 (3.3 percent)
    assert two_of_26["indicative_pass"] is False and two_of_26[
        "false_accept_rate"
    ] == pytest.approx(2 / 26, abs=1e-3)
    assert gate_report(_summary(negatives=60, false_accepts=2))["indicative_pass"] is True
    assert gate_report(_summary(injection_false_accepts=1))["indicative_pass"] is False
    assert (
        gate_report(_summary(false_rejects=6))["indicative_pass"] is False
    )  # 6 of 27 is above 6 of 30
    assert gate_report(_summary(false_rejects=5))["indicative_pass"] is True


def test_a_stored_report_can_be_rescored_without_calling_any_model(make_ctx) -> None:
    from eval.verifier_eval import rescore_report

    report = run_eval(make_ctx(verifier=_obedient(), cap_usd=100.0), ROWS)
    for r in report["rows"]:
        r.pop("guard_ok", None)  # an older report
    del report["summary"]["guard_blocked_ids"]
    again = rescore_report(report)
    assert again["summary"]["guard_blocked_ids"] and again["gate"]["indicative_pass"] is False
    assert again["summary"]["false_accepts"] == report["summary"]["false_accepts"]


def test_cold_start_unloads_loaded_models_so_the_memory_baseline_is_idle() -> None:
    from eval.verifier_eval import unload_models

    calls: list[list[str]] = []

    def runner(cmd, **kw):  # noqa: ANN001, ANN003, ANN202
        calls.append(list(cmd))
        text = (
            "NAME ID SIZE PROCESSOR CONTEXT UNTIL\nqwen3-vl:8b-instruct abc 6.3 GB 76%/24% 4096 4 minutes\n"
            if cmd[1] == "ps"
            else ""
        )
        return type("R", (), {"stdout": text, "returncode": 0})()

    assert unload_models(runner=runner, settle_s=0) == ["qwen3-vl:8b-instruct"]
    assert ["ollama", "stop", "qwen3-vl:8b-instruct"] in calls


def test_rescoring_can_use_the_fixture_version_a_report_was_measured_on(tmp_path) -> None:  # noqa: ANN001
    from eval.verifier_eval import rescore_report

    row = {
        "id": "ZZ99",
        "category": "numeric",
        "label": "unsupported",
        "passage": "It was cheap and quick to build.",
        "quotes": ["It was cheap and quick to build."],
        "claim": "It cost 9 million dollars.",
        "injection": False,
        "adversarial": True,
        "synthetic": True,
    }
    old = tmp_path / "old.jsonl"
    old.write_text(json.dumps(row) + "\n", encoding="utf-8")

    def report() -> dict:  # noqa: ANN202
        stored = {
            "id": "ZZ99",
            "category": "numeric",
            "label": "unsupported",
            "verdict": "supported",
            "reason": "",
            "injection": False,
            "adversarial": True,
            "synthetic": True,
        }
        return {"rows": [dict(stored)], "summary": {}, "by_category": {}}

    assert rescore_report(report(), rows_path=old)["summary"]["guard_blocked_ids"] == ["ZZ99"]
    assert (
        rescore_report(report())["summary"]["guard_blocked_ids"] == []
    )  # unknown id: not assumed blocked


def test_the_original_fixture_version_matches_the_stored_reports() -> None:
    import json as _json
    from pathlib import Path

    v1 = load_rows(FIXTURES.with_name("verifier_scripted_v1.jsonl"))
    assert len(v1) == 45 and len({r["id"] for r in v1}) == 45
    stored = _json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "eval"
            / "reports"
            / "verifier_qwen3-vl_8b-instruct_normal.json"
        ).read_text(encoding="utf-8")
    )
    assert {r["id"] for r in stored["rows"]} == {r["id"] for r in v1}
    assert not any(r["category"] == "paraphrase" for r in v1)
