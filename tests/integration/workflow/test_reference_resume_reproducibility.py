from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review import canonical_json
from evidence_review.workflow.events import load_workflow_events
from evidence_review.workflow.orchestrator import (
    ingest_pending_references,
    open_review_run,
    prepare_review_run,
    resume_review_run,
)
from evidence_review.workflow.request import decode_review_request
from tests.integration.workflow._reference_helpers import (
    FakeReferenceBackend,
    write_source,
)


def _prepare(tmp_path: Path):
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "RUN-001"
    digest, size = write_source(
        run_dir / "inputs" / "original" / "reference.pdf",
        b"reference-v1",
    )
    request = decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "중단 후 같은 질문을 재개할 수 있는가?",
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
    layout = prepare_review_run(
        runs_root,
        "RUN-001",
        request,
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    return runs_root, layout


def test_restart_after_receipt_skips_completed_ingestion(tmp_path: Path) -> None:
    runs_root, layout = _prepare(tmp_path)
    first_backend = FakeReferenceBackend()
    first_receipt = ingest_pending_references(layout, first_backend)
    receipt_bytes = layout.reference_receipt_path.read_bytes()

    reopened = open_review_run(runs_root, "RUN-001")
    second_backend = FakeReferenceBackend(snapshot_sha256="c" * 64)
    second_receipt = ingest_pending_references(reopened, second_backend)
    assert second_backend.calls == []
    assert second_receipt == first_receipt
    assert reopened.reference_receipt_path.read_bytes() == receipt_bytes

    final = resume_review_run(
        reopened,
        recorded_at="2026-08-04T00:01:00+09:00",
    )
    assert final.workflow_state == "READY_TO_EVALUATE"

    event_bytes = tuple(
        path.read_bytes()
        for path in sorted(reopened.events_dir.glob("*.json"))
    )
    repeated = resume_review_run(
        reopened,
        recorded_at="2026-08-04T00:02:00+09:00",
    )
    assert repeated == final
    assert tuple(
        path.read_bytes()
        for path in sorted(reopened.events_dir.glob("*.json"))
    ) == event_bytes
    assert len(load_workflow_events(reopened.events_dir)) == 5


def test_request_tamper_prevents_resume(tmp_path: Path) -> None:
    runs_root, layout = _prepare(tmp_path)
    ingest_pending_references(layout, FakeReferenceBackend())
    layout.request_path.write_text("{}\n", encoding="utf-8")

    try:
        reopened = open_review_run(runs_root, "RUN-001")
        resume_review_run(
            reopened,
            recorded_at="2026-08-04T00:01:00+09:00",
        )
    except ValueError as exc:
        assert "request" in str(exc).lower()
    else:
        raise AssertionError("tampered request must prevent resume")


def test_output_database_tamper_prevents_resume(tmp_path: Path) -> None:
    runs_root, layout = _prepare(tmp_path)
    ingest_pending_references(layout, FakeReferenceBackend())
    (layout.machine_dir / "evidence.sqlite").write_bytes(b"tampered-db")

    reopened = open_review_run(runs_root, "RUN-001")
    try:
        resume_review_run(
            reopened,
            recorded_at="2026-08-04T00:01:00+09:00",
        )
    except ValueError as exc:
        assert "output database" in str(exc).lower()
    else:
        raise AssertionError("tampered evidence database must prevent resume")


def test_receipt_tamper_prevents_resume(tmp_path: Path) -> None:
    runs_root, layout = _prepare(tmp_path)
    ingest_pending_references(layout, FakeReferenceBackend())
    receipt = json.loads(layout.reference_receipt_path.read_text(encoding="utf-8"))
    receipt["sources"][0]["document_id"] = "DOC-FORGED"
    layout.reference_receipt_path.write_bytes(
        canonical_json.dump_bytes(receipt) + b"\n"
    )

    reopened = open_review_run(runs_root, "RUN-001")
    with pytest.raises(ValueError, match="receipt"):
        resume_review_run(
            reopened,
            recorded_at="2026-08-04T00:01:00+09:00",
        )
