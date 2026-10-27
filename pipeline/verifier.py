"""Independent passage-support verifier (PRD FR-19; ARCH §5.8, §10.4).

The verifier sees only the claim, its quotes and the passages they came from. Batches are sized by
tokens so the worst case matches the startup call-graph check. A missing verdict is ``unsupported``
(fail closed); a verifier outage fails the run rather than letting unchecked claims through.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor

from adapters.base import Block
from core.capacity import claims_per_verifier_batch
from core.errors import ErrorCode, PipelineFailure, ProviderError
from core.models import ClaimRecord, SourceRecord, Verdict, VerifierOutput
from core.settings import ModeConfig
from core.tokens import DEFAULT_CHARS_PER_TOKEN
from pipeline.context import RunContext
from pipeline.prompts import VERIFIER_SYSTEM

_RANK = {Verdict.UNSUPPORTED: 0, Verdict.UNCERTAIN: 1, Verdict.SUPPORTED: 2}
Verdicts = dict[str, tuple[Verdict, str]]


class VerifierCache:
    """In-run cache so identical claim/evidence pairs are verified once (never persisted)."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[Verdict, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> tuple[Verdict, str] | None:
        with self._lock:
            return self._items.get(key)

    def put(self, key: str, value: tuple[Verdict, str]) -> None:
        with self._lock:
            self._items[key] = value


def _passage_text(claim: ClaimRecord, sources: Mapping[int, SourceRecord]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for ref in claim.evidence:
        source = sources.get(ref.citation_id)
        text = ""
        if source is not None:
            text = next((p.text for p in source.passages if p.passage_id == ref.passage_id), "")
        items.append({"passage_id": ref.passage_id, "quote": ref.quote, "passage_text": text})
    return items


def _cache_key(claim: ClaimRecord, evidence: list[dict[str, str]]) -> str:
    raw = json.dumps([claim.text, evidence], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_batches(
    claims: Sequence[ClaimRecord],
    sources: Mapping[int, SourceRecord],
    cfg: ModeConfig,
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
) -> list[list[ClaimRecord]]:
    """Order-preserving batches no larger than the token-derived worst case."""
    del sources  # sizes are bounded by the worst case, not the actual text, for a stable bound
    per_batch = claims_per_verifier_batch(cfg, chars_per_token)
    return [list(claims[i : i + per_batch]) for i in range(0, len(claims), per_batch)]


def _verify_batch(
    ctx: RunContext,
    batch: list[ClaimRecord],
    sources: Mapping[int, SourceRecord],
    reservation_stage: str | None,
) -> Verdicts:
    payload = [
        {"claim_id": c.claim_id, "claim": c.text, "evidence": _passage_text(c, sources)}
        for c in batch
    ]
    try:
        out = ctx.generate(
            stage="verifier",
            role="verifier",
            system=VERIFIER_SYSTEM,
            blocks=[Block("claims", json.dumps(payload, ensure_ascii=False))],
            schema=VerifierOutput,
            max_output_tokens=ctx.cfg.verifier_max_output,
            input_cap=ctx.cfg.verifier_input_cap,
            reservation_stage=reservation_stage,
        )
    except ProviderError as err:
        raise PipelineFailure(ErrorCode.VERIFIER_FAILED, type(err).__name__) from err

    wanted = {c.claim_id for c in batch}
    result: Verdicts = {}
    for item in out.results:
        if item.claim_id not in wanted:
            continue
        previous = result.get(item.claim_id)
        if previous is None or _RANK[item.verdict] < _RANK[previous[0]]:
            result[item.claim_id] = (item.verdict, item.reason[:300])
    for claim_id in wanted - result.keys():
        result[claim_id] = (Verdict.UNSUPPORTED, "No verdict returned.")
    return result


def verify_claims(
    ctx: RunContext,
    claims: Sequence[ClaimRecord],
    sources: Mapping[int, SourceRecord],
    *,
    cache: VerifierCache | None = None,
    reservation_stage: str | None = None,
) -> Verdicts:
    cache = cache if cache is not None else VerifierCache()
    verdicts: Verdicts = {}
    pending: list[ClaimRecord] = []
    keys: dict[str, str] = {}
    for claim in claims:
        key = _cache_key(claim, _passage_text(claim, sources))
        keys[claim.claim_id] = key
        hit = cache.get(key)
        if hit is not None:
            verdicts[claim.claim_id] = hit
        else:
            pending.append(claim)

    batches = build_batches(pending, sources, ctx.cfg, ctx.chars_per_token)
    if batches:
        workers = max(1, min(ctx.cfg.verifier_parallel, len(batches)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for batch_result in pool.map(
                lambda b: _verify_batch(ctx, b, sources, reservation_stage), batches
            ):
                verdicts.update(batch_result)
    for claim in pending:
        cache.put(keys[claim.claim_id], verdicts[claim.claim_id])
    return verdicts
