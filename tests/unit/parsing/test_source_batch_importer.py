from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ansim_review.contracts.source_batch import decode_source_batch
from ansim_review.parsing.source_batch_importer import (
    PendingParserOutputError,
    import_source_batch,
    prepare_source_batch,
)


def _source(
    source_path: str,
    *,
    document_id: str | None = None,
    parser_path: str | None = None,
) -> dict[str, object]:
    parser: dict[str, object] | None = None
    if parser_path is not None:
        parser = {
            "kind": "OPENDATALOADER_JSON",
            "artifact_path": parser_path,
        }
    return {
        "source_path": source_path,
        "role": "REFERENCE_DOCUMENT",
        "document_id": document_id,
        "display_title": None,
        "parser": parser,
    }


def _batch(*sources: dict[str, object]):
    return decode_source_batch(
        {
            "format": "evidence-review/source-batch",
            "version": 1,
            "sources": list(sources),
        }
    )


def test_same_bytes_with_different_names_deduplicate(tmp_path: Path) -> None:
    first = tmp_path / "inputs" / "original" / "first.pdf"
    second = tmp_path / "inputs" / "original" / "second.pdf"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"same-pdf-bytes")
    second.write_bytes(b"same-pdf-bytes")

    prepared = prepare_source_batch(
        tmp_path,
        _batch(_source("inputs/original/first.pdf"), _source("inputs/original/second.pdf")),
    )

    assert len(prepared) == 1
    assert prepared[0].document_id.startswith("DOC-")


def test_same_filename_with_different_bytes_produces_different_ids(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    for root, content in ((first_root, b"first"), (second_root, b"second")):
        path = root / "inputs" / "original" / "document.pdf"
        path.parent.mkdir(parents=True)
        path.write_bytes(content)

    first = prepare_source_batch(
        first_root,
        _batch(_source("inputs/original/document.pdf")),
    )[0]
    second = prepare_source_batch(
        second_root,
        _batch(_source("inputs/original/document.pdf")),
    )[0]

    assert first.document_id != second.document_id
    assert first.revision_id != second.revision_id


def test_explicit_document_id_is_preserved(tmp_path: Path) -> None:
    source = tmp_path / "inputs" / "original" / "document.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"document")

    prepared = prepare_source_batch(
        tmp_path,
        _batch(_source("inputs/original/document.pdf", document_id="CITY-POLICY-001")),
    )[0]

    assert prepared.document_id == "CITY-POLICY-001"
    assert prepared.revision_id.startswith("CITY-POLICY-001-")


def test_explicit_document_id_cannot_bind_different_bytes(tmp_path: Path) -> None:
    first = tmp_path / "inputs" / "original" / "first.pdf"
    second = tmp_path / "inputs" / "original" / "second.pdf"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    with pytest.raises(ValueError, match="document_id maps to multiple source hashes"):
        prepare_source_batch(
            tmp_path,
            _batch(
                _source("inputs/original/first.pdf", document_id="SHARED-ID"),
                _source("inputs/original/second.pdf", document_id="SHARED-ID"),
            ),
        )


def test_missing_parser_is_a_pending_source_not_empty_evidence(tmp_path: Path) -> None:
    source = tmp_path / "inputs" / "original" / "document.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"document")

    prepared = prepare_source_batch(
        tmp_path,
        _batch(_source("inputs/original/document.pdf")),
    )[0]

    assert prepared.parser_path is None
    assert prepared.state == "PENDING_PARSER_OUTPUT"


def test_declared_parser_must_exist(tmp_path: Path) -> None:
    source = tmp_path / "inputs" / "original" / "document.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"document")

    with pytest.raises(FileNotFoundError):
        prepare_source_batch(
            tmp_path,
            _batch(
                _source(
                    "inputs/original/document.pdf",
                    parser_path="inputs/parser/missing.json",
                )
            ),
        )


def test_arbitrary_pdf_and_parser_create_searchable_evidence_database(
    tmp_path: Path,
) -> None:
    source = tmp_path / "inputs" / "original" / "사용자-제공-기준.pdf"
    parser = tmp_path / "inputs" / "parser" / "result.json"
    source.parent.mkdir(parents=True)
    parser.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.7\narbitrary-user-document")
    parser.write_text(
        json.dumps(
            {
                "file name": source.name,
                "number of pages": 1,
                "title": "사용자 제공 기준",
                "kids": [
                    {
                        "type": "paragraph",
                        "page number": 1,
                        "bounding box": [10, 20, 100, 40],
                        "content": "임의 문서의 검토 기준 내용",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "evidence" / "evidence.sqlite"

    report = import_source_batch(
        tmp_path,
        _batch(
            _source(
                "inputs/original/사용자-제공-기준.pdf",
                parser_path="inputs/parser/result.json",
            )
        ),
        output,
    )

    assert report.counts["documents"] == 1
    assert report.counts["elements"] == 1
    assert output.is_file()
    with sqlite3.connect(output) as connection:
        title = connection.execute("SELECT title FROM documents").fetchone()
        indexed = connection.execute("SELECT COUNT(*) FROM retrieval_records").fetchone()
    assert title == ("사용자 제공 기준",)
    assert indexed == (1,)


def test_import_refuses_pending_parser_without_creating_empty_database(
    tmp_path: Path,
) -> None:
    source = tmp_path / "inputs" / "original" / "document.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"document")
    output = tmp_path / "evidence.sqlite"

    with pytest.raises(PendingParserOutputError, match="PENDING_PARSER_OUTPUT"):
        import_source_batch(
            tmp_path,
            _batch(_source("inputs/original/document.pdf")),
            output,
        )

    assert not output.exists()
