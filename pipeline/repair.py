"""One bounded repair pass (PRD FR-17; ARCH §5.9).

Rewrites at most ``repair_max_claims`` failed claims, in drafted order, using only the passages
each one already cited, within ``repair_input_cap`` tokens of prompt. It may not add sources,
passages or claims; anything else is ignored.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from adapters.base import Block
from core.errors import ErrorCode, PipelineFailure, ProviderError
from core.models import ClaimRecord, LedgerDraft, Plan, SourceRecord
from core.tokens import estimate_tokens
from pipeline.context import RunContext
from pipeline.prompts import REPAIR_SYSTEM

PROMPT_MARGIN_TOKENS = 100  # keys, separators and block labels the estimate does not see


def _select_within_cap(
    ctx: RunContext,
    plan_block: str,
    targets: Sequence[ClaimRecord],
    reasons: Mapping[str, str],
    sources: Mapping[int, SourceRecord],
) -> tuple[list[ClaimRecord], list[dict[str, object]], list[dict[str, object]]]:
    """Claims (evidence trimmed to the quote limit) that fit the repair input cap, in order."""
    cpt = ctx.chars_per_token
    budget = (
        ctx.cfg.repair_input_cap
        - estimate_tokens(REPAIR_SYSTEM, cpt)
        - estimate_tokens(plan_block, cpt)
        - PROMPT_MARGIN_TOKENS
    )
    chosen: list[ClaimRecord] = []
    claim_blocks: list[dict[str, object]] = []
    passages: dict[tuple[int, str], dict[str, object]] = {}
    used = 0
    for claim in targets:
        trimmed = claim.model_copy(
            update={"evidence": claim.evidence[: ctx.cfg.max_quotes_per_claim]}
        )
        entry: dict[str, object] = {
            "claim_id": trimmed.claim_id,
            "text": trimmed.text,
            "facet_id": trimmed.facet_id,
            "section": trimmed.section,
            "failure": reasons.get(trimmed.claim_id, "FAILED"),
            "evidence": [e.model_dump() for e in trimmed.evidence],
        }
        new_passages: dict[tuple[int, str], dict[str, object]] = {}
        for ref in trimmed.evidence:
            source = sources.get(ref.citation_id)
            passage = (
                next((p for p in source.passages if p.passage_id == ref.passage_id), None)
                if source
                else None
            )
            key = (ref.citation_id, ref.passage_id)
            if passage is not None and key not in passages:
                new_passages[key] = {
                    "citation_id": ref.citation_id,
                    "passage_id": passage.passage_id,
                    "text": passage.text,
                }
        cost = estimate_tokens(json.dumps(entry, ensure_ascii=False), cpt) + sum(
            estimate_tokens(json.dumps(p, ensure_ascii=False), cpt) for p in new_passages.values()
        )
        if used + cost > budget:
            break  # keep drafted order: later claims are not repaired
        used += cost
        chosen.append(trimmed)
        claim_blocks.append(entry)
        passages.update(new_passages)
    return chosen, claim_blocks, list(passages.values())


def repair_claims(
    ctx: RunContext,
    plan: Plan,
    failed: Sequence[ClaimRecord],
    reasons: Mapping[str, str],
    sources: Mapping[int, SourceRecord],
) -> list[ClaimRecord]:
    """Return repaired copies of failed claims. The caller re-runs every check on them."""
    targets = list(failed)[: ctx.cfg.repair_max_claims]
    if not targets:
        return []

    plan_block = json.dumps(
        {"facets": [{"facet_id": f.facet_id, "question": f.question} for f in plan.facets]},
        ensure_ascii=False,
    )
    chosen, claim_blocks, passages = _select_within_cap(ctx, plan_block, targets, reasons, sources)
    if not chosen:
        return []
    try:
        draft = ctx.generate(
            stage="repair",
            role="writer",
            system=REPAIR_SYSTEM,
            blocks=[
                Block("failed_claims", json.dumps(claim_blocks, ensure_ascii=False)),
                Block("passages", json.dumps(passages, ensure_ascii=False)),
                Block("plan", plan_block),
            ],
            schema=LedgerDraft,
            max_output_tokens=ctx.cfg.repair_max_output,
            input_cap=ctx.cfg.repair_input_cap,
            reservation_stage="repair",
        )
    except ProviderError as err:
        raise PipelineFailure(ErrorCode.MODEL_FAILED, type(err).__name__) from err

    originals = {c.claim_id: c for c in chosen}
    allowed = {
        cid: {(e.citation_id, e.passage_id) for e in c.evidence} for cid, c in originals.items()
    }
    repaired: list[ClaimRecord] = []
    seen: set[str] = set()
    for item in draft.claims:
        original = originals.get(item.claim_id)
        if original is None or item.claim_id in seen:
            continue
        if not item.evidence or any(
            (e.citation_id, e.passage_id) not in allowed[item.claim_id] for e in item.evidence
        ):
            continue
        seen.add(item.claim_id)
        repaired.append(
            ClaimRecord(
                claim_id=original.claim_id,
                text=item.text,
                facet_id=original.facet_id,
                section=original.section,
                evidence=list(item.evidence),
            )
        )
    return repaired
