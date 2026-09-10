from __future__ import annotations

import importlib
from types import ModuleType

import pytest


def _attachments() -> ModuleType:
    return importlib.import_module("evidence_review.contracts.attachments")


def _next_actions() -> ModuleType:
    return importlib.import_module("evidence_review.contracts.next_action")


def _attachment(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "attachment_id": "ATT-1",
        "original_name": "site-plan.pdf",
        "stored_path": "inputs/original/ATT-1.pdf",
        "sha256": "a" * 64,
        "byte_size": 1234,
        "mime": "application/pdf",
        "role": "CASE_DRAWING",
    }
    payload.update(overrides)
    return payload


def _next_action(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "format": "ansim/next-action",
        "version": 1,
        "run_id": "RUN-1",
        "workflow_state": "WAITING_TRACK_A",
        "action": "PRODUCE_TRACK_A",
        "input_bundle": "track-a-bundle.json",
        "instructions": "TRACK_A_INSTRUCTIONS.md",
        "expected_output": "track-a-output.json",
        "resume_command": [
            "python",
            "-m",
            "evidence_review",
            "resume",
            "--run-id",
            "RUN-1",
        ],
        "track_a_validated": False,
    }
    payload.update(overrides)
    return payload


def test_attachment_rejects_external_absolute_path() -> None:
    attachments = _attachments()
    with pytest.raises(ValueError, match="safe relative path"):
        attachments.decode_immutable_attachment(
            _attachment(stored_path="C:/incoming/site.pdf")
        )


def test_attachment_rejects_parent_path_escape() -> None:
    attachments = _attachments()
    with pytest.raises(ValueError, match="safe relative path"):
        attachments.decode_immutable_attachment(
            _attachment(stored_path="inputs/original/../site.pdf")
        )


def test_attachment_requires_original_storage_root() -> None:
    attachments = _attachments()
    with pytest.raises(ValueError, match="inputs/original"):
        attachments.decode_immutable_attachment(
            _attachment(stored_path="tmp/ATT-1.pdf")
        )


def test_visual_attachment_requires_case_local_identity() -> None:
    attachments = _attachments()
    with pytest.raises(ValueError, match="case_id"):
        attachments.decode_immutable_attachment(_attachment())


def test_attachment_round_trips() -> None:
    attachments = _attachments()
    payload = _attachment(role="REFERENCE_DOCUMENT")
    attachment = attachments.decode_immutable_attachment(payload)
    assert attachments.immutable_attachment_document(attachment) == payload


def test_track_b_action_requires_validated_track_a() -> None:
    next_actions = _next_actions()
    with pytest.raises(ValueError, match="validated Track A"):
        next_actions.decode_next_action(
            _next_action(
                workflow_state="WAITING_TRACK_B",
                action="PRODUCE_TRACK_B",
                input_bundle="track-b-bundle.json",
                instructions="TRACK_B_INSTRUCTIONS.md",
                expected_output="track-b-output.json",
                track_a_validated=False,
            )
        )


def test_next_action_rejects_path_traversal() -> None:
    next_actions = _next_actions()
    with pytest.raises(ValueError, match="safe relative path"):
        next_actions.decode_next_action(_next_action(input_bundle="../track-a.json"))


def test_next_action_requires_python_resume_command() -> None:
    next_actions = _next_actions()
    with pytest.raises(ValueError, match="must begin with python"):
        next_actions.decode_next_action(
            _next_action(resume_command=["bash", "resume.sh"])
        )


def test_next_action_round_trips_canonical_document() -> None:
    next_actions = _next_actions()
    action = next_actions.decode_next_action(_next_action())
    expected = _next_action(format="evidence-review/next-action")
    assert next_actions.next_action_document(action) == expected
