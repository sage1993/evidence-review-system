from __future__ import annotations

import importlib
from types import ModuleType

import pytest


def _state_machine() -> ModuleType:
    try:
        return importlib.import_module("ansim_review.workflow.state_machine")
    except ModuleNotFoundError:
        pytest.fail("workflow state-machine module is missing")


def test_foundation_transitions_are_explicitly_allowed() -> None:
    machine = _state_machine()
    allowed = (
        (None, "RECEIVED", "TRANSITION"),
        ("RECEIVED", "CLASSIFYING_INPUTS", "TRANSITION"),
        ("CLASSIFYING_INPUTS", "ROLE_CONFIRMATION_REQUIRED", "TRANSITION"),
        ("CLASSIFYING_INPUTS", "PENDING_REFERENCE_INGESTION", "TRANSITION"),
        ("PENDING_REFERENCE_INGESTION", "CLASSIFYING_INPUTS", "TRANSITION"),
        ("CLASSIFYING_INPUTS", "READY_TO_EVALUATE", "TRANSITION"),
        ("READY_TO_EVALUATE", "RETRIEVING_EVIDENCE", "TRANSITION"),
    )
    for previous, next_state, kind in allowed:
        machine.validate_transition(previous, next_state, kind)


def test_reason_codes_and_finalizer_values_are_not_workflow_states() -> None:
    machine = _state_machine()
    for invalid in (
        "SOURCE_HASH_MISMATCH",
        "MISSING_REQUIRED_INPUT",
        "READY_FOR_HUMAN_REVIEW",
        "ABSTAIN",
        "REVIEW_COMPLETED",
    ):
        with pytest.raises(ValueError, match="workflow state"):
            machine.validate_transition("RECEIVED", invalid, "TRANSITION")


def test_representative_illegal_transitions_are_rejected() -> None:
    machine = _state_machine()
    with pytest.raises(ValueError, match="transition is not allowed"):
        machine.validate_transition("RECEIVED", "RUNNING_RULES", "TRANSITION")
    with pytest.raises(ValueError, match="terminal"):
        machine.validate_transition(
            "READY_FOR_REVIEW", "CLASSIFYING_INPUTS", "TRANSITION"
        )
    with pytest.raises(ValueError, match="terminal"):
        machine.validate_transition("FAILED", "CLASSIFYING_INPUTS", "TRANSITION")


def test_blocked_workflow_requires_explicit_resume_event() -> None:
    machine = _state_machine()
    with pytest.raises(ValueError, match="RESUME"):
        machine.validate_transition("BLOCKED", "CLASSIFYING_INPUTS", "TRANSITION")
    machine.validate_transition("BLOCKED", "CLASSIFYING_INPUTS", "RESUME")


def test_resume_event_is_only_valid_after_blocked_state() -> None:
    machine = _state_machine()
    with pytest.raises(ValueError, match="only valid after BLOCKED"):
        machine.validate_transition("RECEIVED", "CLASSIFYING_INPUTS", "RESUME")
