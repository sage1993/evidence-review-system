"""Explicit deterministic transition rules for review workflow states."""

from __future__ import annotations

from typing import Literal

from ansim_review.contracts.validation import expect_literal
from ansim_review.contracts.workflow import WorkflowState

EventKind = Literal["TRANSITION", "RESUME"]
_EVENT_KINDS: tuple[EventKind, ...] = ("TRANSITION", "RESUME")
_KNOWN_STATES: tuple[WorkflowState, ...] = (
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

_ALLOWED_TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    "RECEIVED": frozenset({"CLASSIFYING_INPUTS", "FAILED"}),
    "CLASSIFYING_INPUTS": frozenset(
        {
            "ROLE_CONFIRMATION_REQUIRED",
            "PENDING_REFERENCE_INGESTION",
            "PENDING_DRAWING_INGESTION",
            "INPUT_CONFIRMATION_REQUIRED",
            "READY_TO_EVALUATE",
            "BLOCKED",
            "FAILED",
        }
    ),
    "ROLE_CONFIRMATION_REQUIRED": frozenset(
        {"CLASSIFYING_INPUTS", "BLOCKED", "FAILED"}
    ),
    "PENDING_REFERENCE_INGESTION": frozenset(
        {
            "CLASSIFYING_INPUTS",
            "PENDING_DRAWING_INGESTION",
            "INPUT_CONFIRMATION_REQUIRED",
            "READY_TO_EVALUATE",
            "BLOCKED",
            "FAILED",
        }
    ),
    "PENDING_DRAWING_INGESTION": frozenset(
        {"INPUT_CONFIRMATION_REQUIRED", "READY_TO_EVALUATE", "BLOCKED", "FAILED"}
    ),
    "INPUT_CONFIRMATION_REQUIRED": frozenset(
        {"READY_TO_EVALUATE", "BLOCKED", "FAILED"}
    ),
    "READY_TO_EVALUATE": frozenset(
        {"RETRIEVING_EVIDENCE", "BLOCKED", "FAILED"}
    ),
    "RETRIEVING_EVIDENCE": frozenset(
        {"RUNNING_MATH", "BLOCKED", "FAILED"}
    ),
    "RUNNING_MATH": frozenset({"RUNNING_RULES", "BLOCKED", "FAILED"}),
    "RUNNING_RULES": frozenset({"WAITING_TRACK_A", "BLOCKED", "FAILED"}),
    "WAITING_TRACK_A": frozenset({"WAITING_TRACK_B", "BLOCKED", "FAILED"}),
    "WAITING_TRACK_B": frozenset({"FINALIZING", "BLOCKED", "FAILED"}),
    "FINALIZING": frozenset({"READY_FOR_REVIEW", "BLOCKED", "FAILED"}),
    "READY_FOR_REVIEW": frozenset(),
    "BLOCKED": frozenset(),
    "FAILED": frozenset(),
}

_RESUME_TARGETS: frozenset[WorkflowState] = frozenset(
    {
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
        "FAILED",
    }
)


def decode_workflow_state(value: object, field: str) -> WorkflowState:
    """Decode one canonical M0 workflow state without defining a parallel enum."""
    try:
        return expect_literal(value, field, _KNOWN_STATES)
    except ValueError as exc:
        raise ValueError(f"{field} must be a canonical workflow state") from exc


def decode_event_kind(value: object) -> EventKind:
    """Decode one transition journal event kind."""
    return expect_literal(value, "kind", _EVENT_KINDS)


def validate_transition(
    previous_state: object | None,
    next_state: object,
    kind: object,
) -> None:
    """Reject illegal or implicit workflow transitions."""
    decoded_next = decode_workflow_state(next_state, "next_state")
    decoded_kind = decode_event_kind(kind)

    if previous_state is None:
        if decoded_kind != "TRANSITION" or decoded_next != "RECEIVED":
            raise ValueError("initial transition must enter RECEIVED")
        return

    decoded_previous = decode_workflow_state(previous_state, "previous_state")
    if decoded_previous in {"READY_FOR_REVIEW", "FAILED"}:
        raise ValueError(f"{decoded_previous} is a terminal workflow state")

    if decoded_previous == "BLOCKED":
        if decoded_kind != "RESUME":
            raise ValueError("BLOCKED workflow requires an explicit RESUME event")
        if decoded_next not in _RESUME_TARGETS:
            raise ValueError("resume transition is not allowed")
        return

    if decoded_kind == "RESUME":
        raise ValueError("RESUME is only valid after BLOCKED")
    if decoded_next not in _ALLOWED_TRANSITIONS[decoded_previous]:
        raise ValueError(
            f"transition is not allowed: {decoded_previous} -> {decoded_next}"
        )
