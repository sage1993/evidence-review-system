from math import inf, nan
from pathlib import Path

import pytest

from ansim_review.canonical_json import sha256_json
from ansim_review.parsing.odl_adapter import load_raw_elements
from ansim_review.parsing.odl_source import (
    ParserPageDimensionsResult,
    parser_page_dimensions,
)


def test_load_raw_elements_assigns_stable_page_ordered_ids() -> None:
    fixture = Path("tests/golden/fixtures/minimal-parser-output.json")

    first = load_raw_elements(fixture, document_id="LAW1", revision_id="LAW1-abc123")
    second = load_raw_elements(fixture, document_id="LAW1", revision_id="LAW1-abc123")

    assert first == second
    assert [item.page_number for item in first] == [1, 1, 2]
    assert [item.element_id for item in first] == [
        "LAW1-LAW1-abc123-P0001-E00001",
        "LAW1-LAW1-abc123-P0001-E00002",
        "LAW1-LAW1-abc123-P0002-E00001",
    ]
    assert [item.parser_order for item in first] == [1, 2, 0]
    assert [item.element_type for item in first] == ["list", "list item", "paragraph"]
    assert first[1].raw_payload_hash == sha256_json(first[1].raw_payload)
    assert first[1].source_path == ("kids", 1, "list items", 0)


def test_missing_parser_dimensions_are_absent_not_a4() -> None:
    assert parser_page_dimensions({"number of pages": 1}, 1) == (
        ParserPageDimensionsResult("ABSENT", None, None)
    )


def test_valid_parser_dimensions_are_preserved() -> None:
    payload = {"pages": [{"page_number": 1, "width": 1000.0, "height": 700.0}]}
    assert parser_page_dimensions(payload, 1) == ParserPageDimensionsResult(
        "VALID", 1000.0, 700.0
    )


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (0.0, 700.0),
        (-1.0, 700.0),
        (1000.0, 0.0),
        (1000.0, -1.0),
        (nan, 700.0),
        (inf, 700.0),
        (True, 700.0),
        ("1000", 700.0),
    ],
)
def test_invalid_parser_dimensions_are_not_missing(
    width: object,
    height: object,
) -> None:
    payload = {"pages": [{"page_number": 1, "width": width, "height": height}]}
    assert parser_page_dimensions(payload, 1).state == "INVALID"


def test_partial_parser_dimensions_are_invalid() -> None:
    payload = {"pages": [{"page_number": 1, "width": 1000.0}]}
    assert parser_page_dimensions(payload, 1).state == "INVALID"
