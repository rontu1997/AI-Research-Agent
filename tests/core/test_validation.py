from core.errors import ErrorCode
from core.validation import validate_topic


def test_empty_topic_is_rejected() -> None:
    result = validate_topic("   \n\t ")
    assert not result.ok
    assert result.error is ErrorCode.INPUT_INVALID


def test_topic_is_trimmed() -> None:
    result = validate_topic("  Urban heat islands  ")
    assert result.ok
    assert result.topic == "Urban heat islands"


def test_500_characters_accepted_and_501_rejected() -> None:
    assert validate_topic("a" * 500).ok
    too_long = validate_topic("a" * 501)
    assert not too_long.ok
    assert too_long.error is ErrorCode.INPUT_INVALID


def test_length_counts_unicode_characters_not_bytes() -> None:
    # 500 two-byte Latin characters is still 500 characters.
    assert validate_topic("é" * 500).ok


def test_long_non_latin_topic_is_rejected_as_unsupported_language() -> None:
    result = validate_topic("भारत में कृत्रिम बुद्धिमत्ता का रोजगार पर प्रभाव क्या है")
    assert not result.ok
    assert result.error is ErrorCode.LANGUAGE_UNSUPPORTED


def test_short_non_latin_proper_noun_is_accepted_with_a_warning() -> None:
    result = validate_topic("भारत AI")
    assert result.ok
    assert "NON_LATIN_SHORT" in result.warnings


def test_plain_english_topic_has_no_warnings() -> None:
    result = validate_topic("Impact of AI on the Indian job market")
    assert result.ok
    assert result.warnings == []


def test_accented_latin_topic_is_accepted_with_a_notice() -> None:
    result = validate_topic("Impacto de la inteligencia artificial en el empleo español")
    assert result.ok
    assert "LATIN_NON_ENGLISH_POSSIBLE" in result.warnings


def test_boundary_nineteen_non_latin_letters_is_accepted() -> None:
    # Fewer than 20 alphabetic characters: the heuristic does not reject.
    assert validate_topic("ж" * 19).ok
    assert not validate_topic("ж" * 20).ok
