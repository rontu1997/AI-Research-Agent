"""Claim-ledger drafting (PRD FR-08; ARCH §5.5). One structured writer call over stored passages."""

from __future__ import annotations

import json
from collections.abc import Sequence

from adapters.base import Block
from core.errors import ErrorCode, PipelineFailure, ProviderError
from core.models import EvidenceMode, LedgerDraft, Plan, SourceRecord
from pipeline.context import RunContext
from pipeline.prompts import WRITER_SYSTEM


def passages_block(sources: Sequence[SourceRecord]) -> str:
    items = [
        {
            "citation_id": s.citation_id,
            "passage_id": p.passage_id,
            "source_title": s.title[:120],
            "evidence_mode": s.evidence_mode.value,
            "text": p.text,
        }
        for s in sources
        if s.evidence_mode is not EvidenceMode.METADATA_ONLY
        for p in s.passages
    ]
    return json.dumps(items, ensure_ascii=False)


def draft_ledger(ctx: RunContext, plan: Plan, sources: Sequence[SourceRecord]) -> LedgerDraft:
    plan_block = json.dumps(
        {"facets": [{"facet_id": f.facet_id, "question": f.question} for f in plan.facets]},
        ensure_ascii=False,
    )
    limits = {
        "max_claims": ctx.cfg.max_claims,
        "max_quotes_per_claim": ctx.cfg.max_quotes_per_claim,
        "summary_max_claims": ctx.cfg.summary_max_claims,
        "conclusion_max_claims": ctx.cfg.conclusion_max_claims,
    }
    try:
        return ctx.generate(
            stage="writer",
            role="writer",
            system=WRITER_SYSTEM,
            blocks=[
                Block("plan", plan_block),
                Block("passages", passages_block(sources)),
                Block("limits", json.dumps(limits)),
            ],
            schema=LedgerDraft,
            max_output_tokens=ctx.cfg.writer_max_output,
            input_cap=ctx.cfg.writer_input_cap,
        )
    except ProviderError as err:
        raise PipelineFailure(ErrorCode.MODEL_FAILED, type(err).__name__) from err
