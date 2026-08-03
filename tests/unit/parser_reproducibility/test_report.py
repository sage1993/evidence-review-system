from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

import ansim_review.parser_reproducibility.report as report_module
from ansim_review.parser_reproducibility.report import (
    report_bytes,
    validate_opendataloader_reproducibility,
)
from tests.unit.parser_reproducibility._helpers import config, write_pdf, write_run


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
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


@pytest.mark.parametrize(
    "failure_kind",
    ["malformed", "encrypted", "zero-page"],
)
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
    document_path = run_a / "document.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    document["number of pages"] = 1
    document["pages"] = document["pages"][:1]
    document_path.write_text(
        json.dumps(document, separators=(",", ":")),
        encoding="utf-8",
    )

    report = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )

    assert report.status == "PARSER_FAILED"
    assert report.findings[0].code == "PARSER_PAGE_COUNT_MISMATCH"


def test_parse_failure_is_reported_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)

    def fail_parse(*object: object, **keyword: object) -> object:
        raise ValueError("canonical normalization failed")

    monkeypatch.setattr(report_module, "parse_loaded_run", fail_parse)

    report = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )

    assert report.status == "PARSER_FAILED"
    assert report.error_count == 1
    assert report.run_a is not None
