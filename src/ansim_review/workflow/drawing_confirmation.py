"""Fail-closed drawing confirmation planning for review runs."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.attachments import ImmutableAttachment
from ansim_review.contracts.drawing import (
    ConfirmedInput,
    decode_confirmed_input,
)
from ansim_review.contracts.formats import (
    CONFIRMED_INPUT_SET_FORMAT,
    WORKFLOW_STATE_FORMAT,
)
from ansim_review.contracts.identifiers import validate_identifier
from ansim_review.contracts.validation import expect_sha256
from ansim_review.contracts.workflow import WorkflowState
from ansim_review.parsing.drawing_binding import bind_confirmed_inputs
from ansim_review.parsing.drawing_case import CaseManifestEntry
from ansim_review.parsing.drawing_inputs import (
    confirmed_inputs_document,
    validate_confirmed_input_set,
)
from ansim_review.parsing.drawing_workflow import (
    DrawingWorkflowFacts,
    project_drawing_workflow,
)
from ansim_review.workflow.events import (
    append_workflow_event,
    load_workflow_events,
    make_workflow_event,
)
from ansim_review.workflow.run_layout import ReviewRunLayout


@dataclass(frozen=True, slots=True)
class DrawingConfirmationPlan:
    """Deterministic handoff from drawing candidates to engine eligibility."""

    format: str
    version: int
    run_id: str
    workflow_state: WorkflowState
    source_sha256: str
    confirmed_inputs_sha256: str | None
    candidate_urls: tuple[str, ...]
    engine_allowed: bool


def build_drawing_confirmation_plan(
    *,
    run_id: str,
    candidate_ids: tuple[str, ...],
    source_sha256: str,
    has_source: bool,
    has_validated_inputs: bool,
    confirmed_inputs_sha256: str | None = None,
    previous_source_sha256: str | None = None,
    quality_rejected: bool = False,
    has_conflict: bool = False,
    missing_required_inputs: bool = False,
) -> DrawingConfirmationPlan:
    """Project drawing facts and never grant engines authority prematurely."""
    validated_run_id = validate_identifier(run_id, "run_id")
    validated_source = expect_sha256(source_sha256, "source_sha256")
    if previous_source_sha256 is not None:
        previous = expect_sha256(previous_source_sha256, "previous_source_sha256")
        if previous != validated_source:
            raise ValueError("SOURCE_HASH_MISMATCH: drawing source changed")
    if confirmed_inputs_sha256 is not None:
        confirmed_inputs_sha256 = expect_sha256(
            confirmed_inputs_sha256,
            "confirmed_inputs_sha256",
        )
    validated_candidates = tuple(
        sorted(
            {
                validate_identifier(candidate_id, "candidate_id")
                for candidate_id in candidate_ids
            }
        )
    )
    if has_validated_inputs and confirmed_inputs_sha256 is None:
        raise ValueError("validated drawing inputs require confirmed_inputs_sha256")

    record = project_drawing_workflow(
        validated_run_id,
        DrawingWorkflowFacts(
            has_source=has_source,
            quality_rejected=quality_rejected,
            has_conflict=has_conflict,
            missing_required_inputs=missing_required_inputs,
            has_validated_inputs=has_validated_inputs,
        ),
    )
    if record.workflow_state == "READY_TO_EVALUATE" and not has_validated_inputs:
        raise ValueError("drawing workflow reached READY_TO_EVALUATE without inputs")
    candidate_urls = (
        tuple(
            f"/runs/{validated_run_id}/confirmation/{candidate_id}"
            for candidate_id in validated_candidates
        )
        if record.workflow_state == "INPUT_CONFIRMATION_REQUIRED"
        else ()
    )
    return DrawingConfirmationPlan(
        format=WORKFLOW_STATE_FORMAT,
        version=1,
        run_id=validated_run_id,
        workflow_state=record.workflow_state,
        source_sha256=validated_source,
        confirmed_inputs_sha256=confirmed_inputs_sha256,
        candidate_urls=candidate_urls,
        engine_allowed=record.workflow_state == "READY_TO_EVALUATE",
    )


def confirmation_plan_document(plan: DrawingConfirmationPlan) -> dict[str, object]:
    """Return canonical machine data for a confirmation handoff."""
    return {
        "format": plan.format,
        "version": plan.version,
        "run_id": plan.run_id,
        "workflow_state": plan.workflow_state,
        "source_sha256": plan.source_sha256,
        "confirmed_inputs_sha256": plan.confirmed_inputs_sha256,
        "candidate_urls": list(plan.candidate_urls),
        "engine_allowed": plan.engine_allowed,
    }


def persist_drawing_confirmation_plan(
    machine_dir: Path,
    plan: DrawingConfirmationPlan,
) -> Path:
    """Persist a confirmation handoff exactly once."""
    path = machine_dir / "drawing-confirmation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dump_bytes(confirmation_plan_document(plan))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def start_drawing_confirmation(
    layout: ReviewRunLayout,
    *,
    candidate_ids: tuple[str, ...],
    source_sha256: str,
    recorded_at: str,
) -> DrawingConfirmationPlan:
    """Create the drawing handoff and pause the run before any engine call."""
    request = layout.load_request()
    layout.verify_request_attachments(request)
    drawing_sources = tuple(
        attachment
        for attachment in request.attachments
        if attachment.role == "CASE_DRAWING"
    )
    if len(drawing_sources) != 1:
        raise ValueError("drawing confirmation requires exactly one CASE_DRAWING")
    if drawing_sources[0].sha256 != source_sha256:
        raise ValueError("SOURCE_HASH_MISMATCH: drawing source differs")

    plan = build_drawing_confirmation_plan(
        run_id=layout.run_id,
        candidate_ids=candidate_ids,
        source_sha256=source_sha256,
        has_source=True,
        has_validated_inputs=False,
    )
    if plan.workflow_state != "INPUT_CONFIRMATION_REQUIRED":
        raise ValueError("drawing confirmation plan must require reviewer input")
    plan_path = layout.machine_dir / "drawing-confirmation.json"
    if plan_path.exists():
        if plan_path.read_bytes() != dump_bytes(confirmation_plan_document(plan)):
            raise ValueError("existing drawing confirmation plan differs")
        return plan
    persist_drawing_confirmation_plan(layout.machine_dir, plan)

    events = load_workflow_events(layout.events_dir)
    if events and events[-1].next_state == "PENDING_DRAWING_INGESTION":
        payload_hash = hashlib.sha256(
            dump_bytes(confirmation_plan_document(plan))
        ).hexdigest()
        sequence = len(events) + 1
        append_workflow_event(
            layout.events_dir,
            make_workflow_event(
                run_id=layout.run_id,
                sequence=sequence,
                event_id=f"EVT-{sequence:04d}",
                kind="TRANSITION",
                previous_state=events[-1].next_state,
                next_state="INPUT_CONFIRMATION_REQUIRED",
                finalizer_status=None,
                reason_codes=(),
                resumable=False,
                payload_sha256=payload_hash,
                recorded_at=recorded_at,
            ),
        )
    elif not events or events[-1].next_state != "INPUT_CONFIRMATION_REQUIRED":
        raise ValueError("run is not waiting for drawing confirmation")
    return plan


def _load_confirmed_inputs(path: Path) -> tuple[ConfirmedInput, ...]:
    """Decode one canonical confirmed-input-set without trusting its hash alone."""
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("confirmed inputs must be valid UTF-8 JSON") from error
    if not isinstance(payload, Mapping):
        raise ValueError("confirmed inputs must be an object")
    if set(payload) != {"format", "inputs", "version"}:
        raise ValueError("confirmed inputs must be a confirmed-input-set")
    if payload.get("format") != CONFIRMED_INPUT_SET_FORMAT or payload.get("version") != 1:
        raise ValueError("confirmed inputs must be a confirmed-input-set")
    raw_inputs = payload.get("inputs")
    if isinstance(raw_inputs, (str, bytes, bytearray)) or not isinstance(raw_inputs, Sequence):
        raise ValueError("confirmed inputs must contain an inputs array")
    inputs = tuple(
        decode_confirmed_input(item)
        for item in raw_inputs
    )
    if validate_confirmed_input_set(inputs):
        raise ValueError("confirmed inputs contain unresolved conflicts")
    if raw != dump_bytes(confirmed_inputs_document(inputs)):
        raise ValueError("confirmed inputs must use canonical bytes")
    return inputs


def resume_after_confirmation(
    layout: ReviewRunLayout,
    *,
    confirmed_inputs_path: Path,
    source_sha256: str,
    recorded_at: str,
    case_dir: Path | None = None,
    source_attachments: Mapping[str, ImmutableAttachment] | None = None,
    candidate_entries: Mapping[str, CaseManifestEntry] | None = None,
) -> DrawingConfirmationPlan:
    """Revalidate confirmed-input bytes and resume the original run."""
    if layout.load_state().workflow_state != "INPUT_CONFIRMATION_REQUIRED":
        raise ValueError("run is not waiting for drawing confirmation")
    request = layout.load_request()
    layout.verify_request_attachments(request)
    drawing_sources = tuple(
        attachment
        for attachment in request.attachments
        if attachment.role == "CASE_DRAWING"
    )
    if len(drawing_sources) != 1 or drawing_sources[0].sha256 != source_sha256:
        raise ValueError("SOURCE_HASH_MISMATCH: drawing source differs")
    resolved_path = confirmed_inputs_path.resolve(strict=False)
    if not resolved_path.is_relative_to(layout.run_dir.resolve()):
        raise ValueError("confirmed inputs path escapes run directory")
    if not confirmed_inputs_path.is_file():
        raise FileNotFoundError(confirmed_inputs_path)
    confirmed_inputs = _load_confirmed_inputs(confirmed_inputs_path)
    if any(item.source_sha256 != source_sha256 for item in confirmed_inputs):
        raise ValueError("SOURCE_HASH_MISMATCH: confirmed input source differs")
    binding_values = (case_dir, source_attachments, candidate_entries)
    if any(value is not None for value in binding_values) and not all(
        value is not None for value in binding_values
    ):
        raise ValueError(
            "case_dir, source_attachments, and candidate_entries must be supplied together"
        )
    if case_dir is not None and source_attachments is not None and candidate_entries is not None:
        bind_confirmed_inputs(
            case_dir,
            confirmed_inputs,
            source_attachments,
            candidate_entries=candidate_entries,
        )
    confirmed_hash = hashlib.sha256(confirmed_inputs_path.read_bytes()).hexdigest()
    plan = build_drawing_confirmation_plan(
        run_id=layout.run_id,
        candidate_ids=(),
        source_sha256=source_sha256,
        has_source=True,
        has_validated_inputs=True,
        confirmed_inputs_sha256=confirmed_hash,
    )
    events = load_workflow_events(layout.events_dir)
    payload_hash = hashlib.sha256(
        dump_bytes(confirmation_plan_document(plan))
    ).hexdigest()
    sequence = len(events) + 1
    append_workflow_event(
        layout.events_dir,
        make_workflow_event(
            run_id=layout.run_id,
            sequence=sequence,
            event_id=f"EVT-{sequence:04d}",
            kind="TRANSITION",
            previous_state=events[-1].next_state,
            next_state="READY_TO_EVALUATE",
            finalizer_status=None,
            reason_codes=(),
            resumable=False,
            payload_sha256=payload_hash,
            recorded_at=recorded_at,
        ),
    )
    return plan


__all__ = [
    "DrawingConfirmationPlan",
    "build_drawing_confirmation_plan",
    "confirmation_plan_document",
    "persist_drawing_confirmation_plan",
    "resume_after_confirmation",
    "start_drawing_confirmation",
]
