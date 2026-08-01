"""Workflow-state and hold-reason contracts for resumable review runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from ansim_review.contracts.review import FinalizerStatus
from ansim_review.contracts.validation import (
    expect_bool,
    expect_int,
    expect_literal,
    expect_mapping,
    expect_string,
    expect_string_tuple,
    reject_unknown,
)

WorkflowState = Literal[
    "RECEIVED",
    "CLASSIFYING_INPUTS",
    "ROLE_CONFIRMATION_REQUIRED",
    "PENDING_REFERENCE_INGESTION",
    "PENDING_DRAWING_INGESTION",
    "INPUT_CONFIRMATION_REQUIRED",
    "READY_TO_EVALUATE",
    "RETRIEVING_EVIDENCE",
    "RUNNING_MATH",
    "RUNNING_RULES",
    "WAITING_TRACK_A",
    "WAITING_TRACK_B",
    "FINALIZING",
    "READY_FOR_REVIEW",
    "BLOCKED",
    "FAILED",
]
ReasonCode = Literal[
    "SOURCE_CONFLICT",
    "SOURCE_HASH_MISMATCH",
    "MISSING_REQUIRED_INPUT",
    "UNAPPROVED_RULE",
    "MISSING_FORMULA",
    "STALE_SNAPSHOT",
    "MATH_ENGINE_ERROR",
    "CITATION_AUDIT_FAILED",
    "TRACK_B_REJECTED",
    "ROLE_CONFIRMATION_REQUIRED",
    "DRAWING_QUALITY_REJECTED",
    "DRAWING_CONFIRMATION_REQUIRED",
]

_WORKFLOW_STATES: tuple[WorkflowState, ...] = (
    "RECEIVED",
    "CLASSIFYING_INPUTS",
    "ROLE_CONFIRMATION_REQUIRED",
    "PENDING_REFERENCE_INGESTION",
    "PENDING_DRAWING_INGESTION",
    "INPUT_CONFIRMATION_REQUIRED",
    "READY_TO_EVALUATE",
    "RETRIEVING_EVIDENCE",
    "RUNNING_MATH",
    "RUNNING_RULES",
    "WAITING_TRACK_A",
    "WAITING_TRACK_B",
    "FINALIZING",
    "READY_FOR_REVIEW",
    "BLOCKED",
    "FAILED",
)
_REASON_CODES: tuple[ReasonCode, ...] = (
    "SOURCE_CONFLICT",
    "SOURCE_HASH_MISMATCH",
    "MISSING_REQUIRED_INPUT",
    "UNAPPROVED_RULE",
    "MISSING_FORMULA",
    "STALE_SNAPSHOT",
    "MATH_ENGINE_ERROR",
    "CITATION_AUDIT_FAILED",
    "TRACK_B_REJECTED",
    "ROLE_CONFIRMATION_REQUIRED",
    "DRAWING_QUALITY_REJECTED",
    "DRAWING_CONFIRMATION_REQUIRED",
)
_FINALIZER_STATUSES: tuple[FinalizerStatus, ...] = (
    "READY_FOR_HUMAN_REVIEW",
    "ABSTAIN",
)


@dataclass(frozen=True, slots=True)
class WorkflowStateRecord:
    """One canonical workflow projection separate from machine review output."""

    format: Literal["ansim/workflow-state"]
    version: Literal[1]
    run_id: str
    workflow_state: WorkflowState
    finalizer_status: FinalizerStatus | None
    reason_codes: tuple[ReasonCode, ...]
    resumable: bool


def _validate_relationships(
    workflow_state: WorkflowState,
    finalizer_status: FinalizerStatus | None,
    reason_codes: tuple[ReasonCode, ...],
    resumable: bool,
) -> None:
    if workflow_state == "READY_FOR_REVIEW":
        if finalizer_status is None:
            raise ValueError("finalizer_status is required for READY_FOR_REVIEW")
    elif finalizer_status is not None:
        raise ValueError("finalizer_status is only allowed for READY_FOR_REVIEW")

    if workflow_state == "BLOCKED":
        if not reason_codes:
            raise ValueError("BLOCKED workflow requires reason_codes")
        if not resumable:
            raise ValueError("BLOCKED workflow must be resumable")
        return

    if workflow_state == "FAILED":
        if not reason_codes:
            raise ValueError("FAILED workflow requires reason_codes")
        if resumable:
            raise ValueError("FAILED workflow cannot be resumable")
        return

    if reason_codes:
        raise ValueError("reason_codes are only allowed for BLOCKED or FAILED workflows")
    if resumable:
        raise ValueError("only BLOCKED workflow may be resumable")


def decode_workflow_state_record(value: object) -> WorkflowStateRecord:
    """Decode and cross-validate one workflow state document."""
    payload = expect_mapping(value, "workflow_state")
    allowed = {
        "format",
        "version",
        "run_id",
        "workflow_state",
        "finalizer_status",
        "reason_codes",
        "resumable",
    }
    reject_unknown(payload, allowed, "workflow_state")
    format_value = expect_literal(
        payload.get("format"), "format", ("ansim/workflow-state",)
    )
    version = expect_int(payload.get("version"), "version")
    if version != 1:
        raise ValueError(f"unsupported version: {version}")
    workflow_state = expect_literal(
        payload.get("workflow_state"), "workflow_state", _WORKFLOW_STATES
    )
    finalizer_value = payload.get("finalizer_status")
    finalizer_status = (
        None
        if finalizer_value is None
        else expect_literal(finalizer_value, "finalizer_status", _FINALIZER_STATUSES)
    )
    reason_codes = tuple(
        expect_literal(code, "reason_code", _REASON_CODES)
        for code in expect_string_tuple(payload.get("reason_codes", []), "reason_codes")
    )
    resumable = expect_bool(payload.get("resumable"), "resumable")
    _validate_relationships(workflow_state, finalizer_status, reason_codes, resumable)
    return WorkflowStateRecord(
        format=cast(Literal["ansim/workflow-state"], format_value),
        version=1,
        run_id=expect_string(payload.get("run_id"), "run_id"),
        workflow_state=workflow_state,
        finalizer_status=finalizer_status,
        reason_codes=reason_codes,
        resumable=resumable,
    )


def workflow_state_document(record: WorkflowStateRecord) -> dict[str, object]:
    """Return the explicit canonical JSON document for *record*."""
    return {
        "format": record.format,
        "version": record.version,
        "run_id": record.run_id,
        "workflow_state": record.workflow_state,
        "finalizer_status": record.finalizer_status,
        "reason_codes": list(record.reason_codes),
        "resumable": record.resumable,
    }
