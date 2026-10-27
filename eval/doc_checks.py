"""Traceability checks between the approved documents (rules.md §2.2).

    uv run python -m eval.doc_checks

Reports which PRD requirement, decision and placeholder IDs the tracker never mentions.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_KINDS = {
    "FR": re.compile(r"^\|\s*(FR-\d+)\s*\|", re.MULTILINE),
    "NFR": re.compile(r"^\|\s*(NFR-\d+)\s*\|", re.MULTILINE),
    "D": re.compile(r"^\|\s*(D-\d+)\s*\|", re.MULTILINE),
    "PL": re.compile(r"^\|\s*(PL-\d+)\s*\|", re.MULTILINE),
}


def coverage_report(prd: Path, tracker: Path) -> dict[str, dict[str, Any]]:
    prd_text = prd.read_text(encoding="utf-8")
    tracker_text = tracker.read_text(encoding="utf-8")
    report: dict[str, dict[str, Any]] = {}
    for kind, pattern in _KINDS.items():
        ids = sorted(set(pattern.findall(prd_text)))
        missing = [i for i in ids if not re.search(rf"\b{re.escape(i)}\b", tracker_text)]
        report[kind] = {"total": len(ids), "missing": missing}
    return report


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    report = coverage_report(root / "prd.md", root / "tracker.md")
    print(json.dumps(report, indent=2))
    return 1 if any(v["missing"] for v in report.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
