from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from evidence_review.canonical_json import dump_bytes
from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore


def _snapshot_provenance_api() -> Any:
    module = importlib.import_module("evidence_review.evidence.snapshot")
    if not hasattr(module, "evidence_snapshot_provenance"):
        pytest.fail("evidence_snapshot_provenance is not implemented", pytrace=False)
    return module.evidence_snapshot_provenance


def _run_snapshot_api() -> tuple[type[Exception], Any]:
    module = importlib.import_module("evidence_review.review_question")
    missing = [
        name
        for name in ("ReviewEvidenceSnapshotError", "_assert_run_evidence_snapshot")
        if not hasattr(module, name)
    ]
    if missing:
        pytest.fail(f"review snapshot API missing: {missing}", pytrace=False)
    return module.ReviewEvidenceSnapshotError, module._assert_run_evidence_snapshot


def _workspace(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    evidence_snapshot_provenance = _snapshot_provenance_api()
    workspace = tmp_path / "workspace"
    evidence_dir = workspace / "evidence"
    evidence_dir.mkdir(parents=True)
    database = evidence_dir / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-1", "title": "Snapshot binding"},),
                revisions=(
                    {
                        "id": "REV-1",
                        "document_id": "DOC-1",
                        "source_hash": "a" * 64,
                        "byte_size": 10,
                        "page_count": 1,
                    },
                ),
                pages=(
                    {
                        "id": "REV-1-P1",
                        "revision_id": "REV-1",
                        "page_number": 1,
                        "width": 600.0,
                        "height": 800.0,
                    },
                ),
                elements=(
                    {
                        "id": "E-1",
                        "page_id": "REV-1-P1",
                        "element_type": "paragraph",
                        "raw_json": {"text": "사업대상지의 최소 면적 기준은 1,000㎡로 한다."},
                        "raw_text": "사업대상지의 최소 면적 기준은 1,000㎡로 한다.",
                        "normalized_text": "사업대상지의 최소 면적 기준은 1,000㎡로 한다.",
                        "raw_payload_hash": "b" * 64,
                        "bbox": [10.0, 10.0, 500.0, 30.0],
                        "parser_order": 1,
                    },
                ),
            ),
        )
        finalize_evidence_database(store)
        provenance = evidence_snapshot_provenance(store.require_connection())
    return workspace, provenance


def _write_run_request(
    run_directory: Path,
    snapshot_hash: str,
    provenance: dict[str, object] | None = None,
) -> None:
    run_directory.mkdir(parents=True)
    (run_directory / "review-request.json").write_bytes(
        dump_bytes(
            {
                "format": "evidence-review/review-run-request",
                "version": 1,
                "question": "snapshot binding",
                "inputs": {
                    "snapshot_hash": snapshot_hash,
                    **({"evidence_snapshot_provenance": provenance} if provenance else {}),
                },
                "evidence": [],
                "calculations": [],
                "rules": [],
                "approved_rule_result_ids": [],
                "confidence_input": {"factors": {}},
            }
        )
    )


def test_evidence_snapshot_provenance_records_identity_and_counts(tmp_path: Path) -> None:
    workspace, provenance = _workspace(tmp_path)

    assert len(str(provenance["evidence_snapshot_hash"])) == 64
    assert len(str(provenance["evidence_db_sha256"])) == 64
    assert int(provenance["schema_version"]) >= 4
    assert int(provenance["retrieval_record_count"]) == 1
    assert int(provenance["clause_record_count"]) >= 0
    assert (workspace / "evidence" / "evidence.sqlite").is_file()


def test_run_snapshot_binding_accepts_matching_workspace_snapshot(tmp_path: Path) -> None:
    _error_type, assert_run_evidence_snapshot = _run_snapshot_api()
    workspace, provenance = _workspace(tmp_path)
    run_directory = workspace / "runs" / "RUN-00000000000000000000"
    _write_run_request(
        run_directory,
        str(provenance["evidence_snapshot_hash"]),
        provenance,
    )

    active = assert_run_evidence_snapshot(run_directory)

    assert active["evidence_snapshot_hash"] == provenance["evidence_snapshot_hash"]


def test_run_snapshot_binding_fails_closed_on_stale_run(tmp_path: Path) -> None:
    error_type, assert_run_evidence_snapshot = _run_snapshot_api()
    workspace, provenance = _workspace(tmp_path)
    run_directory = workspace / "runs" / "RUN-00000000000000000000"
    stale_hash = "f" * 64
    assert stale_hash != provenance["evidence_snapshot_hash"]
    _write_run_request(
        run_directory,
        stale_hash,
        {**provenance, "evidence_snapshot_hash": stale_hash},
    )

    with pytest.raises(error_type) as raised:
        assert_run_evidence_snapshot(run_directory)

    assert raised.value.reason_code == "EVIDENCE_SNAPSHOT_MISMATCH"


def test_run_snapshot_binding_rejects_same_logical_snapshot_with_new_file_bytes(
    tmp_path: Path,
) -> None:
    error_type, assert_run_evidence_snapshot = _run_snapshot_api()
    workspace, provenance = _workspace(tmp_path)
    run_directory = workspace / "runs" / "RUN-00000000000000000000"
    _write_run_request(
        run_directory,
        str(provenance["evidence_snapshot_hash"]),
        provenance,
    )

    database = workspace / "evidence" / "evidence.sqlite"
    with EvidenceStore(database) as store:
        store.require_connection().execute(
            "INSERT INTO snapshot_meta(key, value) VALUES('physical_padding', 'changed')"
        )
        store.require_connection().commit()

    with pytest.raises(error_type) as raised:
        assert_run_evidence_snapshot(run_directory)

    assert raised.value.reason_code == "EVIDENCE_DATABASE_MISMATCH"
