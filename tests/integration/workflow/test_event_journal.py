from __future__ import annotations

import ctypes
import importlib
import multiprocessing
import threading
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Protocol

import pytest

from evidence_review.workflow.events import WorkflowEvent


class _BarrierLike(Protocol):
    def wait(self, timeout: float | None = None) -> int:
        ...


class _QueueLike(Protocol):
    def put(self, value: tuple[str, str | None]) -> None:
        ...


def _events() -> ModuleType:
    try:
        return importlib.import_module("evidence_review.workflow.events")
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


def test_windows_journal_lock_routes_through_win32_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _events()
    if events.os.name != "nt":
        pytest.skip("Windows journal lock backend")

    calls: list[str] = []

    def acquire(stream: object) -> None:
        del stream
        calls.append("acquire")

    def release(stream: object) -> None:
        del stream
        calls.append("release")

    monkeypatch.setattr(events, "acquire_exclusive_file_lock", acquire, raising=False)
    monkeypatch.setattr(events, "release_file_lock", release, raising=False)

    with events._journal_lock(tmp_path / "events"):
        calls.append("body")

    assert calls == ["acquire", "body", "release"]


def test_windows_journal_lock_allows_owner_to_progress_while_waiter_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _events()
    if events.os.name != "nt":
        pytest.skip("Windows journal lock backend")

    from evidence_review.workflow import windows_lock

    owner_acquired = threading.Event()
    waiter_native_call_started = threading.Event()
    records: list[str] = []
    records_guard = threading.Lock()
    errors: list[BaseException] = []
    owner_thread_id: int | None = None
    original_lock_file_ex = windows_lock._lock_file_ex

    def record(label: str) -> None:
        with records_guard:
            records.append(label)

    def traced_lock_file_ex(*args: object, **kwargs: object) -> int:
        if threading.get_ident() != owner_thread_id:
            record("waiter_native_call_started")
            waiter_native_call_started.set()
        return original_lock_file_ex(*args, **kwargs)

    monkeypatch.setattr(windows_lock, "_lock_file_ex", traced_lock_file_ex)

    def owner() -> None:
        nonlocal owner_thread_id
        owner_thread_id = threading.get_ident()
        try:
            with events._journal_lock(tmp_path / "events"):
                record("owner_acquired")
                owner_acquired.set()
                if not waiter_native_call_started.wait(timeout=5):
                    raise AssertionError("waiter did not reach LockFileEx")
                record("owner_progress_after_waiter_started")
                record("owner_release")
        except BaseException as exc:
            errors.append(exc)

    def waiter() -> None:
        try:
            if not owner_acquired.wait(timeout=5):
                raise AssertionError("owner did not acquire journal lock")
            with events._journal_lock(tmp_path / "events"):
                record("waiter_entered")
        except BaseException as exc:
            errors.append(exc)

    owner_thread = threading.Thread(target=owner)
    waiter_thread = threading.Thread(target=waiter)
    owner_thread.start()
    waiter_thread.start()
    owner_thread.join(timeout=15)
    waiter_thread.join(timeout=15)

    assert not owner_thread.is_alive()
    assert not waiter_thread.is_alive()
    assert errors == []
    assert records == [
        "owner_acquired",
        "waiter_native_call_started",
        "owner_progress_after_waiter_started",
        "owner_release",
        "waiter_entered",
    ]


def test_windows_journal_lock_acquire_failure_does_not_publish_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _events()
    if events.os.name != "nt":
        pytest.skip("Windows journal lock backend")

    root = tmp_path / "events"
    event = _event(events, sequence=1, previous_state=None, next_state="RECEIVED")

    def fail_acquire(stream: object) -> None:
        del stream
        raise ctypes.WinError(5)

    monkeypatch.setattr(events, "acquire_exclusive_file_lock", fail_acquire)
    with pytest.raises(OSError) as exc_info:
        events.append_workflow_event(root, event)

    assert getattr(exc_info.value, "winerror", None) == 5
    assert list(root.glob("*.json")) == []


