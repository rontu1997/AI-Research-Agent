from __future__ import annotations

import json
import threading
from datetime import date, timedelta
from pathlib import Path

from core.telemetry import Telemetry


def _lines(path: Path) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for file in sorted(path.glob("events-*.jsonl")):
        out += [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()]
    return out


def test_allowed_events_and_fields_are_written(tmp_path: Path) -> None:
    t = Telemetry(tmp_path)
    t.emit(
        "run.finished",
        run_id="r1",
        mode="quick",
        status="completed",
        elapsed_ms=1200,
        cost_usd=0.12,
    )
    (line,) = _lines(tmp_path)
    assert line["event"] == "run.finished"
    assert line["run_id"] == "r1" and line["elapsed_ms"] == 1200
    assert "ts" in line


def test_unknown_events_are_dropped(tmp_path: Path) -> None:
    t = Telemetry(tmp_path)
    t.emit("user.typed.topic", run_id="r1")
    assert _lines(tmp_path) == []


def test_non_allowlisted_fields_never_reach_disk(tmp_path: Path) -> None:
    t = Telemetry(tmp_path)
    t.emit(
        "run.finished",
        run_id="r1",
        topic="my private topic",
        url="https://x.example",
        api_key="sk-secret",
    )
    text = "".join(f.read_text(encoding="utf-8") for f in tmp_path.glob("*.jsonl"))
    assert "private" not in text and "sk-secret" not in text and "https://" not in text


def test_free_text_values_are_dropped_even_under_allowed_names(tmp_path: Path) -> None:
    t = Telemetry(tmp_path)
    t.emit("run.finished", run_id="r1", error_code="a long sentence that looks like user text")
    (line,) = _lines(tmp_path)
    assert "error_code" not in line


def test_old_files_are_purged_and_new_ones_kept(tmp_path: Path) -> None:
    old = tmp_path / f"events-{(date.today() - timedelta(days=30)):%Y%m%d}.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    Telemetry(tmp_path, retention_days=7)
    assert not old.exists()


def test_concurrent_writes_keep_every_line_intact(tmp_path: Path) -> None:
    t = Telemetry(tmp_path)

    def work(n: int) -> None:
        for i in range(50):
            t.emit("stage.finished", run_id=f"r{n}", stage="verifying", elapsed_ms=i)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(_lines(tmp_path)) == 400


def test_feedback_vote_is_recorded_without_any_report_content(tmp_path: Path) -> None:
    t = Telemetry(tmp_path)
    t.emit("ui.feedback", run_id="r1", vote="useful", report="secret report text")
    (line,) = _lines(tmp_path)
    assert line["vote"] == "useful" and "report" not in line
