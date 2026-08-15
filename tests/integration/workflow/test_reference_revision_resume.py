from __future__ import annotations

from pathlib import Path

from evidence_review.workflow.orchestrator import (
    ingest_pending_references,
    prepare_review_run,
)
from evidence_review.workflow.request import decode_review_request
from tests.integration.workflow._reference_helpers import (
    FakeReferenceBackend,
    write_source,
)


def test_same_filename_different_hashes_remain_distinct_revisions(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "RUN-001"
    first_hash, first_size = write_source(
        run_dir / "inputs" / "original" / "first" / "guideline.pdf",
        b"guideline-v1",
    )
    second_hash, second_size = write_source(
        run_dir / "inputs" / "original" / "second" / "guideline.pdf",
        b"guideline-v2",
    )
    request = decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "개정 기준을 적용할 수 있는가?",
            "attachments": [
                {
                    "attachment_id": "ATT-REF-001",
                    "original_name": "guideline.pdf",
                    "stored_path": "inputs/original/first/guideline.pdf",
                    "sha256": first_hash,
                    "byte_size": first_size,
                    "mime": "application/pdf",
                    "role": "REFERENCE_DOCUMENT",
                    "role_confirmation": "USER_CONFIRMED",
                    "proposed_role": None,
                },
                {
                    "attachment_id": "ATT-REF-002",
                    "original_name": "guideline.pdf",
                    "stored_path": "inputs/original/second/guideline.pdf",
                    "sha256": second_hash,
                    "byte_size": second_size,
                    "mime": "application/pdf",
                    "role": "REFERENCE_DOCUMENT",
                    "role_confirmation": "USER_CONFIRMED",
                    "proposed_role": None,
                },
            ],
        }
    )
    layout = prepare_review_run(
        runs_root,
        "RUN-001",
        request,
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    backend = FakeReferenceBackend()
    receipt = ingest_pending_references(layout, backend)

    assert backend.calls == [("ATT-REF-001", "ATT-REF-002")]
    assert tuple(source.source_sha256 for source in receipt.sources) == tuple(
        sorted((first_hash, second_hash))
    )
    assert len({source.revision_id for source in receipt.sources}) == 2
    assert receipt.changed_original_names == ("guideline.pdf",)
    assert receipt.review_required is True


def test_duplicate_source_hash_is_ingested_once(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "RUN-001"
    digest, size = write_source(
        run_dir / "inputs" / "original" / "reference.pdf",
        b"same-source",
    )
    duplicate = run_dir / "inputs" / "original" / "copy.pdf"
    duplicate.write_bytes(b"same-source")
    request = decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "중복 자료를 처리할 수 있는가?",
            "attachments": [
                {
                    "attachment_id": "ATT-REF-001",
                    "original_name": "reference.pdf",
                    "stored_path": "inputs/original/reference.pdf",
                    "sha256": digest,
                    "byte_size": size,
                    "mime": "application/pdf",
                    "role": "REFERENCE_DOCUMENT",
                    "role_confirmation": "USER_CONFIRMED",
                    "proposed_role": None,
                },
                {
                    "attachment_id": "ATT-REF-002",
                    "original_name": "copy.pdf",
                    "stored_path": "inputs/original/copy.pdf",
                    "sha256": digest,
                    "byte_size": size,
                    "mime": "application/pdf",
                    "role": "REFERENCE_DOCUMENT",
                    "role_confirmation": "USER_CONFIRMED",
                    "proposed_role": None,
                },
            ],
        }
    )
    layout = prepare_review_run(
        runs_root,
        "RUN-001",
        request,
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    backend = FakeReferenceBackend()
    receipt = ingest_pending_references(layout, backend)

    assert backend.calls == [("ATT-REF-001", "ATT-REF-002")]
    assert len(receipt.sources) == 1
    assert receipt.sources[0].attachment_ids == ("ATT-REF-001", "ATT-REF-002")
