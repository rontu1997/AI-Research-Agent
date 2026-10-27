"""Evaluate a verifier model on scripted evidence, through the production batching path.

    uv run python -m eval.verifier_eval --model qwen3-vl:8b-instruct
    uv run python -m eval.verifier_eval --model qwen3-vl:8b-instruct --stress --parallel 1

The model is a local Ollama model (`http://localhost:11434/v1`, schema-constrained JSON, strict
Pydantic validation). No NVIDIA or Tavily request is made, and nothing is downloaded.

The fixture set (`eval/fixtures/verifier_scripted.jsonl`) is hand-written and SYNTHETIC: it is a
development check, not the sealed fixture set of PRD §11.2, and cannot certify the §2.6 gate.
Errors (timeouts, truncated prompts, invalid JSON) are counted as errors, never as acceptances.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from statistics import mean
from typing import Any

from adapters.base import LLMClient
from adapters.fakes import FakeLLM, FakeSearch
from core.capacity import (
    BudgetLedger,
    CallGuard,
    Deadline,
    ProviderGate,
    claims_per_verifier_batch,
)
from core.errors import BudgetStop, DeadlineExceeded, PipelineFailure
from core.models import (
    ClaimRecord,
    EvidenceMode,
    EvidenceRef,
    Mode,
    Passage,
    SourceRecord,
    Verdict,
)
from core.settings import load_settings_from_environment, mode_config
from eval.stats import wilson_interval
from pipeline.claim_checks import numeric_guard
from pipeline.context import RunContext
from pipeline.verifier import _verify_batch

FIXTURES = Path(__file__).parent / "fixtures" / "verifier_scripted.jsonl"
REPORTS = Path(__file__).parent / "reports"

# Observed upstream stage times on the live NVIDIA endpoint (replays of 2026-10-22), used only to
# judge whether a verifier stage would still fit a mode's wall clock.
UPSTREAM_WORST_S = 7.0 + 3.0 + 53.0  # planner + search + writer

_FILLER = (
    "Local officials said the figures would be reviewed again next year.",
    "The report was prepared by an independent committee of volunteers.",
    "Several residents asked for more public meetings on the subject.",
    "A summary table of the data is available in the appendix document.",
    "Comparable programmes in neighbouring regions were also examined.",
)


def load_rows(path: Path = FIXTURES) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _pad(text: str, target: int = 1480) -> str:
    out, i = text, 0
    while len(out) + len(_FILLER[i % len(_FILLER)]) + 1 <= target:
        out += " " + _FILLER[i % len(_FILLER)]
        i += 1
    return out


def build_inputs(
    rows: Sequence[dict[str, Any]], *, stress: bool
) -> tuple[list[ClaimRecord], dict[int, SourceRecord]]:
    """Claims and sources from fixture rows.

    Stress mode pads passages to production size and gives each
    claim three evidence references, so one batch approaches the PRD's 7,000-token Quick cap."""
    claims: list[ClaimRecord] = []
    sources: dict[int, SourceRecord] = {}
    for index, row in enumerate(rows, start=1):
        text = _pad(row["passage"]) if stress else row["passage"]
        pid = f"{index}:p1"
        quotes = list(row["quotes"])
        sources[index] = SourceRecord(
            citation_id=index,
            title=f"Fixture {row['id']}",
            url=f"https://fixture{index}.example.org/doc",
            canonical_url=f"https://fixture{index}.example.org/doc",
            registrable_domain="example.org",
            retrieved_at="2026-10-22T00:00:00Z",
            evidence_mode=EvidenceMode.EXTRACTED,
            passages=[Passage(passage_id=pid, text=text)],
            evidence_group_id=f"g{index}",
        )
        evidence = [EvidenceRef(citation_id=index, passage_id=pid, quote=q) for q in quotes]
        if stress:  # two more, unrelated, distinct passages so the batch reaches production size
            for step in (1, 2):
                other = (index - 1 + step) % len(rows) + 1
                evidence.append(
                    EvidenceRef(
                        citation_id=other,
                        passage_id=f"{other}:p1",
                        quote=rows[other - 1]["quotes"][0],
                    )
                )
        claims.append(
            ClaimRecord(
                claim_id=row["id"],
                text=row["claim"],
                facet_id="f1",
                section="findings",
                evidence=evidence,
                quote_match_ok=True,
                numeric_guard_ok=True,
            )
        )
    return claims, sources


# --- measurement helpers ----------------------------------------------------------------


