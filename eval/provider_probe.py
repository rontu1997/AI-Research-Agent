"""Supervised probe of the configured live model providers.

rules.md: ask before the first live call.

    uv run python -m eval.provider_probe --yes-call-live-providers

Sends two tiny verification prompts to the writer and to the verifier and reports whether each
returns parseable, schema-valid JSON, whether usage is reported, and whether the model accepts a
supported claim and rejects a contradicted one. It makes 4 model calls and no search call. The flag
exists so nothing is sent by accident. Only exception class names are reported, never messages,
response bodies or credentials.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Sequence
from typing import Any

from adapters.base import Block, LLMClient
from adapters.live import build_live_providers
from core.errors import ProviderError
from core.models import Verdict, VerifierOutput
from core.settings import load_settings_from_environment, startup_problems
from pipeline.prompts import VERIFIER_SYSTEM

PASSAGE = "The pilot launched in March 2024 with 120 bikes at 15 docking stations."
SUPPORTED = (
    "p1",
    "The pilot launched in March 2024 with 120 bikes.",
    "launched in March 2024 with 120 bikes",
)
CONTRADICTED = (
    "p2",
    "The pilot launched in 1999 with 500 bikes.",
    "launched in March 2024 with 120 bikes",
)


def _blocks(claim: tuple[str, str, str]) -> list[Block]:
    claim_id, text, quote = claim
    payload = [
        {
            "claim_id": claim_id,
            "claim": text,
            "evidence": [{"passage_id": "x:p1", "quote": quote, "passage_text": PASSAGE}],
        }
    ]
    return [Block("claims", json.dumps(payload))]


def probe_llm(chat: LLMClient, *, label: str) -> dict[str, Any]:
    report: dict[str, Any] = {
        "label": label,
        "json_parses": True,
        "usage_reported": True,
        "supported_claim_accepted": None,
        "contradicted_claim_rejected": None,
        "elapsed_ms": 0,
        "errors": [],
    }
    started = time.monotonic()
    for claim, key in (
        (SUPPORTED, "supported_claim_accepted"),
        (CONTRADICTED, "contradicted_claim_rejected"),
    ):
        try:
            result = chat.generate(
                system=VERIFIER_SYSTEM,
                blocks=_blocks(claim),
                schema=VerifierOutput,
                max_output_tokens=400,
                temperature=0.0,
                timeout_s=60.0,
            )
        except ProviderError as err:
            report["json_parses"] = False
            report["errors"].append(type(err).__name__)
            continue
        if result.input_tokens is None or result.output_tokens is None:
            report["usage_reported"] = False
        verdicts = {item.claim_id: item.verdict for item in result.parsed.results}
        verdict = verdicts.get(claim[0])
        report[key] = (
            (verdict is Verdict.SUPPORTED)
            if key == "supported_claim_accepted"
            else (verdict is not None and verdict is not Verdict.SUPPORTED)
        )
    report["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    settings = load_settings_from_environment()
    if "--yes-call-live-providers" not in args:
        print(
            "Refusing to call live providers. Re-run with --yes-call-live-providers.",
            file=sys.stderr,
        )
        return 2
    if settings.provider_mode != "live":
        print("Set RESEARCH_PROVIDER_MODE=live (in .env) to probe live providers.", file=sys.stderr)
        return 1
    problems = startup_problems(settings)
    if problems:
        print("Configuration problems: " + ", ".join(problems), file=sys.stderr)
        return 1
    providers = build_live_providers(settings)
    reports = [
        probe_llm(providers.writer, label=f"writer:{providers.writer_model}"),
        probe_llm(providers.verifier, label=f"verifier:{providers.verifier_model}"),
    ]
    print(json.dumps(reports, indent=2))
    healthy = all(
        r["json_parses"] and r["supported_claim_accepted"] and r["contradicted_claim_rejected"]
        for r in reports
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
