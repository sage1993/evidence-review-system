import pytest

from evidence_review.llm_layer.numeric_grammar import (
    UnsupportedNumericSyntax,
    reject_unsupported_numeric_syntax,
    scan_numeric_tokens,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("값은 0이다.", ("0",)),
        ("값은 -12이다.", ("-12",)),
        ("값은 +3이다.", ("+3",)),
        ("면적은 1,234이다.", ("1,234",)),
        ("비율은 12.50%이다.", ("12.50%",)),
        ("A는 10이고 B는 20이다.", ("10", "20")),
        ("치수는 0.5미터이다.", ("0.5",)),
    ],
)
def test_scan_supported_tokens(text: str, expected: tuple[str, ...]) -> None:
    tokens = scan_numeric_tokens(text)
    assert tuple(token.text for token in tokens) == expected
    reject_unsupported_numeric_syntax(text, tokens)


def test_scanner_returns_original_spans() -> None:
    text = "접면 비율은 9.375%이다."
    token = scan_numeric_tokens(text)[0]

    assert token.text == "9.375%"
    assert text[token.start : token.end] == "9.375%"


@pytest.mark.parametrize("text", ["R1", "DOC-A", "RUN-ABC", "A12B"])
def test_scanner_does_not_extract_inside_identifiers(text: str) -> None:
    tokens = scan_numeric_tokens(text)
    assert tokens == ()
    reject_unsupported_numeric_syntax(text, tokens)


@pytest.mark.parametrize(
    "text",
    [
        "값은 1e3이다.",
        "값은 1E-3이다.",
        "값은 .5이다.",
        "값은 1_000이다.",
        "값은 ½이다.",
        "값은 １２３이다.",
        "값은 12,34이다.",
        "값은 1,23,456이다.",
        "값은 10²이다.",
        "값은 ⑩이다.",
    ],
)
def test_unsupported_numeric_syntax_is_rejected(text: str) -> None:
    tokens = scan_numeric_tokens(text)
    with pytest.raises(UnsupportedNumericSyntax, match="UNSUPPORTED_NUMERIC_SYNTAX"):
        reject_unsupported_numeric_syntax(text, tokens)


def test_unsupported_error_reports_first_exact_span() -> None:
    text = "값은 1e3이고 .5이다."
    tokens = scan_numeric_tokens(text)

    with pytest.raises(
        UnsupportedNumericSyntax,
        match=r"UNSUPPORTED_NUMERIC_SYNTAX at 3:6: 1e3",
    ):
        reject_unsupported_numeric_syntax(text, tokens)
