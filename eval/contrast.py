"""WCAG 2.x contrast checks over the UI design tokens (design.md §5.2, rule DR-12).

Run `uv run python -m eval.contrast` to print every pair; the exit code is 1 if any pair fails.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping

TEXT = 4.5
NON_TEXT = 3.0

# (foreground token, background token, required ratio)
REQUIRED_PAIRS: tuple[tuple[str, str, float], ...] = (
    ("text", "bg", TEXT),
    ("text", "surface", TEXT),
    ("text2", "bg", TEXT),
    ("text2", "surface", TEXT),
    ("primary", "bg", TEXT),
    ("primary", "surface", TEXT),
    ("primary_text", "primary", TEXT),
    ("primary_text", "primary_hover", TEXT),
    ("primary_text", "primary_active", TEXT),
    ("text", "surface_hover", TEXT),
    ("text2", "surface_hover", TEXT),
    ("primary", "surface_hover", TEXT),
    ("border", "bg", NON_TEXT),
    ("border", "surface", NON_TEXT),
    ("border", "surface_hover", NON_TEXT),
    ("ok_fg", "ok_bg", TEXT),
    ("warn_fg", "warn_bg", TEXT),
    ("err_fg", "err_bg", TEXT),
    ("info_fg", "info_bg", TEXT),
    ("ok_bd", "bg", NON_TEXT),
    ("warn_bd", "bg", NON_TEXT),
    ("err_bd", "bg", NON_TEXT),
    ("info_bd", "bg", NON_TEXT),
)


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def failing_pairs(tokens: Mapping[str, str]) -> list[tuple[str, str, float, float]]:
    """Pairs below their threshold: (foreground, background, ratio, required)."""
    bad: list[tuple[str, str, float, float]] = []
    for fg, bg, need in REQUIRED_PAIRS:
        ratio = contrast_ratio(tokens[fg], tokens[bg])
        if ratio < need:
            bad.append((fg, bg, round(ratio, 2), need))
    return bad


def main() -> int:
    from ui.theme import LIGHT

    for fg, bg, need in REQUIRED_PAIRS:
        ratio = contrast_ratio(LIGHT[fg], LIGHT[bg])
        print(
            f"{fg:>14} on {bg:<14} {ratio:6.2f} (need {need}) {'ok' if ratio >= need else 'FAIL'}"
        )
    return 1 if failing_pairs(LIGHT) else 0


if __name__ == "__main__":
    sys.exit(main())
