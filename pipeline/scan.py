"""Coverage scan of non-claim sentences (PRD FR-34; ARCH §5.7).

Interpretation and transition sentences must not smuggle in facts. The scan asks the verifier
model which of them contain a material factual statement. A missing answer counts as flagged, and
so does any sentence that does not fit the scan's input cap (it is never published unchecked).
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from adapters.base import Block
from core.errors import ErrorCode, PipelineFailure, ProviderError
from core.models import ScanOutput
from core.tokens import estimate_tokens
from pipeline.context import RunContext
from pipeline.prompts import SCAN_SYSTEM

PROMPT_MARGIN_TOKENS = 100


def scan_sentences(
    ctx: RunContext,
    sentences: Sequence[tuple[str, str]],
    *,
    reservation_stage: str | None = None,
) -> set[str]:
    """Return the refs of sentences that must be removed (flagged, unanswered or over the cap)."""
    if not sentences:
        return set()
    cpt = ctx.chars_per_token
    budget = ctx.cfg.scan_input_cap - estimate_tokens(SCAN_SYSTEM, cpt) - PROMPT_MARGIN_TOKENS
    payload: list[dict[str, str]] = []
    skipped: set[str] = set()
    used = 0
    for ref, text in sentences:
        entry = {"ref": ref, "text": text}
        cost = estimate_tokens(json.dumps(entry, ensure_ascii=False), cpt)
        if used + cost > budget:
            skipped.add(ref)
            continue
        used += cost
        payload.append(entry)
    if not payload:
        return skipped
    try:
        out = ctx.generate(
            stage="scan",
            role="verifier",
            system=SCAN_SYSTEM,
            blocks=[Block("sentences", json.dumps(payload, ensure_ascii=False))],
            schema=ScanOutput,
            max_output_tokens=ctx.cfg.scan_max_output,
            input_cap=ctx.cfg.scan_input_cap,
            reservation_stage=reservation_stage,
        )
    except ProviderError as err:
        raise PipelineFailure(ErrorCode.VERIFIER_FAILED, type(err).__name__) from err
    wanted = {entry["ref"] for entry in payload}
    clear = {item.sentence_ref for item in out.results if not item.contains_material_fact}
    return (wanted - clear) | skipped
