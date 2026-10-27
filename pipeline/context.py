"""Per-run wiring: budgeted, guarded access to the search provider and both models (ARCH §10.2)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from adapters.base import Block, LLMClient, LLMResult, SearchProvider, T
from core.capacity import CallGuard
from core.models import SearchResponse
from core.settings import ModeConfig, PriceSheet
from core.tokens import DEFAULT_CHARS_PER_TOKEN

Role = Literal["writer", "verifier"]

SEARCH_TIMEOUT_S = 15.0
LLM_TIMEOUT_S = {"planner": 30.0, "writer": 90.0, "verifier": 30.0, "scan": 30.0, "repair": 60.0}


@dataclass
class RunContext:
    cfg: ModeConfig
    prices: PriceSheet
    guard: CallGuard
    search: SearchProvider
    writer: LLMClient
    verifier: LLMClient
    writer_model: str
    verifier_model: str
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN
    writer_timeout_factor: float = 1.0
    verifier_timeout_factor: float = 1.0

    # -- model calls -------------------------------------------------------------------------

    def estimate_llm_cost(self, role: Role, input_cap: int, max_output_tokens: int) -> float:
        model = self.writer_model if role == "writer" else self.verifier_model
        return (
            self.prices.token_cost(model, input_cap, max_output_tokens) * self.prices.safety_factor
        )

    def generate(
        self,
        *,
        stage: str,
        role: Role,
        system: str,
        blocks: Sequence[Block],
        schema: type[T],
        max_output_tokens: int,
        input_cap: int,
        reservation_stage: str | None = None,
        temperature: float = 0.0,
    ) -> T:
        """One guarded model call. ``stage`` names the timeout and telemetry; ``reservation_stage``
        names the budget bucket (defaults to ``stage``)."""
        client = self.writer if role == "writer" else self.verifier
        model = self.writer_model if role == "writer" else self.verifier_model
        factor = self.writer_timeout_factor if role == "writer" else self.verifier_timeout_factor
        timeout = (
            LLM_TIMEOUT_S.get(stage, 30.0) * factor
        )  # the guard still caps it at the time left

        def call(remaining_s: float) -> LLMResult[T]:
            return client.generate(
                system=system,
                blocks=blocks,
                schema=schema,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                timeout_s=remaining_s,
            )

        def actual(result: LLMResult[T]) -> float | None:
            if result.input_tokens is None or result.output_tokens is None:
                return None
            return self.prices.token_cost(model, result.input_tokens, result.output_tokens)

        result = self.guard.call(
            stage=reservation_stage or stage,
            provider=role,
            fn=call,
            est_cost_usd=self.estimate_llm_cost(role, input_cap, max_output_tokens),
            actual_cost=actual,
            per_call_timeout_s=timeout,
            retry_on_schema=True,
        )
        return result.parsed

    # -- search ------------------------------------------------------------------------------

    def search_call(self, query: str, *, max_results: int, want_extracted: bool) -> SearchResponse:
        def call(remaining_s: float) -> SearchResponse:
            return self.search.search(
                query, max_results=max_results, want_extracted=want_extracted, timeout_s=remaining_s
            )

        return self.guard.call(
            stage="search",
            provider="search",
            fn=call,
            est_cost_usd=self.prices.search_per_call * self.prices.safety_factor,
            actual_cost=lambda r: (
                self.prices.search_per_call
                if r.billed_units is None
                else r.billed_units * self.prices.search_per_call
            ),
            per_call_timeout_s=SEARCH_TIMEOUT_S,
        )
