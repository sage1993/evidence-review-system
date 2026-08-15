"""Ordered, hash-bound orchestration around deterministic engine outputs."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.next_action import next_action_document
from evidence_review.contracts.review import FinalizerStatus
from evidence_review.contracts.workflow import ReasonCode, WorkflowState
from evidence_review.workflow.events import (
    append_workflow_event,
    load_workflow_events,
    make_workflow_event,
)
from evidence_review.workflow.run_layout import ReviewRunLayout

StageName = Literal["RETRIEVING_EVIDENCE", "RUNNING_MATH", "RUNNING_RULES"]

_STAGES: tuple[tuple[StageName, str, WorkflowState], ...] = (
    ("RETRIEVING_EVIDENCE", "retrieval.json", "RETRIEVING_EVIDENCE"),
    ("RUNNING_MATH", "math.json", "RUNNING_MATH"),
    ("RUNNING_RULES", "rules.json", "RUNNING_RULES"),
)


@dataclass(frozen=True, slots=True)
class DeterministicStageResult:
    """One persisted deterministic stage result."""

    stage: StageName
    artifact_path: Path
    input_sha256: str
    output_sha256: str


def _write_create_only(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _stage_document(
    layout: ReviewRunLayout,
    stage: StageName,
    input_sha256: str,
    payload: object,
) -> bytes:
    return dump_bytes(
        {
            "format": "evidence-review/deterministic-stage",
            "version": 1,
            "run_id": layout.run_id,
            "stage": stage,
            "input_sha256": input_sha256,
            "payload": payload,
        }
    )


def _append_transition(
    layout: ReviewRunLayout,
    *,
    next_state: WorkflowState,
    payload_sha256: str,
    recorded_at: str,
    reason_codes: tuple[ReasonCode, ...] = (),
    resumable: bool = False,
    finalizer_status: FinalizerStatus | None = None,
) -> None:
    events = load_workflow_events(layout.events_dir)
    if events and events[-1].next_state == next_state:
        return
    if not events:
        raise ValueError("workflow journal is empty")
    sequence = len(events) + 1
    append_workflow_event(
        layout.events_dir,
        make_workflow_event(
            run_id=layout.run_id,
            sequence=sequence,
            event_id=f"EVT-{sequence:04d}",
            kind="TRANSITION",
            previous_state=events[-1].next_state,
            next_state=next_state,
            finalizer_status=finalizer_status,
            reason_codes=reason_codes,
            resumable=resumable,
            payload_sha256=payload_sha256,
            recorded_at=recorded_at,
        ),
    )


def _write_stage(
    layout: ReviewRunLayout,
    stage: StageName,
    filename: str,
    input_sha256: str,
    payload: object,
) -> DeterministicStageResult:
    encoded = _stage_document(layout, stage, input_sha256, payload)
    path = layout.machine_dir / filename
    if path.exists():
        existing = path.read_bytes()
        if existing != encoded:
            raise ValueError(f"existing deterministic artifact differs: {filename}")
    else:
        _write_create_only(path, encoded)
    return DeterministicStageResult(
        stage=stage,
        artifact_path=path,
        input_sha256=input_sha256,
        output_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def _write_track_a_action(layout: ReviewRunLayout) -> Path:
    from evidence_review.contracts.next_action import NextAction

    path = layout.machine_dir / "next-action.json"
    action = NextAction(
        format="evidence-review/next-action",
        version=1,
        run_id=layout.run_id,
        workflow_state="WAITING_TRACK_A",
        action="PRODUCE_TRACK_A",
        input_bundle="machine/rules.json",
        instructions="machine/track-a-instructions.md",
        expected_output="track-a-output.json",
        resume_command=(
            "python",
            "-m",
            "evidence_review",
            "review-run",
            "resume",
            "--run-id",
            layout.run_id,
        ),
        track_a_validated=False,
    )
    encoded = dump_bytes(next_action_document(action))
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("existing Track A action differs")
    else:
        _write_create_only(path, encoded)
    return path


def run_deterministic_stages(
    layout: ReviewRunLayout,
    *,
    retrieval: object,
    math: object,
    rules: object,
    recorded_at: str = "2026-01-01T00:00:00+00:00",
) -> tuple[DeterministicStageResult, ...]:
    """Persist retrieval, Math, and Rule outputs in exactly that order."""
    state = layout.load_state().workflow_state
    completed_count = {
        "READY_TO_EVALUATE": 0,
        "RETRIEVING_EVIDENCE": 1,
        "RUNNING_MATH": 2,
        "RUNNING_RULES": 3,
        "WAITING_TRACK_A": 3,
    }.get(state)
    if completed_count is None:
        raise ValueError("deterministic stages require an evaluable workflow state")
    payloads: tuple[object, object, object] = (retrieval, math, rules)
    results: list[DeterministicStageResult] = []
    input_sha256 = layout.load_request_sha256()
    for index, ((stage, filename, stage_state), payload) in enumerate(
        zip(_STAGES, payloads, strict=True)
    ):
        encoded = _stage_document(layout, stage, input_sha256, payload)
        if index < completed_count:
            path = layout.machine_dir / filename
            if not path.is_file() or path.read_bytes() != encoded:
                raise ValueError(f"completed deterministic artifact cannot be resumed: {filename}")
            result = DeterministicStageResult(
                stage=stage,
                artifact_path=path,
                input_sha256=input_sha256,
                output_sha256=hashlib.sha256(encoded).hexdigest(),
            )
        else:
            result = _write_stage(layout, stage, filename, input_sha256, payload)
        results.append(result)
        if index >= completed_count:
            _append_transition(
                layout,
                next_state=stage_state,
                payload_sha256=result.output_sha256,
                recorded_at=recorded_at,
            )
        input_sha256 = result.output_sha256
    _append_transition(
        layout,
        next_state="WAITING_TRACK_A",
        payload_sha256=results[-1].output_sha256,
        recorded_at=recorded_at,
    )
    _write_track_a_action(layout)
    return tuple(results)


def advance_to_track_b(
    layout: ReviewRunLayout,
    *,
    track_a_sha256: str,
    recorded_at: str,
) -> Path:
    """Record validated Track A and emit the independent Track B handoff."""
    if layout.load_state().workflow_state != "WAITING_TRACK_A":
        raise ValueError("run is not waiting for Track A")
    if len(track_a_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in track_a_sha256
    ):
        raise ValueError("track_a_sha256 must be lowercase SHA-256")
    validation = dump_bytes(
        {
            "format": "evidence-review/track-a-validation",
            "version": 1,
            "run_id": layout.run_id,
            "track_a_sha256": track_a_sha256,
            "validated": True,
        }
    )
    validation_path = layout.machine_dir / "track-a-validation.json"
    if validation_path.exists():
        if validation_path.read_bytes() != validation:
            raise ValueError("existing Track A validation differs")
    else:
        _write_create_only(validation_path, validation)
    validation_hash = hashlib.sha256(validation).hexdigest()
    _append_transition(
        layout,
        next_state="WAITING_TRACK_B",
        payload_sha256=validation_hash,
        recorded_at=recorded_at,
    )
    from evidence_review.contracts.next_action import NextAction

    action = NextAction(
        format="evidence-review/next-action",
        version=1,
        run_id=layout.run_id,
        workflow_state="WAITING_TRACK_B",
        action="PRODUCE_TRACK_B",
        input_bundle="machine/track-a-validation.json",
        instructions="machine/track-b-instructions.md",
        expected_output="track-b-output.json",
        resume_command=(
            "python",
            "-m",
            "evidence_review",
            "review-run",
            "resume",
            "--run-id",
            layout.run_id,
        ),
        track_a_validated=True,
    )
    action_bytes = dump_bytes(next_action_document(action))
    action_path = layout.machine_dir / "next-action-track-b.json"
    if action_path.exists():
        if action_path.read_bytes() != action_bytes:
            raise ValueError("existing Track B action differs")
    else:
        _write_create_only(action_path, action_bytes)
    return action_path


def require_track_b_acceptance(
    layout: ReviewRunLayout,
    track_b: object,
    *,
    recorded_at: str,
) -> None:
    """Allow finalization only when Track B independently accepts all claims."""
    if layout.load_state().workflow_state != "WAITING_TRACK_B":
        raise ValueError("run is not waiting for Track B")
    disposition = track_b.get("overall_disposition") if isinstance(track_b, Mapping) else None
    payload = dump_bytes(track_b)
    payload_hash = hashlib.sha256(payload).hexdigest()
    if disposition != "ACCEPT":
        _append_transition(
            layout,
            next_state="BLOCKED",
            payload_sha256=payload_hash,
            recorded_at=recorded_at,
            reason_codes=("TRACK_B_REJECTED",),
            resumable=True,
        )
        raise ValueError("TRACK_B_REJECTED: finalization is blocked")
    _append_transition(
        layout,
        next_state="FINALIZING",
        payload_sha256=payload_hash,
        recorded_at=recorded_at,
    )


def finalize_orchestration_run(
    layout: ReviewRunLayout,
    *,
    recorded_at: str,
) -> Path:
    """Run the governed finalizer and publish the human-review state transition."""
    if layout.load_state().workflow_state != "FINALIZING":
        raise ValueError("run is not ready for finalization")
    from evidence_review.abstention.finalizer import finalize_run

    packet_path = layout.run_dir / "final-review-packet.json"
    packet = finalize_run(layout.run_dir)
    if not packet_path.is_file():
        raise ValueError("finalizer did not publish final-review-packet.json")
    finalizer_status = getattr(packet, "status", None)
    if finalizer_status not in {"READY_FOR_HUMAN_REVIEW", "ABSTAIN"}:
        try:
            finalizer_status = json.loads(packet_path.read_text(encoding="utf-8"))[
                "status"
            ]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("finalizer packet has no valid status") from error
    if finalizer_status not in {"READY_FOR_HUMAN_REVIEW", "ABSTAIN"}:
        raise ValueError("finalizer packet has an unsupported status")
    packet_hash = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    _append_transition(
        layout,
        next_state="READY_FOR_REVIEW",
        payload_sha256=packet_hash,
        recorded_at=recorded_at,
        finalizer_status=finalizer_status,
    )
    return packet_path


__all__ = [
    "DeterministicStageResult",
    "advance_to_track_b",
    "finalize_orchestration_run",
    "require_track_b_acceptance",
    "run_deterministic_stages",
]
