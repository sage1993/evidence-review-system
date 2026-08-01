from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ansim_review.contracts.source_batch import decode_source_batch
from ansim_review.parsing.source_batch_importer import (
    import_source_batch,
    prepare_source_batch,
)


def _write_source(root: Path, relative: str, content: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_parser(root: Path, relative: str, text: str, kind: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "number of pages": 1,
                "kids": [
                    {
                        "type": kind,
                        "page number": 1,
                        "bounding box": [10, 20, 300, 80],
                        "content": text,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _source(
    source_path: str,
    role: str,
    parser_path: str | None,
) -> dict[str, object]:
    return {
        "source_path": source_path,
        "role": role,
        "document_id": None,
        "display_title": None,
        "parser": (
            None
            if parser_path is None
            else {
                "kind": "OPENDATALOADER_JSON",
                "artifact_path": parser_path,
                "options": {},
            }
        ),
    }


def _workspace(root: Path) -> object:
    declarations = (
        (
            "inputs/legal/statute.pdf",
            b"statute-bytes",
            "법령 조항 증거",
            "paragraph",
            "REFERENCE_DOCUMENT",
        ),
        (
            "inputs/report/report.pdf",
            b"report-bytes",
            "일반 보고서 증거",
            "paragraph",
            "REFERENCE_DOCUMENT",
        ),
        (
            "inputs/table/schedule.pdf",
            b"table-bytes",
            "표 중심 자료 증거",
            "table",
            "CASE_TABLE",
        ),
        (
            "inputs/scan/scanned.pdf",
            b"scan-bytes",
            "OCR 스캔 증거",
            "paragraph",
            "REFERENCE_DOCUMENT",
        ),
        (
            "inputs/a/shared.pdf",
            b"same-name-first",
            "동일 파일명 첫 번째",
            "paragraph",
            "REFERENCE_DOCUMENT",
        ),
        (
            "inputs/b/shared.pdf",
            b"same-name-second",
            "동일 파일명 두 번째",
            "paragraph",
            "REFERENCE_DOCUMENT",
        ),
        (
            "inputs/duplicate/copy-a.pdf",
            b"duplicate-source",
            "동일 bytes 증거",
            "paragraph",
            "REFERENCE_DOCUMENT",
        ),
        (
            "inputs/duplicate/copy-b.pdf",
            b"duplicate-source",
            "동일 bytes 증거",
            "paragraph",
            "REFERENCE_DOCUMENT",
        ),
    )
    sources: list[dict[str, object]] = []
    for index, (source_path, source_bytes, text, kind, role) in enumerate(
        declarations,
        start=1,
    ):
        parser_path = f"parser/source-{index}.json"
        _write_source(root, source_path, source_bytes)
        _write_parser(root, parser_path, text, kind)
        sources.append(_source(source_path, role, parser_path))
    _write_source(root, "inputs/drawing/project-drawing.pdf", b"drawing-bytes")
    sources.append(
        _source(
            "inputs/drawing/project-drawing.pdf",
            "CASE_DRAWING",
            None,
        )
    )
    return decode_source_batch(
        {
            "format": "evidence-review/source-batch",
            "version": 2,
            "sources": sources,
        }
    )


def test_generic_matrix_routes_deduplicates_and_reproduces(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    batch = _workspace(root)

    prepared = prepare_source_batch(root, batch)
    states = [str(source.state) for source in prepared]
    assert states.count("PENDING_REFERENCE_INGESTION") == 7
    assert states.count("PENDING_DRAWING_INGESTION") == 1

    first = import_source_batch(root, batch, tmp_path / "first.sqlite")
    second = import_source_batch(root, batch, tmp_path / "second.sqlite")

    assert first.snapshot_hash == second.snapshot_hash
    assert first.counts == second.counts
    assert first.counts["documents"] == 7
    assert first.counts["revisions"] == 7
    assert first.counts["pages"] == 7
    assert first.counts["elements"] == 7
    assert {str(source.state) for source in first.sources} == {
        "READY_TO_EVALUATE",
        "PENDING_DRAWING_INGESTION",
    }

    with sqlite3.connect(first.output_db) as connection:
        documents = connection.execute(
            "SELECT id, title FROM documents ORDER BY id"
        ).fetchall()
        texts = {
            row[0]
            for row in connection.execute(
                "SELECT raw_text FROM retrieval_records WHERE raw_text IS NOT NULL"
            ).fetchall()
        }

    assert len(documents) == 7
    assert all(str(document_id).startswith("DOC-") for document_id, _ in documents)
    assert all(
        "law" not in str(document_id).lower()
        for document_id, _ in documents
    )
    assert "사업 도면" not in texts
    assert {
        "법령 조항 증거",
        "일반 보고서 증거",
        "표 중심 자료 증거",
        "OCR 스캔 증거",
        "동일 파일명 첫 번째",
        "동일 파일명 두 번째",
        "동일 bytes 증거",
    } <= texts
