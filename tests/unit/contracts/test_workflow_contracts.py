from __future__ import annotations

import importlib
from types import ModuleType

import pytest


def _workflow() -> ModuleType:
    try:
        return importlib.import_module("ansim_review.contracts.workflow")
    except ModuleNotFoundError:
        pytest.fail("workflow contract module is missing")


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "format": "ansim/workflow-state",
        "version": 1,
        "run_id": "RUN-1",
        "workflow_state": "RECEIVED",
        "finalizer_status": None,
        "reason_codes": [],
        "resumable": False,
    }
    payload.update(overrides)
    return payload


def test_workflow_requires_explicit_nullable_and_collection_fields() -> None:
    workflow = _workflow()
    for field in ("finalizer_status", "reason_codes", "resumable"):
        payload = _payload()
        del payload[field]
        with pytest.raises(ValueError, match=f"missing required fields: {field}"):
            workflow.decode_workflow_state_record(payload)


def test_reason_code_cannot_be_used_as_workflow_state() -> None:
    workflow = _workflow()
    with pytest.raises(ValueError, match="unsupported workflow_state"):
        workflow.decode_workflow_state_record(
            _payload(workflow_state="SOURCE_HASH_MISMATCH")
        )


def test_review_completed_is_not_a_machine_workflow_state() -> None:
    workflow = _workflow()
    with pytest.raises(ValueError, match="unsupported workflow_state"):
        workflow.decode_workflow_state_record(_payload(workflow_state="REVIEW_COMPLETED"))


def test_ready_for_review_requires_finalizer_status() -> None:
    workflow = _workflow()
    with pytest.raises(ValueError, match="finalizer_status is required"):
        workflow.decode_workflow_state_record(_payload(workflow_state="READY_FOR_REVIEW"))


def test_failed_state_cannot_be_resumable() -> None:
    workflow = _workflow()
    with pytest.raises(ValueError, match="FAILED workflow cannot be resumable"):
        workflow.decode_workflow_state_record(
            _payload(
                workflow_state="FAILED",
                reason_codes=["SOURCE_HASH_MISMATCH"],
                resumable=True,
            )
        )


def test_blocked_state_requires_reason_and_resumable_true() -> None:
    workflow = _workflow()
    with pytest.raises(ValueError, match="BLOCKED workflow requires reason_codes"):
        workflow.decode_workflow_state_record(
            _payload(workflow_state="BLOCKED", reason_codes=[], resumable=True)
        )
    with pytest.raises(ValueError, match="BLOCKED workflow must be resumable"):
        workflow.decode_workflow_state_record(
            _payload(
                workflow_state="BLOCKED",
                reason_codes=["MISSING_REQUIRED_INPUT"],
                resumable=False,
            )
        )


def test_workflow_state_round_trips_canonical_document() -> None:
    workflow = _workflow()
    record = workflow.decode_workflow_state_record(
        _payload(
            workflow_state="BLOCKED",
            reason_codes=["MISSING_REQUIRED_INPUT"],
            resumable=True,
        )
    )
    expected = _payload(
        workflow_state="BLOCKED",
        reason_codes=["MISSING_REQUIRED_INPUT"],
        resumable=True,
    )
    expected["format"] = "evidence-review/workflow-state"
    assert workflow.workflow_state_document(record) == expected
