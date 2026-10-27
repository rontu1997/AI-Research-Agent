"""Graceful-drain handshake between the wrapper process and the app (PRD NFR-19; ARCH §12.2).

The wrapper cannot reach into the Streamlit process, so the two sides share two small files in the
state directory: a drain marker the wrapper writes, and an active-run count the app publishes.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

MARKER_NAME = "drain.marker"
ACTIVE_NAME = "active-runs.count"


class DrainMarker:
    def __init__(self, state_dir: Path | str) -> None:
        self._dir = Path(state_dir)

    def set(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / MARKER_NAME).write_text("drain", encoding="utf-8")

    def clear(self) -> None:
        (self._dir / MARKER_NAME).unlink(missing_ok=True)

    def is_set(self) -> bool:
        return (self._dir / MARKER_NAME).is_file()

    def publish_active(self, count: int) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / ACTIVE_NAME
        tmp = path.with_suffix(".tmp")
        tmp.write_text(str(count), encoding="utf-8")
        os.replace(tmp, path)

    def read_active(self) -> int:
        path = self._dir / ACTIVE_NAME
        if not path.is_file():
            return 0
        try:
            return max(0, int(path.read_text(encoding="utf-8").strip()))
        except (ValueError, OSError):
            return 1  # unknown: assume work is still running


def wait_for_drain(
    marker: DrainMarker,
    *,
    timeout_s: float,
    poll_s: float = 1.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Set the marker, then wait until no runs are active. False means the timeout was reached."""
    marker.set()
    deadline = clock() + timeout_s
    while marker.read_active() > 0:
        if clock() >= deadline:
            return False
        sleep(poll_s)
    return True
