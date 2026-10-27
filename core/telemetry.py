"""Typed allowlist telemetry (PRD NFR-12; ARCH §11).

Only named events with named fields are written, and string values must look like short codes.
Topics, URLs, passages, claim text and credentials cannot be logged because no field accepts them.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ALLOWED_EVENTS = frozenset(
    {
        "run.started",
        "run.finished",
        "run.abandoned",
        "run.rejected",
        "startup.check",
        "stage.finished",
        "provider.call",
        "provider.breaker",
        "spend.alert",
        "spend.stop",
        "service.paused",
        "service.drain",
        "ui.evidence_opened",
        "ui.feedback",
        "ui.export",
    }
)
ALLOWED_FIELDS = frozenset(
    {
        "run_id",
        "mode",
        "status",
        "stage",
        "error_code",
        "provider",
        "elapsed_ms",
        "cost_usd",
        "attempt",
        "supported_claims",
        "usable_sources",
        "unique_domains",
        "repair_used",
        "replan_used",
        "count",
        "vote",
    }
)
_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


class Telemetry:
    def __init__(self, log_dir: Path | str, *, retention_days: int = 7) -> None:
        self._dir = Path(log_dir)
        self._retention = retention_days
        self._lock = threading.Lock()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._purge()

    def emit(self, event: str, **fields: object) -> None:
        if event not in ALLOWED_EVENTS:
            return
        record: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "event": event,
        }
        for name, value in fields.items():
            if name in ALLOWED_FIELDS and _acceptable(value):
                record[name] = value
        line = json.dumps(record, separators=(",", ":"))
        path = self._dir / f"events-{date.today():%Y%m%d}.jsonl"
        with self._lock, path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _purge(self) -> None:
        cutoff = datetime.combine(date.today(), datetime.min.time()) - timedelta(
            days=self._retention
        )
        for path in self._dir.glob("events-*.jsonl"):
            try:
                day = datetime.strptime(path.stem[len("events-") :], "%Y%m%d")
            except ValueError:
                continue
            if day < cutoff:
                path.unlink(missing_ok=True)


def _acceptable(value: object) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    return isinstance(value, str) and bool(_CODE.match(value))
