from __future__ import annotations

import json
import shutil
from pathlib import Path

from ansim_review.parser_reproducibility.report import (
    validate_opendataloader_reproducibility,
)
from tests.unit.parser_reproducibility._helpers import config, write_pdf, write_run


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

    report = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )

    assert report.status == "MISMATCH"
    assert "TEXT_CONTENT_CHANGED" in {
        difference.kind for difference in report.differences
    }


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

    report = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )

    assert report.status == "MISMATCH"
    assert {
        difference.kind for difference in report.differences
    } & {"WARNING_CHANGED", "WARNING_ADDED", "WARNING_REMOVED"}


def test_table_cell_and_bbox_changes_are_classified(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)
    document = json.loads((run_b / "document.json").read_text(encoding="utf-8"))
    element = document["pages"][0]["kids"][0]
    element["type"] = "table"
    element["rows"] = [{"cells": [{"content": "Changed"}]}]
    element["bounding box"] = [11, 20, 30, 40]
    (run_b / "document.json").write_text(
        json.dumps(document, separators=(",", ":")),
        encoding="utf-8",
    )

    report = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )
    kinds = {difference.kind for difference in report.differences}

    assert report.status == "MISMATCH"
    assert "BOUNDING_BOX_CHANGED" in kinds
    assert kinds & {"TABLE_STRUCTURE_CHANGED", "TABLE_CELL_VALUE_CHANGED"}
