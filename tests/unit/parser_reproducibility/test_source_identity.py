from __future__ import annotations

import json
from pathlib import Path

import pytest

from ansim_review.parser_reproducibility.run_manifest import (
    read_parser_run_metadata,
)
from ansim_review.parser_reproducibility.source_identity import (
    SourceIdentityAuthorityError,
    resolve_source_identity,
)
from tests.unit.parser_reproducibility._helpers import write_pdf, write_run


def write_manifest(
    path: Path,
    source_path: str,
    *,
    parser_kind: str = "OPENDATALOADER_JSON",
    document_id: str | None = None,
) -> Path:
    payload = {
        "format": "evidence-review/source-batch",
        "version": 2,
        "sources": [
            {
                "source_path": source_path,
                "role": "REFERENCE_DOCUMENT",
                "document_id": document_id,
                "display_title": "Reference",
                "parser": {
                    "kind": parser_kind,
                    "artifact_path": "inputs/parser/document.json",
                    "options": {},
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_resolves_exact_source_identity_without_reading_pdf(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run = write_run(tmp_path / "run", source)
    metadata = read_parser_run_metadata(run)
    manifest = write_manifest(
        tmp_path / "source-batch.json",
        metadata.source_relative_path,
    )
    source.unlink()

    identity = resolve_source_identity(manifest, metadata)

    assert identity.source_relative_path == metadata.source_relative_path
    assert identity.source_sha256 == metadata.source_sha256
    assert identity.document_id == metadata.document_id
    assert identity.revision_id == metadata.revision_id


def test_missing_source_entry_fails_with_stable_code(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run = write_run(tmp_path / "run", source)
    metadata = read_parser_run_metadata(run)
    manifest = write_manifest(
        tmp_path / "source-batch.json",
        "inputs/original/other.pdf",
    )

    with pytest.raises(SourceIdentityAuthorityError) as captured:
        resolve_source_identity(manifest, metadata)
    assert captured.value.code == "SOURCE_MANIFEST_ENTRY_MISSING"


def test_parser_kind_mismatch_fails_with_stable_code(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run = write_run(tmp_path / "run", source)
    metadata = read_parser_run_metadata(run)
    manifest = write_manifest(
        tmp_path / "source-batch.json",
        metadata.source_relative_path,
        parser_kind="OTHER_PARSER",
    )

    with pytest.raises(SourceIdentityAuthorityError) as captured:
        resolve_source_identity(manifest, metadata)
    assert captured.value.code == "SOURCE_MANIFEST_PARSER_KIND_MISMATCH"


def test_document_identity_mismatch_fails_with_stable_code(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run = write_run(tmp_path / "run", source)
    metadata = read_parser_run_metadata(run)
    manifest = write_manifest(
        tmp_path / "source-batch.json",
        metadata.source_relative_path,
        document_id="DOC-OTHER",
    )

    with pytest.raises(SourceIdentityAuthorityError) as captured:
        resolve_source_identity(manifest, metadata)
    assert captured.value.code == "SOURCE_IDENTITY_MISMATCH"
