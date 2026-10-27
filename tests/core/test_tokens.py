import math

from hypothesis import given
from hypothesis import strategies as st

from core.tokens import estimate_tokens


def test_estimate_is_ceiling_of_chars_over_ratio() -> None:
    assert estimate_tokens("a" * 7) == 2
    assert estimate_tokens("a" * 8) == math.ceil(8 / 3.5)
    assert estimate_tokens("") == 0


def test_ratio_is_configurable() -> None:
    assert estimate_tokens("a" * 8, chars_per_token=4.0) == 2


@given(st.text(max_size=500))
def test_estimate_never_decreases_when_text_grows(text: str) -> None:
    assert estimate_tokens(text + "x") >= estimate_tokens(text)
