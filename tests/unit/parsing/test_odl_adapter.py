import json
from math import inf, nan
from pathlib import Path

import pytest

import evidence_review.parsing.odl_adapter as odl_adapter
from evidence_review.canonical_json import sha256_json
from evidence_review.parsing.odl_adapter import (
    OpenDataLoaderJsonAdapter,
    load_parsed_tables,
    load_raw_elements,
)
from evidence_review.parsing.odl_source import (
    ParserPageDimensionsResult,
    parser_page_dimensions,
)
from evidence_review.parsing.parser_registry import ParserContext
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


def test_load_parsed_tables_preserves_rows_columns_spans_and_search_text() -> None:
    fixture = Path("tests/golden/fixtures/minimal-table-parser-output.json")

    first = load_parsed_tables(fixture, document_id="LAW1", revision_id="LAW1-abc123")
    second = load_parsed_tables(fixture, document_id="LAW1", revision_id="LAW1-abc123")

    assert first == second
    assert len(first) == 1
    table = first[0]
    assert table.table_key == table.canonical_table_id
    assert table.table_key.startswith("T-")
    assert table.raw_parser_table_id == 608
    assert table.source_revision_id == "LAW1-abc123"
    assert table.structural_path == ("kids", 0)
    assert table.page_number == 1
    assert table.bbox == (10.0, 20.0, 110.0, 180.0)
    assert [(row.row_number, len(row.cells)) for row in table.rows] == [(1, 3), (2, 3)]
    assert table.rows[1].cells[0].row_span == 2
    assert table.rows[0].cells[1].column_number == 2
    assert table.rows[0].cells[1].text == "기존 용도지역"
    assert "행 1 열 2: 기존 용도지역" in table.search_text
    assert "행 2 열 3: 준주거지역" in table.search_text
    assert table.rows[0].cells[1].raw_payload_hash == sha256_json(
        table.rows[0].cells[1].raw_payload
    )
    element = load_raw_elements(fixture, document_id="LAW1", revision_id="LAW1-abc123")[0]
    assert element.element_type == "table"
    assert "행 1 열 2: 기존 용도지역" in element.raw_text


def test_reused_raw_table_id_on_different_pages_gets_distinct_table_keys(
    tmp_path: Path,
) -> None:
    parser = tmp_path / "parser.json"
    parser.write_text(
        json.dumps(
            {
                "kids": [
                    {"type": "table", "id": 1, "page number": 93, "rows": []},
                    {"type": "table", "id": 1, "page number": 95, "rows": []},
                ]
            }
        ),
        encoding="utf-8",
    )

    tables = load_parsed_tables(
        parser,
        document_id="LAW1",
        revision_id="LAW1-abc123",
    )

    assert [table.page_number for table in tables] == [93, 95]
    assert tables[0].canonical_table_id != tables[1].canonical_table_id


def test_reused_raw_table_id_on_same_page_uses_structural_path(
    tmp_path: Path,
) -> None:
    parser = tmp_path / "parser.json"
    parser.write_text(
        json.dumps(
            {
                "kids": [
                    {"type": "table", "id": 1, "page number": 93, "rows": []},
                    {"type": "table", "id": 1, "page number": 93, "rows": []},
                ]
            }
        ),
        encoding="utf-8",
    )

    tables = load_parsed_tables(parser, "LAW1", "LAW1-abc123")

    assert tables[0].canonical_table_id != tables[1].canonical_table_id
    assert tables[0].structural_path != tables[1].structural_path


def test_canonical_table_id_is_deterministic_and_revision_bound(
    tmp_path: Path,
) -> None:
    parser = tmp_path / "parser.json"
    parser.write_text(
        json.dumps(
            {"kids": [{"type": "table", "id": "1", "page number": 93, "rows": []}]}
        ),
        encoding="utf-8",
    )

    first = load_parsed_tables(parser, "LAW1", "LAW1-revision-a")[0]
    repeated = load_parsed_tables(parser, "LAW1", "LAW1-revision-a")[0]
    other_revision = load_parsed_tables(parser, "LAW1", "LAW1-revision-b")[0]

    assert first.canonical_table_id == repeated.canonical_table_id
    assert first.canonical_table_id != other_revision.canonical_table_id


