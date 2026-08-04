from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ansim_review.workflow.drawing_confirmation import (
    resume_after_confirmation,
    start_drawing_confirmation,
)
from ansim_review.workflow.orchestrator import prepare_review_run
from ansim_review.workflow.request import decode_review_request


def test_drawing_confirmation_is_a_pause_before_engine_entry(tmp_path: Path) -> None:
    source = b"drawing-source"
    source_hash = hashlib.sha256(source).hexdigest()
    source_path = tmp_path / "runs" / "RUN-001" / "inputs" / "original" / "drawing.pdf"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source)
    request = decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "도면 확인이 필요한가?",
            "attachments": [
                {
                    "attachment_id": "ATT-DRAW-001",
                    "original_name": "drawing.pdf",
                    "stored_path": "inputs/original/drawing.pdf",
                    "sha256": source_hash,
                    "byte_size": len(source),
                    "mime": "application/pdf",
                    "role": "CASE_DRAWING",
                    "role_confirmation": "USER_CONFIRMED",
                    "proposed_role": None,
                }
            ],
        }
    )
    layout = prepare_review_run(
        tmp_path / "runs",
        "RUN-001",
        request,
        recorded_at="2026-08-04T00:00:00+09:00",
    )

    plan = start_drawing_confirmation(
        layout,
        candidate_ids=("CAND-001",),
        source_sha256=source_hash,
        recorded_at="2026-08-04T00:01:00+09:00",
    )

    assert plan.engine_allowed is False
    assert layout.load_state().workflow_state == "INPUT_CONFIRMATION_REQUIRED"
    assert (layout.machine_dir / "drawing-confirmation.json").is_file()


def test_confirmed_input_resumes_the_same_run_at_engine_gate(tmp_path: Path) -> None:
    source = b"drawing-source"
    source_hash = hashlib.sha256(source).hexdigest()
    run_dir = tmp_path / "runs" / "RUN-001"
    source_path = run_dir / "inputs" / "original" / "drawing.pdf"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source)
    request = decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "확인된 도면 값을 사용할 수 있는가?",
            "attachments": [
                {
                    "attachment_id": "ATT-DRAW-001",
                    "original_name": "drawing.pdf",
                    "stored_path": "inputs/original/drawing.pdf",
                    "sha256": source_hash,
                    "byte_size": len(source),
                    "mime": "application/pdf",
                    "role": "CASE_DRAWING",
                    "role_confirmation": "USER_CONFIRMED",
                    "proposed_role": None,
                }
            ],
        }
    )
    layout = prepare_review_run(
        tmp_path / "runs",
        "RUN-001",
        request,
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    start_drawing_confirmation(
        layout,
        candidate_ids=("CAND-001",),
        source_sha256=source_hash,
        recorded_at="2026-08-04T00:01:00+09:00",
    )
    confirmed_path = layout.machine_dir / "confirmed-inputs.json"
    confirmed_path.write_bytes(
        b'{"format":"evidence-review/confirmed-input-set","inputs":[],"version":1}'
    )

    resumed = resume_after_confirmation(
        layout,
        confirmed_inputs_path=confirmed_path,
        source_sha256=source_hash,
        recorded_at="2026-08-04T00:02:00+09:00",
    )

    assert resumed.engine_allowed is True
    assert layout.load_state().workflow_state == "READY_TO_EVALUATE"


def test_confirmation_resume_rejects_noncanonical_input_artifact(tmp_path: Path) -> None:
    source = b"drawing-source"
    source_hash = hashlib.sha256(source).hexdigest()
    run_dir = tmp_path / "runs" / "RUN-001"
    source_path = run_dir / "inputs" / "original" / "drawing.pdf"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source)
    request = decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "?뺤씤???꾨㈃ 媛믪쓣 ?ъ슜?????덈뒗媛?",
            "attachments": [
                {
                    "attachment_id": "ATT-DRAW-001",
                    "original_name": "drawing.pdf",
                    "stored_path": "inputs/original/drawing.pdf",
                    "sha256": source_hash,
                    "byte_size": len(source),
                    "mime": "application/pdf",
                    "role": "CASE_DRAWING",
                    "role_confirmation": "USER_CONFIRMED",
                    "proposed_role": None,
                }
            ],
        }
    )
    layout = prepare_review_run(
        tmp_path / "runs",
        "RUN-001",
        request,
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    start_drawing_confirmation(
        layout,
        candidate_ids=("CAND-001",),
        source_sha256=source_hash,
        recorded_at="2026-08-04T00:01:00+09:00",
    )
    confirmed_path = layout.machine_dir / "confirmed-inputs.json"
    confirmed_path.write_bytes(b'{"inputs":[]}')

    with pytest.raises(ValueError, match="confirmed-input-set"):
        resume_after_confirmation(
            layout,
            confirmed_inputs_path=confirmed_path,
            source_sha256=source_hash,
            recorded_at="2026-08-04T00:02:00+09:00",
        )
