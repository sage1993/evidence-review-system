"""Agent-mediated next-action contracts for API-free Track A and Track B work."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from ansim_review.contracts.validation import (
    expect_bool,
    expect_int,
    expect_literal,
    expect_mapping,
    expect_sequence,
    expect_string,
    reject_unknown,
)
from ansim_review.contracts.workflow import WorkflowState

NextActionType = Literal["PRODUCE_TRACK_A", "PRODUCE_TRACK_B"]
WaitingWorkflowState = Literal["WAITING_TRACK_A", "WAITING_TRACK_B"]
_FORMATS: tuple[Literal["ansim/next-action"], ...] = ("ansim/next-action",)
_NEXT_ACTIONS: tuple[NextActionType, ...] = ("PRODUCE_TRACK_A", "PRODUCE_TRACK_B")
_WAITING_STATES: tuple[WaitingWorkflowState, ...] = (
    "WAITING_TRACK_A",
    "WAITING_TRACK_B",
)


@dataclass(frozen=True, slots=True)
class NextAction:
    """One deterministic handoff that an external Codex agent must perform."""

    format: Literal["ansim/next-action"]
    version: Literal[1]
    run_id: str
    workflow_state: WaitingWorkflowState
    action: NextActionType
    input_bundle: str
    instructions: str
    expected_output: str
    resume_command: tuple[str, ...]
    track_a_validated: bool


def _safe_relative_path(value: object, field: str) -> str:
    path = expect_string(value, field)
    parsed = PurePosixPath(path)
    first = parsed.parts[0] if parsed.parts else ""
    if (
        parsed.is_absolute()
        or not parsed.parts
        or ".." in parsed.parts
        or ":" in first
        or "\\" in path
    ):
        raise ValueError(f"{field} must be a safe relative path")
    return path


def _resume_command(value: object) -> tuple[str, ...]:
    items = expect_sequence(value, "resume_command")
    command = tuple(
        expect_string(item, f"resume_command[{index}]")
        for index, item in enumerate(items)
    )
    if not command:
        raise ValueError("resume_command must not be empty")
    if command[0].lower() not in {"python", "python3", "py"}:
        raise ValueError("resume_command must begin with python")
    return command


def decode_next_action(value: object) -> NextAction:
    """Decode and cross-check an API-free agent handoff document."""
    payload = expect_mapping(value, "next_action")
    allowed = {
        "format",
        "version",
        "run_id",
        "workflow_state",
        "action",
        "input_bundle",
        "instructions",
        "expected_output",
        "resume_command",
        "track_a_validated",
    }
    reject_unknown(payload, allowed, "next_action")
    format_value = expect_literal(payload.get("format"), "format", _FORMATS)
    version = expect_int(payload.get("version"), "version")
    if version != 1:
        raise ValueError(f"unsupported version: {version}")
    workflow_state = expect_literal(
        payload.get("workflow_state"), "workflow_state", _WAITING_STATES
    )
    action = expect_literal(payload.get("action"), "action", _NEXT_ACTIONS)
    track_a_validated = expect_bool(
        payload.get("track_a_validated"), "track_a_validated"
    )
    expected_state: WaitingWorkflowState = (
        "WAITING_TRACK_A" if action == "PRODUCE_TRACK_A" else "WAITING_TRACK_B"
    )
    if workflow_state != expected_state:
        raise ValueError("action does not match workflow_state")
    if action == "PRODUCE_TRACK_B" and not track_a_validated:
        raise ValueError("Track B requires validated Track A output")
    if action == "PRODUCE_TRACK_A" and track_a_validated:
        raise ValueError("Track A action cannot claim validated Track A output")
    return NextAction(
        format=format_value,
        version=1,
        run_id=expect_string(payload.get("run_id"), "run_id"),
        workflow_state=workflow_state,
        action=action,
        input_bundle=_safe_relative_path(payload.get("input_bundle"), "input_bundle"),
        instructions=_safe_relative_path(payload.get("instructions"), "instructions"),
        expected_output=_safe_relative_path(
            payload.get("expected_output"), "expected_output"
        ),
        resume_command=_resume_command(payload.get("resume_command")),
        track_a_validated=track_a_validated,
    )


def next_action_document(action: NextAction) -> dict[str, object]:
    """Return the explicit canonical next-action document."""
    return {
        "format": action.format,
        "version": action.version,
        "run_id": action.run_id,
        "workflow_state": action.workflow_state,
        "action": action.action,
        "input_bundle": action.input_bundle,
        "instructions": action.instructions,
        "expected_output": action.expected_output,
        "resume_command": list(action.resume_command),
        "track_a_validated": action.track_a_validated,
    }


def waiting_state(action: NextAction) -> WorkflowState:
    """Expose the compatible general workflow-state value for orchestration."""
    return action.workflow_state
