from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.parsing.odl_adapter import OpenDataLoaderJsonAdapter
from evidence_review.parsing.parser_registry import ParserContext
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
                        "content": "rename-safe parser binding",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_direct_parser_filename_mismatch_remains_fail_closed(tmp_path: Path) -> None:
    source = write_pdf_fixture(tmp_path / "renamed.pdf", page_sizes=_PAGE_SIZE)
    parser = _parser(tmp_path / "parser.json", declared_name="original.pdf")

    with pytest.raises(ValueError, match="PARSER_SOURCE_FILENAME_MISMATCH"):
        OpenDataLoaderJsonAdapter().parse(
            ParserContext(source_path=source, parser_artifact_path=parser, options={})
        )


def test_manifest_bound_parser_allows_source_rename_when_hash_matches(tmp_path: Path) -> None:
    source = write_pdf_fixture(tmp_path / "renamed.pdf", page_sizes=_PAGE_SIZE)
    parser = _parser(tmp_path / "parser.json", declared_name="original.pdf")

    contribution = OpenDataLoaderJsonAdapter().parse(
        ParserContext(
            source_path=source,
            parser_artifact_path=parser,
            options={},
            binding_authority="SOURCE_BATCH_MANIFEST",
            source_sha256=sha256_file(source),
        )
    )

    assert contribution.page_count == 1
    assert contribution.elements[0].raw_text == "rename-safe parser binding"


def test_manifest_bound_parser_rejects_source_hash_mismatch(tmp_path: Path) -> None:
    source = write_pdf_fixture(tmp_path / "renamed.pdf", page_sizes=_PAGE_SIZE)
    parser = _parser(tmp_path / "parser.json", declared_name="original.pdf")

    with pytest.raises(ValueError, match="PARSER_SOURCE_HASH_MISMATCH"):
        OpenDataLoaderJsonAdapter().parse(
            ParserContext(
                source_path=source,
                parser_artifact_path=parser,
                options={},
                binding_authority="SOURCE_BATCH_MANIFEST",
                source_sha256="0" * 64,
            )
        )
