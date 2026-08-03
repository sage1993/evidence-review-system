from __future__ import annotations

from pathlib import Path

from ansim_review.workflow.events import load_workflow_events
from ansim_review.workflow.orchestrator import (
    ingest_pending_references,
    prepare_review_run,
    resume_review_run,
)
from ansim_review.workflow.request import (
    decode_review_request,
    review_request_sha256,
)
from tests.integration.workflow._reference_helpers import (
    FakeReferenceBackend,
    write_source,
)


def _request(run_dir: Path):
    digest, size = write_source(
        run_dir / "inputs" / "original" / "reference.pdf",
        b"reference-v1",
    )
    return decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "새 기준문서를 적용할 수 있는가?",
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
                }
            ],
        }
    )


def test_new_reference_pauses_then_resumes_same_request(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "RUN-001"
    request = _request(run_dir)
    original_hash = review_request_sha256(request)

    layout = prepare_review_run(
        runs_root,
        "RUN-001",
        request,
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    assert layout.load_state().workflow_state == "PENDING_REFERENCE_INGESTION"

    backend = FakeReferenceBackend()
    receipt = ingest_pending_references(layout, backend)
    assert backend.calls == [("ATT-REF-001",)]
    assert receipt.request_sha256 == original_hash
    assert layout.load_state().workflow_state == "PENDING_REFERENCE_INGESTION"

    final = resume_review_run(
        layout,
        recorded_at="2026-08-04T00:01:00+09:00",
    )
    assert final.workflow_state == "READY_TO_EVALUATE"
    assert layout.load_request_sha256() == original_hash
    assert review_request_sha256(layout.load_request()) == original_hash

    assert tuple(event.next_state for event in load_workflow_events(layout.events_dir)) == (
        "RECEIVED",
        "CLASSIFYING_INPUTS",
        "PENDING_REFERENCE_INGESTION",
        "CLASSIFYING_INPUTS",
        "READY_TO_EVALUATE",
    )


def test_reference_resume_preserves_pending_drawing_lane(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "RUN-001"
    reference_hash, reference_size = write_source(
        run_dir / "inputs" / "original" / "reference.pdf",
        b"reference-v1",
    )
    drawing_hash, drawing_size = write_source(
        run_dir / "inputs" / "original" / "drawing.pdf",
        b"drawing-v1",
    )
    request = decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "기준문서와 도면을 함께 검토할 수 있는가?",
            "attachments": [
                {
                    "attachment_id": "ATT-REF-001",
                    "original_name": "reference.pdf",
                    "stored_path": "inputs/original/reference.pdf",
                    "sha256": reference_hash,
                    "byte_size": reference_size,
                    "mime": "application/pdf",
                    "role": "REFERENCE_DOCUMENT",
                    "role_confirmation": "USER_CONFIRMED",
                    "proposed_role": None,
                },
                {
                    "attachment_id": "ATT-DRAWING-001",
                    "original_name": "drawing.pdf",
                    "stored_path": "inputs/original/drawing.pdf",
                    "sha256": drawing_hash,
                    "byte_size": drawing_size,
                    "mime": "application/pdf",
                    "role": "CASE_DRAWING",
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
    assert layout.load_state().workflow_state == "PENDING_REFERENCE_INGESTION"

    ingest_pending_references(layout, FakeReferenceBackend())
    resumed = resume_review_run(
        layout,
        recorded_at="2026-08-04T00:01:00+09:00",
    )
    assert resumed.workflow_state == "PENDING_DRAWING_INGESTION"
    assert tuple(event.next_state for event in load_workflow_events(layout.events_dir)) == (
        "RECEIVED",
        "CLASSIFYING_INPUTS",
        "PENDING_REFERENCE_INGESTION",
        "CLASSIFYING_INPUTS",
        "PENDING_DRAWING_INGESTION",
    )

    event_count = len(load_workflow_events(layout.events_dir))
    repeated = resume_review_run(
        layout,
        recorded_at="2026-08-04T00:02:00+09:00",
    )
    assert repeated.workflow_state == "PENDING_DRAWING_INGESTION"
    assert len(load_workflow_events(layout.events_dir)) == event_count


def test_reference_source_tamper_blocks_ingestion(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "RUN-001"
    request = _request(run_dir)
    layout = prepare_review_run(
        runs_root,
        "RUN-001",
        request,
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    (run_dir / "inputs" / "original" / "reference.pdf").write_bytes(b"tampered")

    backend = FakeReferenceBackend()
    try:
        ingest_pending_references(layout, backend)
    except ValueError as exc:
        assert "SOURCE_HASH_MISMATCH" in str(exc)
    else:
        raise AssertionError("tampered immutable source must be rejected")
    assert backend.calls == []
    assert not layout.reference_receipt_path.exists()
