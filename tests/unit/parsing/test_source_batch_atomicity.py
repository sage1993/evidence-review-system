from __future__ import annotations

import json
from pathlib import Path

import pytest

import ansim_review.parsing.source_batch_importer as source_batch_importer
from ansim_review.contracts.source_batch import decode_source_batch
from tests.helpers.pdf_fixtures import write_pdf_fixture


def _ready_batch(tmp_path: Path):
    source = write_pdf_fixture(
        tmp_path / "inputs" / "original" / "policy.pdf",
        page_sizes=((600.0, 800.0),),
    )
    parser = tmp_path / "inputs" / "parser" / "policy.json"
    parser.parent.mkdir(parents=True, exist_ok=True)
    parser.write_text(
        json.dumps(
            {
                "file name": source.name,
                "number of pages": 1,
                "kids": [
                    {
                        "type": "paragraph",
                        "page number": 1,
                        "bounding box": [10, 20, 100, 40],
                        "content": "atomic source batch test",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    batch = decode_source_batch(
        {
            "format": "evidence-review/source-batch",
            "version": 1,
            "sources": [
                {
                    "source_path": "inputs/original/policy.pdf",
                    "role": "REFERENCE_DOCUMENT",
                    "document_id": None,
                    "display_title": None,
                    "parser": {
                        "kind": "OPENDATALOADER_JSON",
                        "artifact_path": "inputs/parser/policy.json",
                    },
                }
            ],
        }
    )
    return batch


def test_fts_failure_does_not_publish_output_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    batch = _ready_batch(tmp_path)
    output = tmp_path / "evidence.sqlite"

    def fail_fts_index(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("forced FTS failure")

    monkeypatch.setattr(source_batch_importer, "build_fts_index", fail_fts_index)

    with pytest.raises(RuntimeError, match="forced FTS failure"):
        source_batch_importer.import_source_batch(tmp_path, batch, output)

    assert not output.exists()
