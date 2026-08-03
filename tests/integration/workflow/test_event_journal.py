from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest


def _events() -> ModuleType:
    try:
        return importlib.import_module("ansim_review.workflow.events")
    except ModuleNotFoundError:
        pytest.fail("workflow event module is missing")


def _event(
    events: ModuleType,
    *,
    sequence: int,
    previous_state: str | None,
    next_state: str,
    kind: str = "TRANSITION",
    reason_codes: tuple[str, ...] = (),
    resumable: bool = False,
    finalizer_status: str | None = None,
):
    return events.make_workflow_event(
        run_id="RUN-001",
        sequence=sequence,
        event_id=f"EVT-{sequence:04d}",
        kind=kind,
        previous_state=previous_state,
        next_state=next_state,
        reason_codes=reason_codes,
        resumable=resumable,
        finalizer_status=finalizer_status,
        payload_sha256="a" * 64,
        recorded_at="2026-08-04T00:00:00+09:00",
    )


def test_event_journal_is_append_only_and_idempotent(tmp_path: Path) -> None:
    events = _events()
    root = tmp_path / "events"
    first = _event(events, sequence=1, previous_state=None, next_state="RECEIVED")

    path = events.append_workflow_event(root, first)
    original = path.read_bytes()
    assert events.append_workflow_event(root, first) == path
    assert path.read_bytes() == original

    conflicting = replace(first, payload_sha256="b" * 64)
    with pytest.raises(FileExistsError, match="different bytes"):
        events.append_workflow_event(root, conflicting)
    assert path.read_bytes() == original


def test_event_journal_rejects_sequence_gaps_and_previous_state_mismatch(
    tmp_path: Path,
) -> None:
    events = _events()
    root = tmp_path / "events"
    events.append_workflow_event(
        root,
        _event(events, sequence=1, previous_state=None, next_state="RECEIVED"),
    )
    with pytest.raises(ValueError, match="next sequence"):
        events.append_workflow_event(
            root,
            _event(
                events,
                sequence=3,
                previous_state="RECEIVED",
                next_state="CLASSIFYING_INPUTS",
            ),
        )
    with pytest.raises(ValueError, match="previous_state"):
        events.append_workflow_event(
            root,
            _event(
                events,
                sequence=2,
                previous_state="CLASSIFYING_INPUTS",
                next_state="PENDING_REFERENCE_INGESTION",
            ),
        )


def test_event_journal_detects_tampering(tmp_path: Path) -> None:
    events = _events()
    root = tmp_path / "events"
    path = events.append_workflow_event(
        root,
        _event(events, sequence=1, previous_state=None, next_state="RECEIVED"),
    )
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        events.load_workflow_events(root)


def test_projection_is_rebuilt_from_journal(tmp_path: Path) -> None:
    events = _events()
    root = tmp_path / "events"
    events.append_workflow_event(
        root,
        _event(events, sequence=1, previous_state=None, next_state="RECEIVED"),
    )
    events.append_workflow_event(
        root,
        _event(
            events,
            sequence=2,
            previous_state="RECEIVED",
            next_state="CLASSIFYING_INPUTS",
        ),
    )
    events.append_workflow_event(
        root,
        _event(
            events,
            sequence=3,
            previous_state="CLASSIFYING_INPUTS",
            next_state="BLOCKED",
            reason_codes=("ROLE_CONFIRMATION_REQUIRED",),
            resumable=True,
        ),
    )

    projection = events.project_workflow_state(root)
    assert projection.run_id == "RUN-001"
    assert projection.workflow_state == "BLOCKED"
    assert projection.reason_codes == ("ROLE_CONFIRMATION_REQUIRED",)
    assert projection.resumable is True


def test_event_bytes_are_deterministic(tmp_path: Path) -> None:
    events = _events()
    event = _event(events, sequence=1, previous_state=None, next_state="RECEIVED")
    assert events.workflow_event_bytes(event) == events.workflow_event_bytes(event)
    assert events.workflow_event_bytes(event).endswith(b"\n")
