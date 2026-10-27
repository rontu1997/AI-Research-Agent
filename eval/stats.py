"""Interval statistics for the evaluation gates (PRD §2.6, §10.2, §11.3).

Seeded and dependency-free.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

Z_95 = 1.959963984540054


def wilson_interval(successes: int, trials: int, z: float = Z_95) -> tuple[float, float]:
    if successes < 0 or trials < 0 or successes > trials:
        raise ValueError("successes must be between 0 and trials")
    if trials == 0:
        return 0.0, 1.0
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("no data")
    position = q * (len(sorted_values) - 1)
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return sorted_values[low]
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def percentile_bootstrap(
    data: Sequence[float], q: float, *, resamples: int = 10_000, seed: int = 0, level: float = 0.95
) -> tuple[float, float]:
    """Percentile-bootstrap interval for the q-quantile of ``data``."""
    rng = random.Random(seed)
    n = len(data)
    estimates = sorted(
        _quantile(sorted(rng.choice(data) for _ in range(n)), q) for _ in range(resamples)
    )
    tail = (1 - level) / 2
    return _quantile(estimates, tail), _quantile(estimates, 1 - tail)


def cluster_bootstrap_lower(
    clusters: Sequence[tuple[int, int]],
    *,
    resamples: int = 10_000,
    seed: int = 0,
    level: float = 0.95,
) -> float:
    """Lower bound of the pooled supported rate, resampling whole reports with replacement.

    Each cluster is ``(supported_claims, reviewed_claims)`` for one report.
    """
    rng = random.Random(seed)
    n = len(clusters)
    rates = []
    for _ in range(resamples):
        picked = [clusters[rng.randrange(n)] for _ in range(n)]
        reviewed = sum(r for _, r in picked)
        rates.append(sum(s for s, _ in picked) / reviewed if reviewed else 0.0)
    rates.sort()
    return _quantile(rates, (1 - level) / 2)
