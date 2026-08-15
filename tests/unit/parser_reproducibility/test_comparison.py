from __future__ import annotations

import json
import shutil
from pathlib import Path

from evidence_review.parser_reproducibility.report import (
    validate_opendataloader_reproducibility,
)
from tests.unit.parser_reproducibility._helpers import config, write_pdf, write_run


def read_document(run: Path) -> dict[str, object]:
    return json.loads((run / "document.json").read_text(encoding="utf-8"))


def write_document(run: Path, document: dict[str, object]) -> None:
    (run / "document.json").write_text(
        json.dumps(document, separators=(",", ":")),
        encoding="utf-8",
    )


def difference_kinds(source: Path, run_a: Path, run_b: Path) -> set[str]:
    report = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )
    assert report.status == "MISMATCH"
    return {difference.kind for difference in report.differences}


def test_raw_equality_is_byte_identical(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = tmp_path / "run-b"
    shutil.copytree(run_a, run_b)

    report = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )

    assert report.status == "BYTE_IDENTICAL"
    assert report.canonical_equivalent is True
    assert report.differences == ()


def test_approved_run_root_difference_is_semantically_identical(
    tmp_path: Path,
) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)

    report = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )

    assert report.status == "SEMANTICALLY_IDENTICAL"
    assert report.canonical_equivalent is True
    assert report.differences == ()


def test_parser_version_difference_is_environment_mismatch(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source, parser_version="1.2.3")
    run_b = write_run(tmp_path / "run-b", source, parser_version="1.2.4")

    report = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )

    assert report.status == "ENVIRONMENT_MISMATCH"
    assert report.canonical_equivalent is None


def test_text_change_is_mismatch(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source, content="Alpha")
    run_b = write_run(tmp_path / "run-b", source, content="Beta")

    assert "TEXT_CONTENT_CHANGED" in difference_kinds(source, run_a, run_b)


def test_warning_page_change_is_mismatch(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(
        tmp_path / "run-a",
        source,
        warning="page 1: inspect layout",
    )
    run_b = write_run(
        tmp_path / "run-b",
        source,
        warning="inspect layout",
    )

    assert difference_kinds(source, run_a, run_b) & {
        "WARNING_CHANGED",
        "WARNING_ADDED",
        "WARNING_REMOVED",
    }


def test_table_cell_and_bbox_changes_are_classified(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)
    document = read_document(run_b)
    pages = document["pages"]
    assert isinstance(pages, list)
    page = pages[0]
    assert isinstance(page, dict)
    kids = page["kids"]
    assert isinstance(kids, list)
    element = kids[0]
    assert isinstance(element, dict)
    element["type"] = "table"
    element["rows"] = [{"cells": [{"content": "Changed"}]}]
    element["bounding box"] = [11, 20, 30, 40]
    write_document(run_b, document)

    kinds = difference_kinds(source, run_a, run_b)
    assert "BOUNDING_BOX_CHANGED" in kinds
    assert kinds & {"TABLE_STRUCTURE_CHANGED", "TABLE_CELL_VALUE_CHANGED"}


def test_table_row_addition_is_classified_as_table_structure_change(
    tmp_path: Path,
) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)
    for run in (run_a, run_b):
        document = read_document(run)
        pages = document["pages"]
        assert isinstance(pages, list)
        page = pages[0]
        assert isinstance(page, dict)
        kids = page["kids"]
        assert isinstance(kids, list)
        element = kids[0]
        assert isinstance(element, dict)
        element["type"] = "table"
        element["rows"] = [{"cells": [{"content": "Base"}]}]
        write_document(run, document)

    document = read_document(run_b)
    pages = document["pages"]
    assert isinstance(pages, list)
    page = pages[0]
    assert isinstance(page, dict)
    kids = page["kids"]
    assert isinstance(kids, list)
    element = kids[0]
    assert isinstance(element, dict)
    rows = element["rows"]
    assert isinstance(rows, list)
    rows.append({"cells": [{"content": "Added"}]})
    write_document(run_b, document)

    assert "TABLE_STRUCTURE_CHANGED" in difference_kinds(source, run_a, run_b)


def test_image_occurrence_change_is_classified(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)
    for run, image_path in ((run_a, "images/a.png"), (run_b, "images/b.png")):
        document = read_document(run)
        pages = document["pages"]
        assert isinstance(pages, list)
        page = pages[0]
        assert isinstance(page, dict)
        kids = page["kids"]
        assert isinstance(kids, list)
        element = kids[0]
        assert isinstance(element, dict)
        element["type"] = "image"
        element["image_path"] = image_path
        write_document(run, document)

    assert "IMAGE_OCCURRENCE_CHANGED" in difference_kinds(source, run_a, run_b)


def test_relationship_change_is_classified(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)
    for run, next_id in ((run_a, "ELEMENT-2"), (run_b, "ELEMENT-3")):
        document = read_document(run)
        pages = document["pages"]
        assert isinstance(pages, list)
        page = pages[0]
        assert isinstance(page, dict)
        kids = page["kids"]
        assert isinstance(kids, list)
        element = kids[0]
        assert isinstance(element, dict)
        element["next"] = next_id
        write_document(run, document)

    assert "RELATIONSHIP_CHANGED" in difference_kinds(source, run_a, run_b)


def test_page_order_change_is_classified(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf", pages=2)
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)
    document = read_document(run_b)
    pages = document["pages"]
    assert isinstance(pages, list)
    pages.reverse()
    write_document(run_b, document)

    assert "PAGE_ORDER_CHANGED" in difference_kinds(source, run_a, run_b)