def test_raw_parser_table_id_and_structural_provenance_are_preserved(
    tmp_path: Path,
) -> None:
    parser = tmp_path / "parser.json"
    parser_bytes = json.dumps(
        {"kids": [{"type": "table", "id": 1, "page number": 93, "rows": []}]}
    ).encode("utf-8")
    parser.write_bytes(parser_bytes)

    table = load_parsed_tables(parser, "LAW1", "LAW1-revision-a")[0]

    assert table.raw_parser_table_id == 1
    assert table.raw_payload["id"] == 1
    assert table.searchable_document()["raw_parser_table_id"] == 1
    assert table.searchable_document()["structural_path"] == list(table.structural_path)
    assert parser.read_bytes() == parser_bytes


def test_canonical_table_identity_collision_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = tmp_path / "parser.json"
    parser.write_text(
        json.dumps(
            {
                "kids": [
                    {
                        "type": "table",
                        "id": 1,
                        "page number": 93,
                        "content": "first representation",
                        "rows": [],
                    },
                    {
                        "type": "table",
                        "id": 1,
                        "page number": 95,
                        "content": "second representation",
                        "rows": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        odl_adapter,
        "_canonical_table_id",
        lambda **_kwargs: "T-FORCED-COLLISION",
    )

    with pytest.raises(ValueError, match="PARSER_TABLE_IDENTITY_COLLISION"):
        load_parsed_tables(parser, "LAW1", "LAW1-revision-a")


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


@pytest.mark.parametrize("page_number", [0, -1])
def test_load_raw_elements_rejects_non_positive_page_numbers(
    tmp_path: Path,
    page_number: int,
) -> None:
    parser = tmp_path / "invalid-page.json"
    parser.write_text(
        json.dumps(
            {
                "kids": [
                    {
                        "type": "paragraph",
                        "page number": page_number,
                        "content": "invalid page",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="page number must be a positive integer"):
        load_raw_elements(parser, document_id="DOC", revision_id="REV")


@pytest.mark.parametrize("element_type", ["paragraph", "table", "figure"])
def test_parser_page_bound_record_above_declared_page_count_is_rejected(
    tmp_path: Path,
    element_type: str,
) -> None:
    source = write_pdf_fixture(
        tmp_path / "one-page.pdf",
        page_sizes=((600.0, 800.0),),
    )
    parser = tmp_path / "one-page.json"
    parser.write_text(
        json.dumps(
            {
                "file name": source.name,
                "number of pages": 1,
                "kids": [
                    {
                        "type": element_type,
                        "page number": 2,
                        "content": "out of range",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"PARSER_ELEMENT_PAGE_OUT_OF_RANGE: page=2 page_count=1",
    ):
        _parse(source, parser)


def test_parser_page_count_is_inferred_from_elements_when_metadata_is_absent(
    tmp_path: Path,
) -> None:
    source = write_pdf_fixture(
        tmp_path / "two-page.pdf",
        page_sizes=((600.0, 800.0), (600.0, 800.0)),
    )
    parser = tmp_path / "two-page.json"
    parser.write_text(
        json.dumps(
            {
                "file name": source.name,
                "kids": [
                    {
                        "type": "paragraph",
                        "page number": 2,
                        "content": "inferred page count",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    contribution = _parse(source, parser)

    assert len(contribution.page_dimensions) == 2
    assert contribution.elements[0].page_number == 2

def test_odl_preserves_cropbox_origin_and_rotation_in_canonical_bbox(
    tmp_path: Path,
) -> None:
    source = write_pdf_fixture(
        tmp_path / "rotated.pdf",
        page_sizes=((500.0, 700.0),),
        crop_boxes={1: (10.0, 20.0, 510.0, 720.0)},
        rotations={1: 90},
    )
    parser = tmp_path / "rotated.json"
    parser.write_text(
        json.dumps(
            {
                "file name": "rotated.pdf",
                "number of pages": 1,
                "pages": [
                    {
                        "page_number": 1,
                        "width": 500,
                        "height": 700,
                        "origin_x": 10,
                        "origin_y": 20,
                        "rotation": 90,
                        "box_kind": "CROP_BOX",
                    }
                ],
                "kids": [
                    {
                        "type": "paragraph",
                        "page number": 1,
                        "bounding box": [110, 220, 210, 320],
                        "content": "rotated evidence",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    contribution = OpenDataLoaderJsonAdapter().parse(
        ParserContext(source, parser, {})
    )

    page = contribution.page_dimensions[0]
    assert (page.origin_x, page.origin_y) == (10.0, 20.0)
    assert page.rotation == 90
    assert page.box_kind == "CROP_BOX"
    assert contribution.elements[0].bbox == (100.0, 200.0, 200.0, 300.0)
