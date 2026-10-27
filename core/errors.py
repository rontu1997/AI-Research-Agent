"""Error taxonomy (ARCH §6.4) and provider exception types (ARCH §6.5)."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    INPUT_INVALID = "INPUT_INVALID"
    LANGUAGE_UNSUPPORTED = "LANGUAGE_UNSUPPORTED"
    BUSY = "BUSY"
    SESSION_ACTIVE = "SESSION_ACTIVE"
    SERVICE_PAUSED = "SERVICE_PAUSED"
    CONFIG_INVALID = "CONFIG_INVALID"
    PLAN_TOO_NARROW = "PLAN_TOO_NARROW"
    NO_EVIDENCE = "NO_EVIDENCE"
    SEARCH_FAILED = "SEARCH_FAILED"
    MODEL_FAILED = "MODEL_FAILED"
    VERIFIER_FAILED = "VERIFIER_FAILED"
    INTEGRITY_FAILED = "INTEGRITY_FAILED"
    BUDGET_STOP = "BUDGET_STOP"
    TIMEOUT = "TIMEOUT"
    ABANDONED = "ABANDONED"
    NOT_FOUND = "NOT_FOUND"


class ProviderError(Exception):
    """Base class. Adapters raise only subclasses of this (ARCH §6.5)."""


class ProviderAuthError(ProviderError):
    """HTTP 401 or 403: bad or missing credentials. Never retried."""


class ProviderRateLimit(ProviderError):
    """HTTP 429. May carry the provider's Retry-After value in seconds."""

    def __init__(self, retry_after_s: float | None = None) -> None:
        super().__init__("rate limited")
        self.retry_after_s = retry_after_s


class ProviderTimeout(ProviderError):
    """Connection or read timeout."""


class ProviderServerError(ProviderError):
    """HTTP 5xx or a dropped connection."""


class ProviderBadRequest(ProviderError):
    """HTTP 400: the request itself is invalid. Never retried."""


class ContextTruncated(ProviderBadRequest):
    """The server processed far less of the prompt than was sent (a small context window).

    Verifying partly read evidence is unsafe, so this is never retried and the run fails closed.
    """


class SchemaViolation(ProviderError):
    """The model returned output that does not match the required schema."""


class ContentRefused(ProviderError):
    """The model declined to answer. Never retried."""


class BudgetStop(Exception):
    """A reservation was refused: the call would exceed the run's modeled budget."""


class DeadlineExceeded(Exception):
    """The run's wall-clock limit was reached."""


class RunCancelled(Exception):
    """The run was abandoned (heartbeat lost) and must stop issuing calls."""


class PipelineFailure(Exception):
    """A terminal failure inside the pipeline, carrying its error code."""

    def __init__(self, code: ErrorCode, detail: str = "") -> None:
        super().__init__(code.value if not detail else f"{code.value}: {detail}")
        self.code = code
        self.detail = detail


class ProviderCircuitOpen(ProviderServerError):
    """The per-provider circuit breaker is open: fail fast without calling the provider."""
