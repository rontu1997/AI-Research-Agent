"""Provider adapter contracts (ARCH §6.5). The pipeline depends only on these Protocols."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

from core.models import SearchResponse

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Block:
    """One labeled block of untrusted data passed to a model (ARCH §5.5).

    The label names the block; the content is JSON text built by code, never free-form prose.
    """

    label: str
    content: str


@dataclass(frozen=True)
class LLMResult(Generic[T]):
    parsed: T
    model_id: str
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: str = "stop"


class SearchProvider(Protocol):
    def search(
        self, query: str, *, max_results: int, want_extracted: bool, timeout_s: float
    ) -> SearchResponse: ...


class LLMClient(Protocol):
    def generate(
        self,
        *,
        system: str,
        blocks: Sequence[Block],
        schema: type[T],
        max_output_tokens: int,
        temperature: float,
        timeout_s: float,
    ) -> LLMResult[T]: ...


@dataclass
class Providers:
    """The three external providers a run needs, with the model IDs used for pricing."""

    search: SearchProvider
    writer: LLMClient
    verifier: LLMClient
    writer_model: str
    verifier_model: str
