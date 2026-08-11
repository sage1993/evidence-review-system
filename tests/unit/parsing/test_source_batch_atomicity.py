from __future__ import annotations

import json
import sqlite3
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
    return decode_source_batch(
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


def _temporary_artifacts(output: Path) -> tuple[Path, ...]:
    return tuple(output.parent.glob(f".{output.name}.tmp-*"))


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
    assert _temporary_artifacts(output) == ()


def test_snapshot_hash_failure_cleans_temporary_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    batch = _ready_batch(tmp_path)
    output = tmp_path / "evidence.sqlite"

    def fail_snapshot_hash(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("forced snapshot hash failure")

    monkeypatch.setattr(
        source_batch_importer,
        "compute_snapshot_hash",
        fail_snapshot_hash,
    )

    with pytest.raises(RuntimeError, match="forced snapshot hash failure"):
        source_batch_importer.import_source_batch(tmp_path, batch, output)

    assert not output.exists()
    assert _temporary_artifacts(output) == ()


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    batch = _ready_batch(tmp_path)
    output = tmp_path / "evidence.sqlite"
    sentinel = b"existing database must survive"
    output.write_bytes(sentinel)

    with pytest.raises(FileExistsError):
        source_batch_importer.import_source_batch(tmp_path, batch, output)

    assert output.read_bytes() == sentinel
    assert _temporary_artifacts(output) == ()


def test_successful_import_publishes_fresh_index_without_temp_artifacts(
    tmp_path: Path,
) -> None:
    batch = _ready_batch(tmp_path)
    output = tmp_path / "evidence.sqlite"

    report = source_batch_importer.import_source_batch(tmp_path, batch, output)

    assert output.is_file()
    assert _temporary_artifacts(output) == ()
    with sqlite3.connect(output) as connection:
        snapshot_hash = connection.execute(
            "SELECT value FROM snapshot_meta WHERE key = 'snapshot_hash'"
        ).fetchone()
        database_snapshot_hash = connection.execute(
            "SELECT value FROM snapshot_meta WHERE key = 'database_snapshot_hash'"
        ).fetchone()
        retrieval_hash = connection.execute(
            "SELECT value FROM retrieval_meta WHERE key = 'snapshot_hash'"
        ).fetchone()
    assert snapshot_hash is not None
    assert snapshot_hash == retrieval_hash
    assert database_snapshot_hash == (report.snapshot_hash,)


def test_failed_import_can_be_retried_immediately(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    batch = _ready_batch(tmp_path)
    output = tmp_path / "evidence.sqlite"
    original_build_fts_index = source_batch_importer.build_fts_index

    def fail_fts_index(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("forced FTS failure")

    monkeypatch.setattr(source_batch_importer, "build_fts_index", fail_fts_index)
    with pytest.raises(RuntimeError, match="forced FTS failure"):
        source_batch_importer.import_source_batch(tmp_path, batch, output)

    assert not output.exists()
    assert _temporary_artifacts(output) == ()

    monkeypatch.setattr(
        source_batch_importer,
        "build_fts_index",
        original_build_fts_index,
    )
    report = source_batch_importer.import_source_batch(tmp_path, batch, output)

    assert output.is_file()
    assert report.counts["documents"] == 1
    assert _temporary_artifacts(output) == ()
