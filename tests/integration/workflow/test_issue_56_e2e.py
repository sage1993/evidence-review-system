from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import ansim_review.workflow.engine_orchestration as orchestration
from ansim_review.contracts.attachments import ImmutableAttachment
from ansim_review.parsing.drawing_quality import (
    TrustedSourceMetadata,
    assess_drawing_quality,
)
from ansim_review.parsing.drawing_source import DrawingIntakePolicy
from ansim_review.workflow.drawing_confirmation import start_drawing_confirmation
from ansim_review.workflow.engine_orchestration import run_deterministic_stages
from ansim_review.workflow.orchestrator import (
    ingest_pending_references,
    prepare_review_run,
    resume_review_run,
)
from ansim_review.workflow.request import decode_review_request
from tests.integration.workflow._reference_helpers import FakeReferenceBackend


def _request(question: str, attachments: list[dict[str, object]]):
    return decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": question,
            "attachments": attachments,
        }
    )


def _attachment(
    attachment_id: str,
    name: str,
    content: bytes,
    role: str,
    mime: str,
) -> tuple[dict[str, object], str]:
    digest = hashlib.sha256(content).hexdigest()
    return (
        {
            "attachment_id": attachment_id,
            "original_name": name,
            "stored_path": f"inputs/original/{name}",
            "sha256": digest,
            "byte_size": len(content),
            "mime": mime,
            "role": role,
            "role_confirmation": "USER_CONFIRMED",
            "proposed_role": None,
        },
        digest,
    )


def test_existing_db_question_reaches_track_a_gate(tmp_path: Path) -> None:
    layout = prepare_review_run(
        tmp_path / "runs",
        "RUN-001",
        _request("기존 DB로 질문에 답할 수 있는가?", []),
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    run_deterministic_stages(
        layout,
        retrieval={"source": "existing-db"},
        math={"status": "SUCCESS"},
        rules={"status": "SATISFIED"},
    )
    assert layout.load_state().workflow_state == "WAITING_TRACK_A"


def test_new_reference_pdf_question_resumes_then_reaches_engine_gate(tmp_path: Path) -> None:
    content = b"reference-pdf-fixture"
    attachment, _ = _attachment(
        "ATT-REF-001", "reference.pdf", content, "REFERENCE_DOCUMENT", "application/pdf"
    )
    run_dir = tmp_path / "runs" / "RUN-001"
    source = run_dir / "inputs" / "original" / "reference.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(content)
    layout = prepare_review_run(
        tmp_path / "runs",
        "RUN-001",
        _request("신규 기준 PDF를 적용할 수 있는가?", [attachment]),
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    ingest_pending_references(layout, FakeReferenceBackend())
    resumed = resume_review_run(
        layout,
        recorded_at="2026-08-04T00:01:00+09:00",
    )
    assert resumed.workflow_state == "READY_TO_EVALUATE"


def test_a3_600dpi_drawing_stops_at_confirmation(tmp_path: Path) -> None:
    content = b"a3-600dpi-drawing-fixture"
    attachment, source_hash = _attachment(
        "ATT-DRAW-001", "a3.pdf", content, "CASE_DRAWING", "application/pdf"
    )
    run_dir = tmp_path / "runs" / "RUN-001"
    source = run_dir / "inputs" / "original" / "a3.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(content)
    layout = prepare_review_run(
        tmp_path / "runs",
        "RUN-001",
        _request("A3 600dpi 도면 값을 확인할 수 있는가?", [attachment]),
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    plan = start_drawing_confirmation(
        layout,
        candidate_ids=("CAND-A3-001",),
        source_sha256=source_hash,
        recorded_at="2026-08-04T00:01:00+09:00",
    )
    assert plan.engine_allowed is False
    assert layout.load_state().workflow_state == "INPUT_CONFIRMATION_REQUIRED"


def test_200dpi_jpeg_quality_gate_does_not_enter_engine(tmp_path: Path) -> None:
    content = b"jpeg-200dpi-fixture"
    digest = hashlib.sha256(content).hexdigest()
    attachment = ImmutableAttachment(
        attachment_id="ATT-JPEG-001",
        original_name="drawing.jpg",
        stored_path="inputs/original/ATT-JPEG-001.jpg",
        sha256=digest,
        byte_size=len(content),
        mime="image/jpeg",
        role="CASE_DRAWING",
    )
    quality = assess_drawing_quality(
        attachment,
        TrustedSourceMetadata(
            source_sha256=digest,
            adapter="fixture",
            adapter_version="1",
            parser_outcome="SUCCESS",
            page_count=None,
            width=1654,
            height=2339,
            physical_size_trust="METADATA_ONLY",
            lossy_or_screen_capture=True,
        ),
        DrawingIntakePolicy(),
    )
    assert quality.assessment.quality == "REVIEW_REQUIRED"
    assert "LOSSY_OR_SCREEN_CAPTURE_SOURCE" in quality.detailed_reasons


def test_interrupted_confirmation_run_resumes_without_replaying_retrieval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    layout = prepare_review_run(
        tmp_path / "runs",
        "RUN-001",
        _request("중단 후 재개할 수 있는가?", []),
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    original = orchestration._write_stage

    def stop_at_math(*args, **kwargs):
        if args[1] == "RUNNING_MATH":
            raise RuntimeError("interrupted")
        return original(*args, **kwargs)

    monkeypatch.setattr(orchestration, "_write_stage", stop_at_math)
    with pytest.raises(RuntimeError, match="interrupted"):
        run_deterministic_stages(
            layout,
            retrieval={"source": "resume"},
            math={"status": "SUCCESS"},
            rules={"status": "SATISFIED"},
        )
    monkeypatch.setattr(orchestration, "_write_stage", original)
    run_deterministic_stages(
        layout,
        retrieval={"source": "resume"},
        math={"status": "SUCCESS"},
        rules={"status": "SATISFIED"},
    )
    assert layout.load_state().workflow_state == "WAITING_TRACK_A"
