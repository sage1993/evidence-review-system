from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pypdf import PdfWriter

from ansim_review.parser_reproducibility.report import (
    report_bytes,
    validate_opendataloader_reproducibility,
)
from tests.unit.parser_reproducibility._helpers import config, write_pdf, write_run


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_validation_does_not_modify_inputs(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)
    before = tree_hashes(tmp_path)

    report = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )

    assert report.status == "SEMANTICALLY_IDENTICAL"
    assert tree_hashes(tmp_path) == before


def test_report_is_byte_deterministic_and_has_no_absolute_path(
    tmp_path: Path,
) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)

    first = report_bytes(
        validate_opendataloader_reproducibility(
            source,
            run_a,
            run_b,
            config(),
        )
    )
    second = report_bytes(
        validate_opendataloader_reproducibility(
            source,
            run_a,
            run_b,
            config(),
        )
    )

    assert first == second
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
    assert str(tmp_path).encode("utf-8") not in first
    assert first.endswith(b"\n")


@pytest.mark.parametrize("failure_kind", ["malformed", "encrypted", "zero-page"])
def test_invalid_pdf_fails_closed_without_exception(
    tmp_path: Path,
    failure_kind: str,
) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)

    if failure_kind == "malformed":
        source.write_bytes(b"not a pdf")
    else:
        writer = PdfWriter()
        if failure_kind == "encrypted":
            writer.add_blank_page(width=595, height=842)
            writer.encrypt("secret")
        with source.open("wb") as stream:
            writer.write(stream)

    report = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )

    assert report.status == "PARSER_FAILED"
    assert report.error_count == 1
    assert report.findings


def test_source_and_parser_page_count_must_match(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf", pages=2)
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)

    report = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )

    assert report.status == "PARSER_FAILED"
    assert report.findings[0].code == "PARSER_PAGE_COUNT_MISMATCH"
