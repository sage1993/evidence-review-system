from __future__ import annotations

from pathlib import Path

import pytest

from evidence_review.canonical_json import dump_bytes
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.snapshot import evidence_snapshot_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.index import build_fts_index
from evidence_review.review_question import (
    ReviewEvidenceSnapshotError,
    _assert_run_evidence_snapshot,
)


def _workspace(tmp_path: Path) -> tuple[Path, dict[str, object]]:
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
        build_fts_index(store.require_connection())
        provenance = evidence_snapshot_provenance(store.require_connection())
    return workspace, provenance


def _write_run_request(run_directory: Path, snapshot_hash: str) -> None:
    run_directory.mkdir(parents=True)
    (run_directory / "review-request.json").write_bytes(
        dump_bytes(
            {
                "format": "evidence-review/review-run-request",
                "version": 1,
                "question": "snapshot binding",
                "inputs": {"snapshot_hash": snapshot_hash},
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
    workspace, provenance = _workspace(tmp_path)
    run_directory = workspace / "runs" / "RUN-00000000000000000000"
    _write_run_request(run_directory, str(provenance["evidence_snapshot_hash"]))

    active = _assert_run_evidence_snapshot(run_directory)

    assert active["evidence_snapshot_hash"] == provenance["evidence_snapshot_hash"]


def test_run_snapshot_binding_fails_closed_on_stale_run(tmp_path: Path) -> None:
    workspace, provenance = _workspace(tmp_path)
    run_directory = workspace / "runs" / "RUN-00000000000000000000"
    stale_hash = "f" * 64
    assert stale_hash != provenance["evidence_snapshot_hash"]
    _write_run_request(run_directory, stale_hash)

    with pytest.raises(ReviewEvidenceSnapshotError) as raised:
        _assert_run_evidence_snapshot(run_directory)

    assert raised.value.reason_code == "EVIDENCE_SNAPSHOT_MISMATCH"