class MemoryPeak:
    """Tracks the peak of a memory sampler (MB) while a run is in progress."""

    def __init__(self, sampler: Callable[[], float | None], interval_s: float = 2.0) -> None:
        self._sampler = sampler
        self._interval = interval_s
        self._peak: float | None = None
        self._baseline: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def sample_now(self) -> None:
        value = self._sampler()
        if value is not None and self._baseline is None:
            self._baseline = value  # the first reading is the baseline before the run
        if value is not None and (self._peak is None or value > self._peak):
            self._peak = value

    @property
    def peak_mb(self) -> float | None:
        return self._peak

    @property
    def baseline_mb(self) -> float | None:
        return self._baseline

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.is_set():
                self.sample_now()
                self._stop.wait(self._interval)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        self.sample_now()


def _powershell(command: str, timeout: float = 20.0) -> str | None:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def sample_memory_mb(prefix: str = "ollama") -> float | None:
    """Working set of every process whose name starts with ``prefix`` (Windows), in MB."""
    text = _powershell(
        f"(Get-Process | Where-Object {{ $_.Name -like '{prefix}*' }} | "
        "Measure-Object WorkingSet64 -Sum).Sum"
    )
    try:
        return round(float(text) / 1024 / 1024, 1) if text else None
    except ValueError:
        return None


def sample_system_ram_used_mb() -> float | None:
    """System RAM in use (Windows), in MB: total minus free. Counts model memory that a process
    working set misses (memory-mapped weights)."""
    text = _powershell(
        "$o = Get-CimInstance Win32_OperatingSystem; "
        "[math]::Round(($o.TotalVisibleMemorySize - $o.FreePhysicalMemory) / 1024, 1)"
    )
    try:
        return float(text) if text else None
    except ValueError:
        return None


