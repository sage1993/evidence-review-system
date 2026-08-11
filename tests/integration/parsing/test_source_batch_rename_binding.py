from __future__ import annotations

import json
from pathlib import Path

from ansim_review.contracts.source_batch import ParserBinding, SourceBatch, SourceItem
from ansim_review.parsing.source_batch_importer import import_source_batch
from ansim_review.parsing.source_manifest import sha256_file
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


def test_source_batch_allows_renamed_source_with_manifest_binding(tmp_path: Path) -> None:
    source = write_pdf_fixture(tmp_path / "renamed.pdf", page_sizes=_PAGE_SIZE)
    _parser(tmp_path / "parser.json", declared_name="original.pdf")
    batch = SourceBatch(
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
                    options={},
                ),
            ),
        ),
    )

    report = import_source_batch(tmp_path, batch, tmp_path / "evidence.sqlite")

    assert report.sources[0].source_sha256 == sha256_file(source)
    assert report.sources[0].document_id == "DOC-RENAMED"
    assert report.output_db.is_file()
