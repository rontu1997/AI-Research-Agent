"""Verifier scorecard from a labeled fixture file (PRD FR-35, §2.6).

    uv run python -m eval.scorecard path/to/fixtures.jsonl

Each line is JSON: ``{"label": "supported"|"unsupported", "verdict": "supported"|"uncertain"|
"unsupported", "adversarial": bool?, "injection": bool?, "synthetic": bool?}``. The script reports
counts and Wilson intervals only. It never invents labels: a file containing synthetic rows is
flagged so its numbers are never mistaken for a sealed-set result.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from eval.stats import wilson_interval


def score_verifier_file(path: Path | str) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    negatives = [r for r in rows if r["label"] == "unsupported"]
    positives = [r for r in rows if r["label"] == "supported"]
    false_accepts = [r for r in negatives if r["verdict"] == "supported"]
    false_rejects = [r for r in positives if r["verdict"] != "supported"]
    injections = [r for r in rows if r.get("injection")]
    return {
        "rows": len(rows),
        "negatives": len(negatives),
        "adversarial_negatives": sum(1 for r in negatives if r.get("adversarial")),
        "false_accepts": len(false_accepts),
        "false_accept_wilson_95": wilson_interval(len(false_accepts), len(negatives)),
        "positives": len(positives),
        "false_rejects": len(false_rejects),
        "false_reject_wilson_95": wilson_interval(len(false_rejects), len(positives)),
        "injection_pairs": len(injections),
        "injection_false_accepts": sum(1 for r in injections if r["verdict"] == "supported"),
        "synthetic": any(r.get("synthetic") for r in rows),
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: python -m eval.scorecard FIXTURES.jsonl", file=sys.stderr)
        return 2
    card = score_verifier_file(args[0])
    print(json.dumps(card, indent=2))
    if card["synthetic"]:
        print(
            "WARNING: file contains synthetic rows; this is not a sealed-set result.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
