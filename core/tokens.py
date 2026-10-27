"""The single token estimator (ARCH ADR-013).

Deliberately conservative for English text. The measurement harness compares it with
provider-reported token counts, and the ratio may be changed once at the D-13 checkpoint.
"""

from __future__ import annotations

import math

DEFAULT_CHARS_PER_TOKEN = 3.5

# Shared size limits (PRD §9.2, FR-33). Single source for the pipeline and the cost model.
MAX_PASSAGE_CHARS = 1500
QUOTE_MIN_CHARS = 25
QUOTE_MAX_CHARS = 300


def estimate_tokens(text: str, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN) -> int:
    if not text:
        return 0
    return math.ceil(len(text) / chars_per_token)
