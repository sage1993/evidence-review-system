"""Resumable review workflow contracts and orchestration helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evidence_review.workflow.events import (
    WorkflowEvent,
    append_workflow_event,
    decode_workflow_event,
    load_workflow_events,
    make_workflow_event,
    project_workflow_state,
    workflow_event_bytes,
    workflow_event_document,
)
from evidence_review.workflow.request import (
    RequestAttachment,
    ReviewRequest,
    confirmed_attachment_documents,
    confirmed_attachments,
    decode_review_request,
    requires_role_confirmation,
    review_request_bytes,
    review_request_document,
    review_request_sha256,
)
from evidence_review.workflow.state_machine import validate_transition

if TYPE_CHECKING:
    from evidence_review.workflow.versioning import (
        compute_versioned_run_id,
        prepare_versioned_review_run,
    )


def __getattr__(name: str) -> object:
    """Lazily expose versioning helpers without importing the orchestrator on package load."""
    if name == "compute_versioned_run_id":
        from evidence_review.workflow.versioning import compute_versioned_run_id

        return compute_versioned_run_id
    if name == "prepare_versioned_review_run":
        from evidence_review.workflow.versioning import prepare_versioned_review_run

        return prepare_versioned_review_run
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "RequestAttachment",
    "ReviewRequest",
    "WorkflowEvent",
    "append_workflow_event",
    "confirmed_attachment_documents",
    "confirmed_attachments",
    "decode_review_request",
    "decode_workflow_event",
    "load_workflow_events",
    "make_workflow_event",
    "project_workflow_state",
    "requires_role_confirmation",
    "review_request_bytes",
    "review_request_document",
    "review_request_sha256",
    "compute_versioned_run_id",
    "prepare_versioned_review_run",
    "validate_transition",
    "workflow_event_bytes",
    "workflow_event_document",
]