def test_windows_journal_lock_release_failure_preserves_body_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _events()
    if events.os.name != "nt":
        pytest.skip("Windows journal lock backend")

    def acquire(stream: object) -> None:
        del stream

    def fail_release(stream: object) -> None:
        del stream
        raise ctypes.WinError(6)

    monkeypatch.setattr(events, "acquire_exclusive_file_lock", acquire)
    monkeypatch.setattr(events, "release_file_lock", fail_release)

    with pytest.raises(OSError) as exc_info:
        with events._journal_lock(tmp_path / "events"):
            raise ValueError("body failure")

    assert getattr(exc_info.value, "winerror", None) == 6
    assert isinstance(exc_info.value.__context__, ValueError)


def test_concurrent_events_cannot_publish_two_events_for_one_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _events()
    root = tmp_path / "events"
    first = _event(
        events,
        sequence=1,
        previous_state=None,
        next_state="RECEIVED",
    )
    second = replace(first, event_id="EVT-OTHER")
    original_journal_lock = events._journal_lock
    rendezvous = threading.Barrier(2)

    @contextmanager
    def synchronized_journal_lock(events_dir: Path):
        rendezvous.wait(timeout=5)
        with original_journal_lock(events_dir):
            yield

    monkeypatch.setattr(events, "_journal_lock", synchronized_journal_lock)
    outcomes: list[tuple[object, BaseException | None]] = []
    outcomes_guard = threading.Lock()

    def append(event: object) -> None:
        try:
            events.append_workflow_event(root, event)
        except BaseException as exc:
            outcome = (event, exc)
        else:
            outcome = (event, None)
        with outcomes_guard:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=append, args=(first,)),
        threading.Thread(target=append, args=(second,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert all(not thread.is_alive() for thread in threads)
    assert len(outcomes) == 2

    monkeypatch.setattr(events, "_journal_lock", original_journal_lock)

    successes = [item for item in outcomes if item[1] is None]
    failures = [item for item in outcomes if item[1] is not None]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0][1], FileExistsError)
    assert not isinstance(failures[0][1], PermissionError)

    persisted = events.load_workflow_events(root)
    assert len(persisted) == 1
    assert persisted[0].sequence == 1
    assert persisted[0] == successes[0][0]
    assert persisted[0] in (first, second)

    json_files = sorted(root.glob("*.json"))
    assert len(json_files) == 1
    assert json_files[0].read_bytes() == events.workflow_event_bytes(persisted[0])



def _append_event_in_spawned_process(
    root: str,
    event: WorkflowEvent,
    barrier: _BarrierLike,
    result_queue: _QueueLike,
) -> None:
    events = _events()
    original_journal_lock = events._journal_lock

    @contextmanager
    def synchronized_journal_lock(events_dir: Path):
        barrier.wait(timeout=10)
        with original_journal_lock(events_dir):
            yield

    events._journal_lock = synchronized_journal_lock
    try:
        events.append_workflow_event(Path(root), event)
    except FileExistsError:
        result_queue.put(("FILE_EXISTS", None))
    except BaseException as exc:
        result_queue.put(("ERROR", f"{type(exc).__name__}: {exc}"))
    else:
        result_queue.put(("SUCCESS", None))

def test_windows_processes_cannot_publish_two_events_for_one_sequence(
    tmp_path: Path,
) -> None:
    events = _events()
    if events.os.name != "nt":
        pytest.skip("Windows process journal lock backend")

    ctx = multiprocessing.get_context("spawn")
    root = tmp_path / "events"
    first = _event(
        events,
        sequence=1,
        previous_state=None,
        next_state="RECEIVED",
    )
    second = replace(first, event_id="EVT-OTHER")
    barrier = ctx.Barrier(2)
    result_queue = ctx.Queue()
    processes = [
        ctx.Process(
            target=_append_event_in_spawned_process,
            args=(str(root), first, barrier, result_queue),
        ),
        ctx.Process(
            target=_append_event_in_spawned_process,
            args=(str(root), second, barrier, result_queue),
        ),
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
    for process in processes:
        if process.is_alive():
            process.terminate()

    assert all(not process.is_alive() for process in processes)
    assert all(process.exitcode == 0 for process in processes)

    results = [result_queue.get(timeout=5) for _ in processes]
    assert sorted(status for status, _ in results) == ["FILE_EXISTS", "SUCCESS"]
    assert all(detail is None for _, detail in results)

    persisted = events.load_workflow_events(root)
    assert len(persisted) == 1
    assert persisted[0] in (first, second)

    json_files = sorted(root.glob("*.json"))
    assert len(json_files) == 1
    assert json_files[0].read_bytes() == events.workflow_event_bytes(persisted[0])
