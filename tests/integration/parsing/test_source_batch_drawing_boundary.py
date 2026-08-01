from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ansim_review.contracts.source_batch import decode_source_batch
from ansim_review.parsing.source_batch_importer import (
    import_source_batch,
    prepare_source_batch,
)


def _write_parser(path: Path, file_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "file name": file_name,
                "number of pages": 1,
                "kids": [
                    {
                        "type": "paragraph",
                        "page number": 1,
                        "bounding box": [10, 20, 100, 40],
                        "content": "검토 기준 내용",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _mixed_batch() -> object:
    return decode_source_batch(
        {
            "format": "evidence-review/source-batch",
            "version": 1,
            "sources": [
                {
                    "source_path": "inputs/original/reference.pdf",
                    "role": "REFERENCE_DOCUMENT",
                    "document_id": "REFERENCE-001",
                    "display_title": "참고 기준",
                    "parser": {
                        "kind": "OPENDATALOADER_JSON",
                        "artifact_path": "inputs/parser/reference.json",
                    },
                },
                {
                    "source_path": "inputs/original/drawing.pdf",
                    "role": "CASE_DRAWING",
                    "document_id": "DRAWING-001",
                    "display_title": "사업 도면",
                    "parser": None,
                },
            ],
        }
    )


def test_parserless_case_drawing_does_not_block_reference_ingestion(
    tmp_path: Path,
) -> None:
    original = tmp_path / "inputs" / "original"
    parser = tmp_path / "inputs" / "parser" / "reference.json"
    original.mkdir(parents=True)
    (original / "reference.pdf").write_bytes(b"%PDF-1.7\nreference")
    (original / "drawing.pdf").write_bytes(b"%PDF-1.7\ndrawing")
    _write_parser(parser, "reference.pdf")

    prepared = prepare_source_batch(tmp_path, _mixed_batch())
    states = {source.role: source.state for source in prepared}
    assert states == {
        "REFERENCE_DOCUMENT": "READY_FOR_INGESTION",
        "CASE_DRAWING": "DRAWING_BACKEND_ONLY",
    }

    output = tmp_path / "evidence.sqlite"
    report = import_source_batch(tmp_path, _mixed_batch(), output)

    assert output.is_file()
    assert {source.role: source.state for source in report.sources} == states
    with sqlite3.connect(output) as connection:
        document_ids = connection.execute(
            "SELECT id FROM documents ORDER BY id"
        ).fetchall()
    assert document_ids == [("REFERENCE-001",)]


def test_drawing_only_batch_refuses_empty_evidence_database(tmp_path: Path) -> None:
    source = tmp_path / "inputs" / "original" / "drawing.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.7\ndrawing")
    batch = decode_source_batch(
        {
            "format": "evidence-review/source-batch",
            "version": 1,
            "sources": [
                {
                    "source_path": "inputs/original/drawing.pdf",
                    "role": "CASE_DRAWING",
                    "document_id": "DRAWING-001",
                    "display_title": "사업 도면",
                    "parser": None,
                }
            ],
        }
    )
    output = tmp_path / "evidence.sqlite"

    with pytest.raises(ValueError, match="NO_EVIDENCE_SOURCES"):
        import_source_batch(tmp_path, batch, output)

    assert not output.exists()
