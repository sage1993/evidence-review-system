"""Append-only workflow event journal and derived state projection."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Literal, Protocol, cast

if os.name == "nt":
    from evidence_review.workflow.windows_lock import (
        acquire_exclusive_file_lock,
        release_file_lock,
    )
else:
    import fcntl


from evidence_review import canonical_json
from evidence_review.contracts.formats import (
    WORKFLOW_EVENT_FORMAT,
    WORKFLOW_STATE_FORMAT,
)
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.review import FinalizerStatus
from evidence_review.contracts.validation import (
    expect_bool,
    expect_int,
    expect_literal,
    expect_mapping,
    expect_sequence,
    expect_sha256,
    expect_string,
    reject_unknown,
    require_fields,
)
from evidence_review.contracts.workflow import (
    ReasonCode,
    WorkflowState,
    WorkflowStateRecord,
    decode_workflow_state_record,
)
from evidence_review.workflow.state_machine import (
    EventKind,
    decode_event_kind,
    decode_workflow_state,
    validate_transition,
)


class _FcntlApi(Protocol):
    LOCK_EX: int
    LOCK_UN: int

    def flock(self, file_descriptor: int, operation: int) -> None:
        ...


def _lock_with_fcntl(stream: BinaryIO, *, unlock: bool) -> None:
    api = cast(_FcntlApi, fcntl)
    operation = api.LOCK_UN if unlock else api.LOCK_EX
    api.flock(stream.fileno(), operation)


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
    "PARTIALLY_RESOLVED",
    "ABSTAIN",
)


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    """One append-only state transition with a deterministic payload binding."""

    format: Literal["evidence-review/workflow-event"]
    version: Literal[1]
    run_id: str
    sequence: int
    event_id: str
    kind: EventKind
    previous_state: WorkflowState | None
    next_state: WorkflowState
    finalizer_status: FinalizerStatus | None
    reason_codes: tuple[ReasonCode, ...]
    resumable: bool
    payload_sha256: str
    recorded_at: str


def _parse_recorded_at(value: object) -> str:
    text = expect_string(value, "recorded_at")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("recorded_at must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("recorded_at must include a timezone offset")
    return parsed.isoformat()


def _projection_document(
    *,
    run_id: str,
    state: WorkflowState,
    finalizer_status: FinalizerStatus | None,
    reason_codes: tuple[ReasonCode, ...],
    resumable: bool,
) -> dict[str, object]:
    return {
        "format": WORKFLOW_STATE_FORMAT,
        "version": 1,
        "run_id": run_id,
        "workflow_state": state,
        "finalizer_status": finalizer_status,
        "reason_codes": list(reason_codes),
        "resumable": resumable,
    }


def decode_workflow_event(value: object) -> WorkflowEvent:
    """Decode one strict event and validate its state relationships."""
    payload = expect_mapping(value, "workflow_event")
    required = {
        "format",
        "version",
        "run_id",
        "sequence",
        "event_id",
        "kind",
        "previous_state",
        "next_state",
        "finalizer_status",
        "reason_codes",
        "resumable",
        "payload_sha256",
        "recorded_at",
    }
    require_fields(payload, required, "workflow_event")
    reject_unknown(payload, required, "workflow_event")
    expect_literal(payload.get("format"), "format", (WORKFLOW_EVENT_FORMAT,))
    version = expect_int(payload.get("version"), "version")
    if version != 1:
        raise ValueError(f"unsupported version: {version}")
    sequence = expect_int(payload.get("sequence"), "sequence")
    if sequence < 1:
        raise ValueError("sequence must be positive")

    previous_value = payload.get("previous_state")
    previous_state = (
        None
        if previous_value is None
        else decode_workflow_state(previous_value, "previous_state")
    )
    next_state = decode_workflow_state(payload.get("next_state"), "next_state")
    kind = decode_event_kind(payload.get("kind"))
    validate_transition(previous_state, next_state, kind)

    finalizer_value = payload.get("finalizer_status")
    finalizer_status = (
        None
        if finalizer_value is None
        else expect_literal(
            finalizer_value,
            "finalizer_status",
            _FINALIZER_STATUSES,
        )
    )
    reason_codes = tuple(
        expect_literal(item, "reason_code", _REASON_CODES)
        for item in expect_sequence(payload.get("reason_codes"), "reason_codes")
    )
    if len(reason_codes) != len(set(reason_codes)):
        raise ValueError("reason_codes must be unique")
    canonical_reasons = tuple(sorted(reason_codes))
    resumable = expect_bool(payload.get("resumable"), "resumable")
    run_id = validate_identifier(payload.get("run_id"), "run_id")
    projection = decode_workflow_state_record(
        _projection_document(
            run_id=run_id,
            state=next_state,
            finalizer_status=finalizer_status,
            reason_codes=canonical_reasons,
            resumable=resumable,
        )
    )
    return WorkflowEvent(
        format=WORKFLOW_EVENT_FORMAT,
        version=1,
        run_id=projection.run_id,
        sequence=sequence,
        event_id=validate_identifier(payload.get("event_id"), "event_id"),
        kind=kind,
        previous_state=previous_state,
        next_state=projection.workflow_state,
        finalizer_status=projection.finalizer_status,
        reason_codes=projection.reason_codes,
        resumable=projection.resumable,
        payload_sha256=expect_sha256(
            payload.get("payload_sha256"), "payload_sha256"
        ),
        recorded_at=_parse_recorded_at(payload.get("recorded_at")),
    )


def make_workflow_event(
    *,
    run_id: str,
    sequence: int,
    event_id: str,
    kind: EventKind,
    previous_state: WorkflowState | None,
    next_state: WorkflowState,
    reason_codes: tuple[ReasonCode, ...],
    resumable: bool,
    finalizer_status: FinalizerStatus | None,
    payload_sha256: str,
    recorded_at: str,
) -> WorkflowEvent:
    """Construct an event through the strict disk decoder."""
    return decode_workflow_event(
        {
            "format": WORKFLOW_EVENT_FORMAT,
            "version": 1,
            "run_id": run_id,
            "sequence": sequence,
            "event_id": event_id,
            "kind": kind,
            "previous_state": previous_state,
            "next_state": next_state,
            "finalizer_status": finalizer_status,
            "reason_codes": list(reason_codes),
            "resumable": resumable,
            "payload_sha256": payload_sha256,
            "recorded_at": recorded_at,
        }
    )


def workflow_event_document(event: WorkflowEvent) -> dict[str, object]:
    """Return the explicit canonical event document."""
    return {
        "format": WORKFLOW_EVENT_FORMAT,
        "version": event.version,
        "run_id": event.run_id,
        "sequence": event.sequence,
        "event_id": event.event_id,
        "kind": event.kind,
        "previous_state": event.previous_state,
        "next_state": event.next_state,
        "finalizer_status": event.finalizer_status,
        "reason_codes": list(event.reason_codes),
        "resumable": event.resumable,
        "payload_sha256": event.payload_sha256,
        "recorded_at": event.recorded_at,
    }


def workflow_event_bytes(event: WorkflowEvent) -> bytes:
    """Return canonical UTF-8 bytes with one trailing newline."""
    return canonical_json.dump_bytes(workflow_event_document(event)) + b"\n"


def workflow_event_filename(event: WorkflowEvent) -> str:
    """Return the deterministic direct-child journal filename."""
    return f"{event.sequence:04d}-{event.event_id}.json"


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _reject_link_ancestors(path: Path) -> None:
    absolute = path.absolute()
    for candidate in (absolute, *absolute.parents):
        if not candidate.exists():
            continue
        if candidate.is_symlink() or _is_reparse_point(candidate):
            raise ValueError(
                "workflow journal path must not contain links or reparse points"
            )


@contextmanager
def _journal_lock(events_dir: Path) -> Iterator[None]:
    """Serialize journal readers and writers across threads and processes."""
    lock_path = events_dir.parent / f".{events_dir.name}.lock"
    _reject_link_ancestors(lock_path.parent)
    _reject_link_ancestors(lock_path)
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT,
        0o600,
    )
    with os.fdopen(descriptor, "r+b") as stream:
        acquired = False
        try:
            if os.name == "nt":
                acquire_exclusive_file_lock(stream)
            else:
                _lock_with_fcntl(stream, unlock=False)
            acquired = True
            yield
        finally:
            if acquired:
                if os.name == "nt":
                    release_file_lock(stream)
                else:
                    _lock_with_fcntl(stream, unlock=True)


def _load_json_document(raw: bytes) -> object:
    def reject_constant(value: str) -> object:
        raise ValueError(f"invalid JSON constant: {value}")

    def reject_duplicate_keys(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return cast(
            object,
            json.loads(
                raw.decode("utf-8"),
                parse_constant=reject_constant,
                object_pairs_hook=reject_duplicate_keys,
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("workflow event must be valid UTF-8 JSON") from exc


def _load_workflow_events_unlocked(events_dir: Path) -> tuple[WorkflowEvent, ...]:
    """Load and revalidate the complete canonical event journal."""
    if not events_dir.exists():
        return ()
    _reject_link_ancestors(events_dir)
    if not events_dir.is_dir():
        raise ValueError("workflow events path must be a directory")

    loaded: list[WorkflowEvent] = []
    for path in sorted(events_dir.iterdir(), key=lambda item: item.name):
        if path.is_dir() or path.suffix != ".json":
            raise ValueError(
                "workflow event directory contains an unexpected entry"
            )
        _reject_link_ancestors(path)
        raw = path.read_bytes()
        event = decode_workflow_event(_load_json_document(raw))
        if path.name != workflow_event_filename(event):
            raise ValueError(
                "workflow event filename does not match event identity"
            )
        if raw != workflow_event_bytes(event):
            raise ValueError("workflow event bytes are not canonical")
        loaded.append(event)

    loaded.sort(key=lambda event: event.sequence)
    previous: WorkflowState | None = None
    run_id: str | None = None
    for expected_sequence, event in enumerate(loaded, start=1):
        if event.sequence != expected_sequence:
            raise ValueError("workflow journal contains a sequence gap")
        if run_id is None:
            run_id = event.run_id
        elif event.run_id != run_id:
            raise ValueError("workflow journal contains multiple run IDs")
        if event.previous_state != previous:
            raise ValueError(
                "workflow event previous_state does not match journal"
            )
        validate_transition(event.previous_state, event.next_state, event.kind)
        previous = event.next_state
    return tuple(loaded)


def load_workflow_events(events_dir: Path) -> tuple[WorkflowEvent, ...]:
    """Load and revalidate the complete canonical event journal."""
    if not events_dir.exists():
        return ()
    _reject_link_ancestors(events_dir)
    with _journal_lock(events_dir):
        return _load_workflow_events_unlocked(events_dir)


def append_workflow_event(events_dir: Path, event: WorkflowEvent) -> Path:
    """Atomically append an event, allowing only byte-identical retries."""
    _reject_link_ancestors(events_dir)
    events_dir.mkdir(parents=True, exist_ok=True)
    _reject_link_ancestors(events_dir)
    with _journal_lock(events_dir):
        existing = _load_workflow_events_unlocked(events_dir)
        target = events_dir / workflow_event_filename(event)
        encoded = workflow_event_bytes(event)

        if event.sequence <= len(existing):
            recorded = existing[event.sequence - 1]
            recorded_path = events_dir / workflow_event_filename(recorded)
            if recorded_path == target and workflow_event_bytes(recorded) == encoded:
                return target
            raise FileExistsError(
                "workflow sequence already contains different bytes"
            )

        expected_sequence = len(existing) + 1
        if event.sequence != expected_sequence:
            raise ValueError(f"next sequence must be {expected_sequence}")
        expected_previous = existing[-1].next_state if existing else None
        if event.previous_state != expected_previous:
            raise ValueError("event previous_state does not match journal state")
        validate_transition(event.previous_state, event.next_state, event.kind)

        try:
            descriptor = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            _reject_link_ancestors(target)
            if target.read_bytes() == encoded:
                return target
            raise FileExistsError(
                "workflow event path contains different bytes"
            ) from None
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        return target


def project_workflow_state(events_dir: Path) -> WorkflowStateRecord:
    """Rebuild the current state projection from authoritative events."""
    events = load_workflow_events(events_dir)
    if not events:
        raise ValueError("workflow journal is empty")
    last = events[-1]
    return decode_workflow_state_record(
        _projection_document(
            run_id=last.run_id,
            state=last.next_state,
            finalizer_status=last.finalizer_status,
            reason_codes=last.reason_codes,
            resumable=last.resumable,
        )
    )
