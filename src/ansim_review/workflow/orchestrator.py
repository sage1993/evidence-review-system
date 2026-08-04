"""Foundation orchestration for pausing and resuming reference ingestion."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ansim_review.contracts.attachments import ImmutableAttachment
from ansim_review.contracts.workflow import WorkflowState, WorkflowStateRecord
from ansim_review.workflow.events import (
    append_workflow_event,
    load_workflow_events,
    make_workflow_event,
)
from ansim_review.workflow.reference_ingestion import (
    ReferenceIngestionBackend,
    ReferenceIngestionReceipt,
    load_reference_ingestion_receipt,
    make_reference_ingestion_receipt,
    persist_reference_ingestion_receipt,
    reference_ingestion_receipt_sha256,
)
from ansim_review.workflow.request import (
    ReviewRequest,
    confirmed_attachments,
    requires_role_confirmation,
    review_request_sha256,
)
from ansim_review.workflow.run_layout import (
    ReviewRunLayout,
    initialize_review_run,
    open_review_run,
    reject_link_ancestors,
)
from ansim_review.workflow.state_machine import EventKind


def _reference_attachments(
    request: ReviewRequest,
) -> tuple[ImmutableAttachment, ...]:
    return tuple(
        attachment
        for attachment in confirmed_attachments(request)
        if attachment.role in {"REFERENCE_DOCUMENT", "CASE_TABLE"}
    )


def _has_drawing(request: ReviewRequest) -> bool:
    return any(
        attachment.role == "CASE_DRAWING"
        for attachment in confirmed_attachments(request)
    )


def _append_state(
    layout: ReviewRunLayout,
    *,
    next_state: WorkflowState,
    payload_sha256: str,
    recorded_at: str,
    kind: EventKind = "TRANSITION",
) -> WorkflowStateRecord:
    existing = load_workflow_events(layout.events_dir)
    previous = existing[-1].next_state if existing else None
    sequence = len(existing) + 1
    event = make_workflow_event(
        run_id=layout.run_id,
        sequence=sequence,
        event_id=f"EVT-{sequence:04d}",
        kind=kind,
        previous_state=previous,
        next_state=next_state,
        finalizer_status=None,
        reason_codes=(),
        resumable=False,
        payload_sha256=payload_sha256,
        recorded_at=recorded_at,
    )
    append_workflow_event(layout.events_dir, event)
    return layout.load_state()


def prepare_review_run(
    runs_root: Path,
    run_id: str,
    request: ReviewRequest,
    *,
    recorded_at: str,
) -> ReviewRunLayout:
    """Freeze the request and pause at the first preparation lane."""
    layout = initialize_review_run(runs_root, run_id, request)
    existing = load_workflow_events(layout.events_dir)
    if existing:
        stored = layout.load_request()
        if review_request_sha256(stored) != review_request_sha256(request):
            raise ValueError("existing run request differs from supplied request")
        return layout

    request_hash = review_request_sha256(request)
    _append_state(
        layout,
        next_state="RECEIVED",
        payload_sha256=request_hash,
        recorded_at=recorded_at,
    )
    _append_state(
        layout,
        next_state="CLASSIFYING_INPUTS",
        payload_sha256=request_hash,
        recorded_at=recorded_at,
    )
    next_state: WorkflowState
    if requires_role_confirmation(request):
        next_state = "ROLE_CONFIRMATION_REQUIRED"
    elif _reference_attachments(request):
        next_state = "PENDING_REFERENCE_INGESTION"
    elif _has_drawing(request):
        next_state = "PENDING_DRAWING_INGESTION"
    else:
        next_state = "READY_TO_EVALUATE"
    _append_state(
        layout,
        next_state=next_state,
        payload_sha256=request_hash,
        recorded_at=recorded_at,
    )
    return layout


def ingest_pending_references(
    layout: ReviewRunLayout,
    backend: ReferenceIngestionBackend,
) -> ReferenceIngestionReceipt:
    """Ingest once and persist a create-only receipt before state advance."""
    request = layout.load_request()
    layout.verify_request_attachments(request)
    state = layout.load_state()
    if state.workflow_state not in {
        "PENDING_REFERENCE_INGESTION",
        "PENDING_DRAWING_INGESTION",
        "READY_TO_EVALUATE",
    }:
        raise ValueError("run is not awaiting reference ingestion")
    if layout.reference_receipt_path.exists():
        return load_reference_ingestion_receipt(layout)

    attachments = _reference_attachments(request)
    if not attachments:
        raise ValueError("review request contains no reference attachments")
    if state.workflow_state != "PENDING_REFERENCE_INGESTION":
        raise ValueError("reference receipt is missing after reference lane completion")
    result = backend.ingest(
        request=request,
        attachments=attachments,
        run_dir=layout.run_dir,
    )
    receipt = make_reference_ingestion_receipt(request, attachments, result)
    output_path = layout.run_dir.joinpath(
        *receipt.output_db_relative_path.split("/")
    )
    if not output_path.resolve(strict=False).is_relative_to(
        layout.run_dir.resolve()
    ):
        raise ValueError("reference ingestion output escapes run directory")
    if not output_path.is_file():
        raise ValueError(
            "reference ingestion backend did not publish its output database"
        )
    reject_link_ancestors(output_path)
    output_payload = output_path.read_bytes()
    if len(output_payload) != receipt.output_db_byte_size:
        raise ValueError("reference ingestion backend reported a wrong DB size")
    if hashlib.sha256(output_payload).hexdigest() != receipt.output_db_sha256:
        raise ValueError("reference ingestion backend reported a wrong DB hash")
    persist_reference_ingestion_receipt(layout, receipt)
    return load_reference_ingestion_receipt(layout)


def resume_review_run(
    layout: ReviewRunLayout,
    *,
    recorded_at: str,
) -> WorkflowStateRecord:
    """Resume only after the exact reference receipt validates."""
    request = layout.load_request()
    layout.verify_request_attachments(request)
    state = layout.load_state()
    references = _reference_attachments(request)
    if state.workflow_state in {
        "PENDING_DRAWING_INGESTION",
        "READY_TO_EVALUATE",
    }:
        if references:
            load_reference_ingestion_receipt(layout)
        return state
    if state.workflow_state != "PENDING_REFERENCE_INGESTION":
        raise ValueError("run cannot resume from its current workflow state")

    receipt = load_reference_ingestion_receipt(layout)
    if receipt.request_sha256 != review_request_sha256(request):
        raise ValueError("reference receipt is bound to a different request")
    receipt_hash = reference_ingestion_receipt_sha256(receipt)
    _append_state(
        layout,
        next_state="CLASSIFYING_INPUTS",
        payload_sha256=receipt_hash,
        recorded_at=recorded_at,
    )
    next_state: WorkflowState = (
        "PENDING_DRAWING_INGESTION"
        if _has_drawing(request)
        else "READY_TO_EVALUATE"
    )
    return _append_state(
        layout,
        next_state=next_state,
        payload_sha256=receipt_hash,
        recorded_at=recorded_at,
    )


__all__ = [
    "ReviewRunLayout",
    "ingest_pending_references",
    "open_review_run",
    "prepare_review_run",
    "resume_review_run",
]