def sample_gpu_used_mb() -> float | None:
    """NVIDIA GPU memory in use, in MB (first GPU), or None without nvidia-smi."""
    text = _powershell("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
    try:
        return float(text.splitlines()[0]) if text else None
    except ValueError:
        return None


def ollama_ps() -> str | None:
    try:
        out = subprocess.run(
            ["ollama", "ps"], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def hardware_snapshot() -> dict[str, Any]:
    info: dict[str, Any] = {"ram_total_gb": None, "cpu": None, "gpus": None}
    ram = _powershell("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")
    if ram:
        try:
            info["ram_total_gb"] = round(float(ram) / 1024**3, 1)
        except ValueError:
            pass
    info["cpu"] = _powershell("(Get-CimInstance Win32_Processor | Select-Object -First 1).Name")
    gpus = _powershell("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader")
    info["gpus"] = gpus.splitlines() if gpus else None
    return info


class _Recorder:
    """Wraps the verifier client to record each call's duration, token counts and outcome."""

    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def generate(self, **kwargs: Any) -> Any:
        started = time.monotonic()
        record: dict[str, Any] = {}
        try:
            result = self._inner.generate(**kwargs)
            record.update(
                input_tokens=result.input_tokens, output_tokens=result.output_tokens, ok=True
            )
            return result
        except Exception as err:  # noqa: BLE001 - recorded, then re-raised for the production path
            record.update(ok=False, error=type(err).__name__)
            raise
        finally:
            record["seconds"] = round(time.monotonic() - started, 2)
            with self._lock:
                self.calls.append(record)


# --- the run ----------------------------------------------------------------------------


def run_eval(
    ctx: RunContext,
    rows: Sequence[dict[str, Any]],
    *,
    stress: bool = False,
    parallel: int = 1,
    memory: dict[str, MemoryPeak] | None = None,
) -> dict[str, Any]:
    from pipeline.verifier import build_batches

    claims, sources = build_inputs(rows, stress=stress)
    batches = build_batches(claims, sources, ctx.cfg, ctx.chars_per_token)
    recorder = _Recorder(ctx.verifier)
    original = ctx.verifier
    ctx.verifier = recorder
    for series in (memory or {}).values():
        series.sample_now()  # baseline before the first request
        series.start()

    def one(
        item: tuple[int, list[ClaimRecord]],
    ) -> tuple[int, dict[str, Any], dict[str, tuple[Verdict, str]]]:
        index, batch = item
        started = time.monotonic()
        calls_before = len(recorder.calls)
        error = detail = None
        verdicts: dict[str, tuple[Verdict, str]] = {}
        try:
            verdicts = _verify_batch(ctx, batch, sources, None)
        except PipelineFailure as err:
            error, detail = err.code.value, err.detail
        except (BudgetStop, DeadlineExceeded) as err:
            error = type(err).__name__
        record = {
            "index": index,
            "claims": len(batch),
            "seconds": round(time.monotonic() - started, 2),
            "error": error,
            "detail": detail,
            "calls": len(recorder.calls) - calls_before,
        }
        return index, record, verdicts

    wall_started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
            outcomes = list(pool.map(one, enumerate(batches)))
    finally:
        ctx.verifier = original
        for series in (memory or {}).values():
            series.stop()
    wall = time.monotonic() - wall_started

    verdicts: dict[str, tuple[Verdict, str]] = {}
    batch_records = []
    for _, record, batch_verdicts in sorted(outcomes, key=lambda o: o[0]):
        batch_records.append(record)
        verdicts.update(batch_verdicts)

    result_rows = []
    for row in rows:
        found = verdicts.get(row["id"])
        result_rows.append(
            {
                "id": row["id"],
                "category": row["category"],
                "label": row["label"],
                "verdict": found[0].value if found else "error",
                "reason": (found[1] if found else "")[:160],
                "injection": row["injection"],
                "adversarial": row["adversarial"],
                "guard_ok": numeric_guard(row["claim"], row["quotes"]).ok,
                "synthetic": True,
            }
        )
    return {
        "config": {
            "model": ctx.verifier_model,
            "stress": stress,
            "parallel": parallel,
            "batch_size": claims_per_verifier_batch(ctx.cfg, ctx.chars_per_token),
            "verifier_input_cap": ctx.cfg.verifier_input_cap,
            "verifier_max_output": ctx.cfg.verifier_max_output,
            "wall_seconds": round(wall, 1),
            "full_batch_seconds": [
                b["seconds"]
                for b in batch_records
                if b["claims"] == claims_per_verifier_batch(ctx.cfg, ctx.chars_per_token)
                and not b["error"]
            ],
            "memory": {
                name: {"peak": s.peak_mb, "baseline": s.baseline_mb}
                for name, s in (memory or {}).items()
            },
        },
        "summary": _summarize(result_rows),
        "by_category": _by_category(result_rows),
        "batches": batch_records,
        "calls": recorder.calls,
        "rows": result_rows,
    }


def _summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    negatives = [r for r in rows if r["label"] == "unsupported"]
    positives = [r for r in rows if r["label"] == "supported"]
    errors = [r for r in rows if r["verdict"] == "error"]
    correct = sum(
        1
        for r in rows
        if r["verdict"] != "error" and (r["verdict"] == "supported") == (r["label"] == "supported")
    )
    fa = [r for r in negatives if r["verdict"] == "supported"]
    fr = [r for r in positives if r["verdict"] not in {"supported", "error"}]
    return {
        "rows": len(rows),
        "positives": len(positives),
        "negatives": len(negatives),
        "adversarial_negatives": sum(1 for r in negatives if r["adversarial"]),
        "errors": len(errors),
        "uncertain": sum(1 for r in rows if r["verdict"] == "uncertain"),
        "accuracy": round(correct / len(rows), 4) if rows else 0.0,
        "false_accepts": len(fa),
        "false_accept_ids": [r["id"] for r in fa],
        "false_accept_wilson_95": [round(x, 3) for x in wilson_interval(len(fa), len(negatives))],
        "false_rejects": len(fr),
        "false_reject_ids": [r["id"] for r in fr],
        "injection_rows": sum(1 for r in rows if r["injection"]),
        "injection_false_accepts": sum(1 for r in fa if r["injection"]),
        # In production the numeric guard rejects a claim before the verifier sees it, so these
        # separate the pairs only the verifier can decide from the ones the guard already stops.
        "guard_blocked_ids": [r["id"] for r in negatives if not r.get("guard_ok", True)],
        "guard_blocked_positive_ids": [r["id"] for r in positives if not r.get("guard_ok", True)],
        "negatives_reaching_verifier": sum(1 for r in negatives if r.get("guard_ok", True)),
        "false_accepts_reaching_verifier": sum(1 for r in fa if r.get("guard_ok", True)),
        "injection_negatives": sum(1 for r in negatives if r["injection"]),
        "injection_negatives_reaching_verifier": sum(
            1 for r in negatives if r["injection"] and r.get("guard_ok", True)
        ),
        "injection_false_accepts_reaching_verifier": sum(
            1 for r in fa if r["injection"] and r.get("guard_ok", True)
        ),
    }


def _by_category(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = defaultdict(
        lambda: {"rows": 0, "correct": 0, "false_accepts": 0, "false_rejects": 0, "errors": 0}
    )
    for r in rows:
        c = out[r["category"]]
        c["rows"] += 1
        if r["verdict"] == "error":
            c["errors"] += 1
            continue
        accepted = r["verdict"] == "supported"
        if accepted == (r["label"] == "supported"):
            c["correct"] += 1
        elif accepted:
            c["false_accepts"] += 1
        else:
            c["false_rejects"] += 1
    return dict(out)


def quick_feasibility(
    batch_seconds: Sequence[float], *, parallel: int, mode: Mode
) -> dict[str, Any]:
    """Would the verifier stage, a scan call and the observed upstream stages fit the wall clock?"""
    cfg = mode_config(mode)
    per_batch = claims_per_verifier_batch(cfg)
    batches = math.ceil(cfg.max_claims / per_batch)
    mean_s = mean(batch_seconds) if batch_seconds else 0.0
    stage = math.ceil(batches / max(1, parallel)) * mean_s
    total = stage + mean_s + UPSTREAM_WORST_S  # + one scan call
    out: dict[str, Any] = {
        "mode": mode.value,
        "batches": batches,
        "mean_batch_s": round(mean_s, 1),
        "verifier_stage_s": round(stage, 1),
        "upstream_worst_s": UPSTREAM_WORST_S,
        "total_estimate_s": round(total, 1),
        "wall_clock_s": cfg.wall_clock_s,
        "fits_limit": total <= cfg.wall_clock_s,
    }
    if mode is Mode.QUICK:
        out["fits_quick_limit"] = out["fits_limit"]
    return out


def gate_report(report: dict[str, Any]) -> dict[str, Any]:
    """PRD §2.6 screening thresholds applied as RATES to this small synthetic set. Indicative only.

    The PRD allows 2 false accepts among 60 negatives (3.3 percent) and 6 false rejects among 30
    supported pairs (20 percent), and none on injection pairs. Raw counts flatter a smaller set.
    """
    s = report["summary"]
    negatives, positives = max(1, s["negatives"]), max(1, s["positives"])
    fa_rate, fr_rate = s["false_accepts"] / negatives, s["false_rejects"] / positives
    formal = s["negatives"] >= 60 and s["adversarial_negatives"] >= 20 and s["positives"] >= 30
    indicative = fa_rate <= 2 / 60 and fr_rate <= 6 / 30 and s["injection_false_accepts"] == 0
    return {
        "formal_gate_possible": formal,
        "indicative_pass": indicative,
        "false_accept_rate": round(fa_rate, 4),
        "false_reject_rate": round(fr_rate, 4),
        "thresholds": "false accepts at most 2 in 60 (3.3 percent) among negatives with 20+ "
        "adversarial, no false accept on an injection pair, false rejects at most 6 in 30 "
        "(20 percent) among supported pairs",
        "note": "this synthetic set is smaller than the sealed set and cannot certify the gate",
    }


def rescore_report(report: dict[str, Any], rows_path: Path = FIXTURES) -> dict[str, Any]:
    """Recompute summary, categories and gate from stored rows. Calls no model."""
    guard = {r["id"]: numeric_guard(r["claim"], r["quotes"]).ok for r in load_rows(rows_path)}
    for row in report["rows"]:
        row["guard_ok"] = guard.get(row["id"], True)
    report["summary"] = _summarize(report["rows"])
    report["by_category"] = _by_category(report["rows"])
    report["gate"] = gate_report(report)
    return report


def unload_models(runner: Callable[..., Any] = subprocess.run, settle_s: float = 5.0) -> list[str]:
    """Stop every model Ollama has loaded, so the memory baseline is an idle machine."""
    try:
        listing = runner(["ollama", "ps"], capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    names = [line.split()[0] for line in listing.stdout.strip().splitlines()[1:] if line.strip()]
    for name in names:
        try:
            runner(
                ["ollama", "stop", name], capture_output=True, text=True, timeout=60, check=False
            )
        except (OSError, subprocess.SubprocessError):
            pass
    if names and settle_s:
        time.sleep(settle_s)
    return names


# --- command line -----------------------------------------------------------------------


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def main(argv: Sequence[str] | None = None) -> int:
    from adapters.live import build_verifier

    parser = argparse.ArgumentParser(
        description="Evaluate a local Ollama verifier on scripted evidence."
    )
    parser.add_argument("--model", default="", help="Ollama model tag, e.g. qwen3-vl:8b-instruct")
    parser.add_argument(
        "--rescore", default="", help="recompute a stored report (no model is called)"
    )
    parser.add_argument("--cold-start", action="store_true", help="unload loaded models first")
    parser.add_argument(
        "--fixtures",
        default="",
        help="fixture file a stored report was measured on (with --rescore)",
    )
    parser.add_argument(
        "--stress",
        action="store_true",
        help="production-sized prompts (3 x 1,500-char passages per claim)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="batches in flight at once (Ollama serves one at a time by default)",
    )
    parser.add_argument("--mode", choices=["quick", "deep"], default="quick")
    parser.add_argument(
        "--timeout-s", type=float, default=900.0, help="per-call timeout for the evaluation only"
    )
    parser.add_argument("--limit", type=int, default=0, help="evaluate only the first N rows")
    parser.add_argument(
        "--base-url",
        default="",
        help="override the Ollama endpoint (default http://localhost:11434/v1)",
    )
    parser.add_argument("--out", default="", help="report path (default eval/reports/...)")
    try:
        args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])
    except SystemExit as err:
        return int(err.code or 2)

    if args.rescore:
        path = Path(args.rescore)
        rescored = rescore_report(
            json.loads(path.read_text(encoding="utf-8")),
            Path(args.fixtures) if args.fixtures else FIXTURES,
        )
        path.write_text(json.dumps(rescored, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"rescored {path}", file=sys.stderr)
        return 0
    if not args.model:
        print("--model is required (or --rescore PATH).", file=sys.stderr)
        return 2
    settings = load_settings_from_environment()
    settings = replace(
        settings,
        verifier_provider="ollama",
        verifier_model=args.model,
        verifier_json_mode="json_schema",
        verifier_base_url=args.base_url,
        verifier_token_param="max_tokens",
    )
    mode = Mode(args.mode)
    cfg = mode_config(mode)
    prices = settings.price_sheet
    if not prices.has_model(args.model):
        print(
            f"Model {args.model} is not in the price sheet; add it to PRICE_SHEET_PATH.",
            file=sys.stderr,
        )
        return 2
    verifier = build_verifier(settings)
    guard = CallGuard(
        ledger=BudgetLedger(
            1000.0, {}
        ),  # an evaluation is not a production run: no cost cap applies
        deadline=Deadline(4 * 3600),
        is_cancelled=lambda: False,
        gates={n: ProviderGate(n, 1000.0, 1000) for n in ("search", "writer", "verifier")},
    )
    ctx = RunContext(
        cfg=cfg,
        prices=prices,
        guard=guard,
        search=FakeSearch(),
        writer=FakeLLM("fake-writer"),
        verifier=verifier,
        writer_model=args.model,
        verifier_model=args.model,
        verifier_timeout_factor=max(1.0, args.timeout_s / 30.0),
    )
    rows = load_rows()
    if args.limit:
        rows = rows[: args.limit]
    unloaded = unload_models() if args.cold_start else []
    memory = {
        "system_ram_used_mb": MemoryPeak(sample_system_ram_used_mb),
        "gpu_used_mb": MemoryPeak(sample_gpu_used_mb),
        "ollama_working_set_mb": MemoryPeak(sample_memory_mb),
    }
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    report = run_eval(ctx, rows, stress=args.stress, parallel=args.parallel, memory=memory)
    report["started"] = started
    report["hardware"] = hardware_snapshot()
    report["ollama_ps"] = ollama_ps()
    report["config"]["cold_start"] = {"unloaded": unloaded} if args.cold_start else None
    seconds = report["config"]["full_batch_seconds"]  # a short last batch would bias the mean
    report["quick_feasibility"] = (
        quick_feasibility(seconds, parallel=args.parallel, mode=Mode.QUICK) if seconds else None
    )
    report["deep_feasibility"] = (
        quick_feasibility(seconds, parallel=args.parallel, mode=Mode.DEEP) if seconds else None
    )
    report["gate"] = gate_report(report)
    out = (
        Path(args.out)
        if args.out
        else REPORTS / f"verifier_{_safe(args.model)}_{'stress' if args.stress else 'normal'}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    s = report["summary"]
    print(
        json.dumps(
            {
                "summary": s,
                "by_category": report["by_category"],
                "config": report["config"],
                "quick_feasibility": report["quick_feasibility"],
                "gate": report["gate"],
            },
            indent=2,
        )
    )
    print(f"report written to {out}", file=sys.stderr)
    return 0 if s["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
