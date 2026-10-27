from __future__ import annotations

from pathlib import Path

from core.drain import DrainMarker, wait_for_drain


def test_marker_round_trip_and_active_count(tmp_path: Path) -> None:
    marker = DrainMarker(tmp_path)
    assert not marker.is_set()
    marker.set()
    assert marker.is_set()
    marker.publish_active(3)
    assert marker.read_active() == 3
    marker.clear()
    assert not marker.is_set()


def test_read_active_is_conservative_when_the_file_is_missing_or_garbled(tmp_path: Path) -> None:
    marker = DrainMarker(tmp_path)
    assert marker.read_active() == 0
    (tmp_path / "active-runs.count").write_text("not a number", encoding="utf-8")
    assert marker.read_active() == 1  # unknown means assume work is still running


def test_wait_returns_true_as_soon_as_runs_finish(tmp_path: Path) -> None:
    marker = DrainMarker(tmp_path)
    marker.publish_active(2)
    ticks = {"n": 0}

    def sleep(_: float) -> None:
        ticks["n"] += 1
        if ticks["n"] == 3:
            marker.publish_active(0)

    now = {"t": 0.0}
    assert (
        wait_for_drain(marker, timeout_s=120, poll_s=1, clock=lambda: now["t"], sleep=sleep) is True
    )
    assert marker.is_set()


def test_wait_gives_up_at_the_drain_timeout(tmp_path: Path) -> None:
    marker = DrainMarker(tmp_path)
    marker.publish_active(1)
    now = {"t": 0.0}

    def sleep(seconds: float) -> None:
        now["t"] += seconds

    assert (
        wait_for_drain(marker, timeout_s=10, poll_s=1, clock=lambda: now["t"], sleep=sleep) is False
    )
