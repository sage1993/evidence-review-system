import pytest

from ansim_review.llm_layer.numeric_grammar import scan_numeric_tokens


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("값은 0이다.", ("0",)),
        ("값은 -12이다.", ("-12",)),
        ("값은 +3이다.", ("+3",)),
        ("면적은 1,234이다.", ("1,234",)),
        ("비율은 12.50%이다.", ("12.50%",)),
        ("A는 10이고 B는 20이다.", ("10", "20")),
        ("치수는 0.5m이다.", ("0.5",)),
    ],
)
def test_scan_supported_tokens(text: str, expected: tuple[str, ...]) -> None:
    assert tuple(token.text for token in scan_numeric_tokens(text)) == expected


def test_scanner_returns_original_spans() -> None:
    text = "접면 비율은 9.375%이다."
    token = scan_numeric_tokens(text)[0]

    assert token.text == "9.375%"
    assert text[token.start : token.end] == "9.375%"


@pytest.mark.parametrize("text", ["R1", "DOC-A", "RUN-ABC", "A12B"])
def test_scanner_does_not_extract_inside_identifiers(text: str) -> None:
    assert scan_numeric_tokens(text) == ()
