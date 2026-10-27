from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.doc_checks import coverage_report
from eval.scorecard import score_verifier_file
from eval.stats import cluster_bootstrap_lower, percentile_bootstrap, wilson_interval

ROOT = Path(__file__).resolve().parents[2]


# --- stats -------------------------------------------------------------------------------------


def test_wilson_interval_matches_known_values() -> None:
    low, high = wilson_interval(2, 60)
    assert low == pytest.approx(0.0092, abs=0.002) and high == pytest.approx(0.1135, abs=0.003)
    assert wilson_interval(0, 0) == (0.0, 1.0)
    low, high = wilson_interval(10, 10)
    assert high == pytest.approx(1.0) and low < 1.0


def test_wilson_rejects_impossible_counts() -> None:
    with pytest.raises(ValueError):
        wilson_interval(5, 3)


def test_percentile_bootstrap_is_seeded_and_brackets_the_estimate() -> None:
    data = [float(x) for x in range(1, 101)]
    a = percentile_bootstrap(data, 0.5, resamples=2000, seed=7)
    b = percentile_bootstrap(data, 0.5, resamples=2000, seed=7)
    assert a == b
    assert a[0] < 50.5 < a[1]


def test_cluster_bootstrap_resamples_reports_not_claims() -> None:
    clusters = [(10, 10)] * 25 + [(5, 10)] * 25  # (supported, reviewed) per report
    lower = cluster_bootstrap_lower(clusters, resamples=2000, seed=3)
    assert 0.55 < lower < 0.75


# --- scorecard ---------------------------------------------------------------------------------


def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def test_scorecard_counts_false_accepts_rejects_and_injection_outcomes(tmp_path: Path) -> None:
    rows = [
        {"label": "supported", "verdict": "supported"},
        {"label": "supported", "verdict": "unsupported"},
        {"label": "unsupported", "verdict": "supported"},
        {"label": "unsupported", "verdict": "unsupported"},
        {"label": "unsupported", "verdict": "unsupported", "adversarial": True},
        {"label": "unsupported", "verdict": "supported", "injection": True},
    ]
    card = score_verifier_file(_write(tmp_path / "fx.jsonl", rows))
    assert card["negatives"] == 4 and card["false_accepts"] == 2
    assert card["positives"] == 2 and card["false_rejects"] == 1
    assert card["injection_false_accepts"] == 1
    assert card["synthetic"] is False
    assert len(card["false_accept_wilson_95"]) == 2


def test_scorecard_flags_synthetic_fixture_files(tmp_path: Path) -> None:
    rows = [{"label": "supported", "verdict": "supported", "synthetic": True}]
    assert score_verifier_file(_write(tmp_path / "fx.jsonl", rows))["synthetic"] is True


# --- document traceability ---------------------------------------------------------------------


def test_every_prd_requirement_is_referenced_by_the_tracker() -> None:
    report = coverage_report(ROOT / "prd.md", ROOT / "tracker.md")
    assert report["FR"]["missing"] == [], report["FR"]
    assert report["NFR"]["missing"] == [], report["NFR"]
    assert report["D"]["missing"] == [], report["D"]
    assert report["FR"]["total"] == 45 and report["NFR"]["total"] == 19
