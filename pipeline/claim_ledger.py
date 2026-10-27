"""Claim ledger normalization and placement rules (PRD §6.3, FR-08; ARCH §5.6).

The writer's draft is untrusted structure. This module makes it deterministic: unique claim IDs,
known facets, a cap on claims, every claim printed exactly once in its own section, and the
per-mode limits on summary and conclusion claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models import (
    SECTION_ORDER,
    ClaimRecord,
    DraftSentence,
    LedgerDraft,
    Plan,
    SectionName,
)
from core.settings import ModeConfig
from core.tokens import DEFAULT_CHARS_PER_TOKEN


@dataclass
class NormalizedLedger:
    claims: list[ClaimRecord]
    rejected: dict[str, str]
    sections: dict[SectionName, list[DraftSentence]]
    notes: list[str] = field(default_factory=list)


def normalize_draft(draft: LedgerDraft, plan: Plan, cfg: ModeConfig) -> NormalizedLedger:
    facet_ids = {f.facet_id for f in plan.facets}
    max_claim_chars = int(cfg.claim_text_allowance * DEFAULT_CHARS_PER_TOKEN)
    claims: list[ClaimRecord] = []
    rejected: dict[str, str] = {}
    seen: set[str] = set()
    notes: list[str] = []

    for draft_claim in draft.claims:
        if draft_claim.claim_id in seen:
            rejected[draft_claim.claim_id] = "DUPLICATE_ID"
            continue
        if draft_claim.facet_id not in facet_ids:
            rejected[draft_claim.claim_id] = "UNKNOWN_FACET"
            continue
        if len(draft_claim.text) > max_claim_chars:
            rejected[draft_claim.claim_id] = "CLAIM_TOO_LONG"
            continue
        if len(claims) >= cfg.max_claims:
            rejected[draft_claim.claim_id] = "OVER_CAP"
            continue
        seen.add(draft_claim.claim_id)
        claims.append(
            ClaimRecord(
                claim_id=draft_claim.claim_id,
                text=draft_claim.text,
                facet_id=draft_claim.facet_id,
                section=draft_claim.section,
                evidence=list(draft_claim.evidence),
            )
        )

    by_id = {c.claim_id: c for c in claims}
    sections: dict[SectionName, list[DraftSentence]] = {name: [] for name in SECTION_ORDER}
    placed: set[str] = set()

    for section in draft.sections:
        for sentence in section.sentences:
            if sentence.type == "claim":
                cid = sentence.claim_id
                if cid is None or cid not in by_id or cid in placed:
                    continue
                placed.add(cid)
                target = by_id[cid].section
                if target != section.section:
                    notes.append(f"moved {cid} to {target}")
                sections[target].append(DraftSentence(type="claim", claim_id=cid))
            else:
                text = (sentence.text or "").strip()
                if not text:
                    continue
                sections[section.section].append(
                    DraftSentence(type=sentence.type, text=text, refs=list(sentence.refs))
                )

    for claim in claims:
        if claim.claim_id not in placed:
            notes.append(f"placed {claim.claim_id} in {claim.section}")
            sections[claim.section].append(DraftSentence(type="claim", claim_id=claim.claim_id))

    _move_overflow(sections, "summary", cfg.summary_max_claims, notes)
    _move_overflow(sections, "conclusion", cfg.conclusion_max_claims, notes)
    return NormalizedLedger(claims=claims, rejected=rejected, sections=sections, notes=notes)


def _move_overflow(
    sections: dict[SectionName, list[DraftSentence]],
    name: SectionName,
    limit: int,
    notes: list[str],
) -> None:
    kept: list[DraftSentence] = []
    count = 0
    for sentence in sections[name]:
        if sentence.type == "claim":
            count += 1
            if count > limit:
                notes.append(f"moved overflow {sentence.claim_id} from {name} to findings")
                sections["findings"].append(sentence)
                continue
        kept.append(sentence)
    sections[name] = kept
