from __future__ import annotations

import pytest

from evidence_review.llm_layer.numeric_grammar import (
    reject_unsupported_numeric_syntax,
    scan_numeric_tokens,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("천장높이는 2.4m 이상이다.", ("2.4",)),
        ("복도 폭은 1500mm이다.", ("1500",)),
        ("이격거리는 300cm이다.", ("300",)),
        ("거리는 0.25km이다.", ("0.25",)),
        ("전용면적은 49.91m²이다.", ("49.91",)),
    ],
)
def test_scanner_accepts_attached_measurement_units(
    text: str,
    expected: tuple[str, ...],
) -> None:
    tokens = scan_numeric_tokens(text)

    assert tuple(token.text for token in tokens) == expected
    reject_unsupported_numeric_syntax(text, tokens)


def test_attached_unit_support_does_not_turn_identifiers_into_numbers() -> None:
    text = "3F A12B RUN-123 R1"

    tokens = scan_numeric_tokens(text)

    assert tokens == ()
    reject_unsupported_numeric_syntax(text, tokens)
