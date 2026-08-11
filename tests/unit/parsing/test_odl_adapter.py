import json
from math import inf, nan
from pathlib import Path

import pytest

from ansim_review.canonical_json import sha256_json
from ansim_review.parsing.odl_adapter import OpenDataLoaderJsonAdapter, load_raw_elements
from ansim_review.parsing.odl_source import (
    ParserPageDimensionsResult,
    parser_page_dimensions,
)
from ansim_review.parsing.parser_registry import ParserContext
from tests.helpers.pdf_fixtures import write_pdf_fixture


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


def _write_parser(
    path: Path,
    *,
    file_name: str,
    page_count: int,
    bbox: tuple[float, float, float, float],
    dimensions: tuple[float, float] | None = None,
) -> Path:
    payload: dict[str, object] = {
        "file name": file_name,
        "number of pages": page_count,
        "kids": [
            {
                "type": "paragraph",
                "page number": 1,
                "bounding box": list(bbox),
                "content": "geometry fixture",
            }
        ],
    }
    if dimensions is not None:
        payload["pages"] = [
            {
                "page_number": 1,
                "width": dimensions[0],
                "height": dimensions[1],
            }
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _parse(source: Path, parser: Path):
    return OpenDataLoaderJsonAdapter().parse(
        ParserContext(source_path=source, parser_artifact_path=parser, options={})
    )


@pytest.mark.parametrize(
    "page_size",
    [
        (595.0, 842.0),
        (842.0, 1191.0),
        (1191.0, 842.0),
        (1000.0, 700.0),
    ],
)
def test_missing_parser_dimensions_follow_source_pdf(
    tmp_path: Path,
    page_size: tuple[float, float],
) -> None:
    source = write_pdf_fixture(tmp_path / "source.pdf", page_sizes=(page_size,))
    parser = _write_parser(
        tmp_path / "source.json",
        file_name=source.name,
        page_count=1,
        bbox=(10.0, 20.0, 100.0, 40.0),
    )

    contribution = _parse(source, parser)

    assert (
        contribution.page_dimensions[0].width,
        contribution.page_dimensions[0].height,
    ) == page_size


def test_a3_landscape_bbox_is_not_rejected_by_a4_bounds(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "drawing.pdf",
        page_sizes=((1191.0, 842.0),),
    )
    parser = _write_parser(
        tmp_path / "drawing.json",
        file_name=source.name,
        page_count=1,
        bbox=(100.0, 100.0, 1100.0, 700.0),
    )

    contribution = _parse(source, parser)

    assert contribution.elements[0].bbox == (100.0, 100.0, 1100.0, 700.0)


def test_parser_dimensions_within_half_point_use_pdf_values(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "custom.pdf",
        page_sizes=((1000.0, 700.0),),
    )
    parser = _write_parser(
        tmp_path / "custom.json",
        file_name=source.name,
        page_count=1,
        bbox=(10.0, 20.0, 100.0, 40.0),
        dimensions=(999.6, 700.4),
    )

    contribution = _parse(source, parser)

    assert (
        contribution.page_dimensions[0].width,
        contribution.page_dimensions[0].height,
    ) == (1000.0, 700.0)


def test_parser_pdf_dimension_mismatch_is_rejected(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "custom.pdf",
        page_sizes=((1000.0, 700.0),),
    )
    parser = _write_parser(
        tmp_path / "custom.json",
        file_name=source.name,
        page_count=1,
        bbox=(10.0, 20.0, 100.0, 40.0),
        dimensions=(998.0, 700.0),
    )

    with pytest.raises(ValueError, match="PARSER_PDF_PAGE_DIMENSIONS_MISMATCH"):
        _parse(source, parser)


def test_invalid_parser_dimension_is_rejected(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "custom.pdf",
        page_sizes=((1000.0, 700.0),),
    )
    parser = _write_parser(
        tmp_path / "custom.json",
        file_name=source.name,
        page_count=1,
        bbox=(10.0, 20.0, 100.0, 40.0),
        dimensions=(0.0, 700.0),
    )

    with pytest.raises(ValueError, match="PARSER_PAGE_DIMENSIONS_INVALID"):
        _parse(source, parser)


def test_parser_pdf_page_count_mismatch_is_rejected(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "one-page.pdf",
        page_sizes=((600.0, 800.0),),
    )
    parser = _write_parser(
        tmp_path / "one-page.json",
        file_name=source.name,
        page_count=2,
        bbox=(10.0, 20.0, 100.0, 40.0),
    )

    with pytest.raises(ValueError, match="PARSER_PDF_PAGE_COUNT_MISMATCH"):
        _parse(source, parser)
