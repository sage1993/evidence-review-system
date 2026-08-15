from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.contracts.source_batch import ParserBinding, SourceBatch, SourceItem
from evidence_review.parsing.source_batch_importer import import_source_batch
from evidence_review.parsing.source_manifest import sha256_file
from tests.helpers.pdf_fixtures import write_pdf_fixture

_PAGE_SIZE = ((595.0, 842.0),)


def _parser(path: Path, *, declared_name: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "file name": declared_name,
                "number of pages": 1,
                "kids": [
                    {
                        "type": "paragraph",
                        "page number": 1,
                        "bounding box": [10.0, 20.0, 100.0, 40.0],
                        "content": "source-batch rename binding",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _batch(source: Path, *, bound_source_sha256: str | None) -> SourceBatch:
    options: dict[str, object] = {}
    if bound_source_sha256 is not None:
        options["source_sha256"] = bound_source_sha256
    return SourceBatch(
        format="evidence-review/source-batch",
        version=2,
        sources=(
            SourceItem(
                source_path=source.name,
                role="REFERENCE_DOCUMENT",
                document_id="DOC-RENAMED",
                display_title="Renamed reference",
                parser=ParserBinding(
                    kind="OPENDATALOADER_JSON",
                    artifact_path="parser.json",
                    options=options,
                ),
            ),
        ),
    )


def test_source_batch_allows_rename_with_parser_time_source_hash(tmp_path: Path) -> None:
    source = write_pdf_fixture(tmp_path / "renamed.pdf", page_sizes=_PAGE_SIZE)
    _parser(tmp_path / "parser.json", declared_name="original.pdf")

    report = import_source_batch(
        tmp_path,
        _batch(source, bound_source_sha256=sha256_file(source)),
        tmp_path / "evidence.sqlite",
    )

    assert report.sources[0].source_sha256 == sha256_file(source)
    assert report.sources[0].document_id == "DOC-RENAMED"
    assert report.output_db.is_file()


def test_source_batch_rename_without_parser_time_hash_remains_fail_closed(
    tmp_path: Path,
) -> None:
    source = write_pdf_fixture(tmp_path / "renamed.pdf", page_sizes=_PAGE_SIZE)
    _parser(tmp_path / "parser.json", declared_name="original.pdf")

    with pytest.raises(ValueError, match="PARSER_SOURCE_FILENAME_MISMATCH"):
        import_source_batch(
            tmp_path,
            _batch(source, bound_source_sha256=None),
            tmp_path / "evidence.sqlite",
        )


def test_source_batch_rejects_wrong_parser_source_hash(tmp_path: Path) -> None:
    source = write_pdf_fixture(tmp_path / "renamed.pdf", page_sizes=_PAGE_SIZE)
    _parser(tmp_path / "parser.json", declared_name="original.pdf")

    with pytest.raises(ValueError, match="PARSER_SOURCE_HASH_MISMATCH"):
        import_source_batch(
            tmp_path,
            _batch(source, bound_source_sha256="0" * 64),
            tmp_path / "evidence.sqlite",
        )


def test_source_hash_mismatch_is_rejected_even_when_filename_matches(
    tmp_path: Path,
) -> None:
    source = write_pdf_fixture(tmp_path / "same-name.pdf", page_sizes=_PAGE_SIZE)
    _parser(tmp_path / "parser.json", declared_name="same-name.pdf")

    with pytest.raises(ValueError, match="PARSER_SOURCE_HASH_MISMATCH"):
        import_source_batch(
            tmp_path,
            _batch(source, bound_source_sha256="f" * 64),
            tmp_path / "evidence.sqlite",
        )
