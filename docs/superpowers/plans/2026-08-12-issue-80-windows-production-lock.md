# Issue #80 Windows Production Journal Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Windows CRT journal lock with a blocking Win32 `LockFileEx`/`UnlockFileEx` backend so normal contention waits, conflicting sequence publication resolves as one success plus one `FileExistsError`, and genuine Windows API failures remain fail-closed.

**Architecture:** Keep journal semantics and the persistent sibling `.events.lock` path in `events.py`, while isolating the Windows native primitive in `src/ansim_review/workflow/windows_lock.py`. The Windows helper converts the CRT descriptor to a native handle, locks byte range `[0, 1)` with blocking exclusive `LockFileEx`, and releases the same range with `UnlockFileEx`; the POSIX `flock(LOCK_EX)` path is unchanged. Tests cover the primitive, GIL-safe same-process contention, Issue #80 conflicting sequence publication, spawned-process contention, and genuine Win32 failures.

**Tech Stack:** Python 3.11/3.13, standard-library `ctypes`, `ctypes.wintypes`, `msvcrt.get_osfhandle`, Kernel32 `LockFileEx`/`UnlockFileEx`, `threading`, `multiprocessing`, pytest, Ruff, mypy, compileall.

## Global Constraints

- Execute on branch `agent/issue-80-event-journal-concurrency`; never implement on `main`.
- At execution start load `superpowers:using-git-worktrees`, create or verify an isolated worktree, fetch `origin/main`, and reconcile branch drift before editing production code.
- Approved design spec: `docs/superpowers/specs/2026-08-12-issue-80-windows-production-lock-design.md`, latest approved design commit `c282a6afc24bec54dd1a639b59ee0f5a361feea6`.
- Preserve the diagnostic classification `PRODUCTION_EXCEPTION`: Windows Python 3.11 iteration 23, `max_active_sections=1`, same `.events.lock`, winner `EVT-0001`, loser `EVT-OTHER`, `PermissionError(13)` from `_lock_with_msvcrt`, diagnostic SHA-256 `B6FE5D487AFCDB58563F5908A5D249B7CC27CFB2E12447114806B43A99D4422E`.
- Normal Windows contention must block until release. It must not be implemented with polling, `PermissionError` retry, sleeps, xfail, skip masking, or timeout-based correctness.
- Acquire uses `LockFileEx` with `LOCKFILE_EXCLUSIVE_LOCK` only. `LOCKFILE_FAIL_IMMEDIATELY` is absent; `dwReserved=0`; offset `0`; low length `1`; high length `0`.
- Release uses `UnlockFileEx` on the same handle, offset, and one-byte range.
- Use `ctypes.WinDLL(..., use_last_error=True)`, never `ctypes.PyDLL`, so a waiter blocked in native code does not retain the GIL.
- Preserve genuine Win32 failures as `OSError`/`WinError` with their Windows error code. Never suppress broad `OSError` or infer contention from an exception class.
- Keep `.events.lock` persistent. Do not delete and recreate it for each critical section.
- Remove the Windows-only sentinel-byte write used by the old CRT path. Lock-file bytes carry no semantic state.
- Do not change journal format, canonical event bytes, append ordering, sequence validation, `O_CREAT | O_EXCL` publication, or POSIX `fcntl.flock` behavior.
- Add no third-party dependency.
- Windows Python 3.11 verification is mandatory. Run Python 3.13 verification when installed; otherwise record `UNAVAILABLE`.
- One failure in a stress loop invalidates the loop and returns execution to `superpowers:systematic-debugging`.
- GitHub Actions status is literal. No usable runner means `ACTIONS_UNAVAILABLE`, never PASS.

---

### Task 1: Implement and unit-test the Win32 primitive

**Files:**
- Create: `src/ansim_review/workflow/windows_lock.py`
- Create: `tests/unit/workflow/test_windows_lock.py`

**Interfaces:**
- Produces: `acquire_exclusive_file_lock(stream: BinaryIO) -> None`
- Produces: `release_file_lock(stream: BinaryIO) -> None`
- Private test seams: `_lock_file_ex`, `_unlock_file_ex`
- Consumes: `stream.fileno()`, `msvcrt.get_osfhandle()`, `ctypes.get_last_error()`, `ctypes.WinError()`

- [ ] **Step 1: Pre-flight branch and worktree**

```powershell
git status --short --branch
git rev-parse HEAD
git fetch origin main
git rev-list --left-right --count HEAD...origin/main
git log --oneline --decorate -8
```

If the branch is behind `origin/main`, rebase the clean Issue #80 branch before code edits:

```powershell
git rebase origin/main
git status --short --branch
git rev-list --left-right --count HEAD...origin/main
```

Required result: clean worktree, approved Issue #80 spec/plan retained, zero commits behind `origin/main`. If a source or test conflict appears, inspect the upstream change before resolving it; do not choose a side blindly.

- [ ] **Step 2: Write the primitive tests first**

Create `tests/unit/workflow/test_windows_lock.py`. Skip the whole module before importing the Windows helper when `os.name != "nt"`:

```python
from __future__ import annotations

import ctypes
import os
from pathlib import Path

import pytest

if os.name != "nt":
    pytest.skip("Windows file-lock backend", allow_module_level=True)

from ansim_review.workflow import windows_lock


def test_acquire_uses_blocking_exclusive_one_byte_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int, int, int]] = []

    def fake_lock(
        handle: object,
        flags: int,
        reserved: int,
        low: int,
        high: int,
        overlapped: object,
    ) -> int:
        del handle, overlapped
        calls.append((flags, reserved, low, high))
        return 1

    monkeypatch.setattr(windows_lock, "_lock_file_ex", fake_lock)
    with (tmp_path / "lock").open("w+b") as stream:
        windows_lock.acquire_exclusive_file_lock(stream)

    assert calls == [(windows_lock.LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0)]


def test_release_uses_same_one_byte_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int, int]] = []

    def fake_unlock(
        handle: object,
        reserved: int,
        low: int,
        high: int,
        overlapped: object,
    ) -> int:
        del handle, overlapped
        calls.append((reserved, low, high))
        return 1

    monkeypatch.setattr(windows_lock, "_unlock_file_ex", fake_unlock)
    with (tmp_path / "lock").open("w+b") as stream:
        windows_lock.release_file_lock(stream)

    assert calls == [(0, 1, 0)]


def test_acquire_preserves_win32_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_lock(*args: object) -> int:
        del args
        ctypes.set_last_error(5)
        return 0

    monkeypatch.setattr(windows_lock, "_lock_file_ex", fail_lock)
    with (tmp_path / "lock").open("w+b") as stream:
        with pytest.raises(OSError) as exc_info:
            windows_lock.acquire_exclusive_file_lock(stream)

    assert getattr(exc_info.value, "winerror", None) == 5


def test_release_preserves_win32_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_unlock(*args: object) -> int:
        del args
        ctypes.set_last_error(6)
        return 0

    monkeypatch.setattr(windows_lock, "_unlock_file_ex", fail_unlock)
    with (tmp_path / "lock").open("w+b") as stream:
        with pytest.raises(OSError) as exc_info:
            windows_lock.release_file_lock(stream)

    assert getattr(exc_info.value, "winerror", None) == 6
```

- [ ] **Step 3: Run the new unit test and record RED**

```powershell
py -3.11 -m pytest -q tests/unit/workflow/test_windows_lock.py
```

Required RED: import/collection failure because `ansim_review.workflow.windows_lock` does not exist yet, or focused failures proving the required interface is absent. Save the exact command and output in the Task 1 SDD report.

- [ ] **Step 4: Implement the minimal Windows helper module**

Create `src/ansim_review/workflow/windows_lock.py` with the exact public API above. Define the Win32 layout explicitly:

```python
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import BinaryIO, Protocol, cast

if os.name == "nt":
    import msvcrt


LOCKFILE_EXCLUSIVE_LOCK = 0x00000002


class _MsvcrtApi(Protocol):
    def get_osfhandle(self, file_descriptor: int) -> int:
        ...


class _OverlappedOffset(ctypes.Structure):
    _fields_ = [
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
    ]


class _OverlappedUnion(ctypes.Union):
    _anonymous_ = ("offset",)
    _fields_ = [
        ("offset", _OverlappedOffset),
        ("Pointer", wintypes.LPVOID),
    ]


class _Overlapped(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("union", _OverlappedUnion),
        ("hEvent", wintypes.HANDLE),
    ]
```

On Windows, bind `kernel32` exactly once with `ctypes.WinDLL("kernel32", use_last_error=True)`. Bind these signatures with explicit `argtypes` and `restype`:

```text
LockFileEx(HANDLE, DWORD, DWORD, DWORD, DWORD, POINTER(_Overlapped)) -> BOOL
UnlockFileEx(HANDLE, DWORD, DWORD, DWORD, POINTER(_Overlapped)) -> BOOL
```

The public functions are:

```python
def acquire_exclusive_file_lock(stream: BinaryIO) -> None:
    api = cast(_MsvcrtApi, msvcrt)
    handle = wintypes.HANDLE(api.get_osfhandle(stream.fileno()))
    overlapped = _Overlapped()
    ctypes.set_last_error(0)
    result = _lock_file_ex(
        handle,
        LOCKFILE_EXCLUSIVE_LOCK,
        0,
        1,
        0,
        ctypes.byref(overlapped),
    )
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())


def release_file_lock(stream: BinaryIO) -> None:
    api = cast(_MsvcrtApi, msvcrt)
    handle = wintypes.HANDLE(api.get_osfhandle(stream.fileno()))
    overlapped = _Overlapped()
    ctypes.set_last_error(0)
    result = _unlock_file_ex(
        handle,
        0,
        1,
        0,
        ctypes.byref(overlapped),
    )
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
```

Do not define or pass `LOCKFILE_FAIL_IMMEDIATELY`. Do not add polling or application-level retry.

- [ ] **Step 5: Verify Task 1 GREEN**

```powershell
py -3.11 -m pytest -q tests/unit/workflow/test_windows_lock.py
py -3.11 -m ruff check src/ansim_review/workflow/windows_lock.py tests/unit/workflow/test_windows_lock.py
py -3.11 -m mypy src/ansim_review/workflow/windows_lock.py
py -3.11 -m compileall -q src/ansim_review/workflow/windows_lock.py tests/unit/workflow/test_windows_lock.py
```

All four commands must PASS. Cross-platform typing adjustments, if needed, must remain inside the new Windows helper's import/type boundary; they must not reintroduce CRT locking into `events.py`.

- [ ] **Step 6: Commit Task 1**

```powershell
git add src/ansim_review/workflow/windows_lock.py tests/unit/workflow/test_windows_lock.py
git commit -m "fix: add blocking Win32 journal lock primitive"
```

---

### Task 2: Integrate the primitive and make the thread contract deterministic

**Files:**
- Modify: `src/ansim_review/workflow/events.py` — Windows import block, `_lock_with_msvcrt`, `_journal_lock`
- Modify: `tests/integration/workflow/test_event_journal.py` — Windows routing, GIL/blocking, failure propagation, Issue #80 regression

**Interfaces:**
- Consumes: `acquire_exclusive_file_lock(BinaryIO) -> None`, `release_file_lock(BinaryIO) -> None`
- Preserves: `_journal_lock(events_dir: Path) -> Iterator[None]`
- Preserves: `append_workflow_event(events_dir: Path, event: WorkflowEvent) -> Path`
- Required conflict result: one success, one `FileExistsError`, zero normal-contention `PermissionError`, one canonical event matching the winner.

- [ ] **Step 1: Add deterministic RED routing coverage**

Add a Windows-only test that injects the Task 1 helper names and proves `_journal_lock()` must call them:

```python
def test_windows_journal_lock_routes_through_win32_backend(
    tmp_path: Path,
    monkeypatch,
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
```

Run:

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py::test_windows_journal_lock_routes_through_win32_backend
```

Required RED: the current CRT branch ignores the injected Win32 helpers.

- [ ] **Step 2: Replace only the Windows lock backend in `events.py`**

Use the Task 1 helpers only on Windows:

```python
if os.name == "nt":
    from ansim_review.workflow.windows_lock import (
        acquire_exclusive_file_lock,
        release_file_lock,
    )
else:
    import fcntl
```

Remove `_MsvcrtApi` and `_lock_with_msvcrt()` when no references remain. Keep `_FcntlApi` and `_lock_with_fcntl()` unchanged.

The lock lifetime becomes:

```python
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
```

Delete only the obsolete Windows sentinel block that seeks to EOF, writes `b"\0"` for an empty lock file, flushes it, and seeks back to zero. Preserve lock-path construction, link/reparse checks, `os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)`, and all append logic.

Run the routing test again; it must PASS.

- [ ] **Step 3: Add a real GIL-safe same-process contention regression**

Use the actual native `LockFileEx` call. Patch the private native callable only to observe when the waiter reaches the real blocking call; the wrapper must immediately delegate to the original `_lock_file_ex`.

Test choreography:

1. Owner thread enters the real `_journal_lock()` and signals `owner_acquired`.
2. Waiter thread attempts the same `_journal_lock()`.
3. The tracing wrapper signals `waiter_native_call_started` for the waiter immediately before calling the original WinDLL function.
4. Owner waits for that signal while still holding the lock, then records `owner_progress_after_waiter_started` and exits its critical section.
5. Waiter subsequently enters and records `waiter_entered`.
6. Join both threads with bounded deadlock guards.

Assert the recorded order contains `owner_acquired`, `waiter_native_call_started`, `owner_progress_after_waiter_started`, `owner_release`, then `waiter_entered`; both threads are dead; no exception was captured. This proves the owner Python thread can continue after the waiter reaches the blocking native call. Do not use `sleep()`.

- [ ] **Step 4: Replace the old `os.open` call-count barrier in the Issue #80 regression**

Remove the global `events.os.open` monkeypatch and `open_calls <= 2` synchronization. Rendezvous at the actual journal-lock boundary while retaining the real production lock:

```python
original_journal_lock = events._journal_lock
rendezvous = threading.Barrier(2)

@contextmanager
def synchronized_journal_lock(events_dir: Path):
    rendezvous.wait(timeout=5)
    with original_journal_lock(events_dir):
        yield

monkeypatch.setattr(events, "_journal_lock", synchronized_journal_lock)
```

Capture `(event, exception)` pairs under a `threading.Lock`; join both workers with a bounded deadlock guard; assert neither remains alive; restore the real `_journal_lock` before loading the journal.

Required assertions:

```python
assert len(outcomes) == 2
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
```

The test must not assume which event wins.

- [ ] **Step 5: Add genuine acquire/release failure regressions at the journal boundary**

Acquire failure case:
- monkeypatch `events.acquire_exclusive_file_lock` to raise `ctypes.WinError(5)`;
- call `append_workflow_event()`;
- assert the OS error propagates with `winerror == 5`;
- assert no event JSON file was created.

Release failure with a body exception:
- monkeypatch acquire to succeed and release to raise `ctypes.WinError(6)`;
- enter `_journal_lock()` and raise `ValueError("body failure")` inside it;
- assert the propagated exception has `winerror == 6`;
- assert its `__context__` is the original `ValueError`.

This fixes the exception-preservation policy required by the design: unlock failure is never hidden; when the body is already unwinding, Python context chaining retains the body exception.

- [ ] **Step 6: Run focused Task 2 tests and module regression**

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py::test_windows_journal_lock_routes_through_win32_backend
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py::test_windows_journal_lock_allows_owner_to_progress_while_waiter_blocks
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py::test_windows_journal_lock_acquire_failure_does_not_publish_event
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py::test_windows_journal_lock_release_failure_preserves_body_context
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py
py -3.11 -m ruff check src/ansim_review/workflow/events.py tests/integration/workflow/test_event_journal.py
py -3.11 -m mypy src/ansim_review/workflow/events.py src/ansim_review/workflow/windows_lock.py
```

All commands must PASS.

- [ ] **Step 7: Commit Task 2**

```powershell
git add src/ansim_review/workflow/events.py tests/integration/workflow/test_event_journal.py
git commit -m "fix: use blocking Win32 lock for workflow journal"
```

---

### Task 3: Add Windows spawned-process contention coverage

**Files:**
- Modify: `tests/integration/workflow/test_event_journal.py`

**Interfaces:**
- Consumes the real Task 2 journal lock.
- Produces a module-scope spawn-safe worker and a Windows process regression.
- Process outcomes are exactly `SUCCESS`, `FILE_EXISTS`, or `ERROR` with a diagnostic detail string.

- [ ] **Step 1: Add typed spawn-safe synchronization interfaces**

At module scope:

```python
class _BarrierLike(Protocol):
    def wait(self, timeout: float | None = None) -> int:
        ...


class _QueueLike(Protocol):
    def put(self, value: tuple[str, str | None]) -> None:
        ...
```

Add required `multiprocessing` and `Protocol` imports without altering production code.

- [ ] **Step 2: Add the module-scope spawned worker**

```python
def _append_event_in_spawned_process(
    root: str,
    event,
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

    setattr(events, "_journal_lock", synchronized_journal_lock)
    try:
        events.append_workflow_event(Path(root), event)
    except FileExistsError:
        result_queue.put(("FILE_EXISTS", None))
    except BaseException as exc:
        result_queue.put(("ERROR", f"{type(exc).__name__}: {exc}"))
    else:
        result_queue.put(("SUCCESS", None))
```

Use the repository's concrete `WorkflowEvent` type annotation for `event` if it is already imported by the test module; otherwise import that public/dataclass type from the same production module used by the existing test helpers. Do not leave the worker parameter untyped in the committed code.

- [ ] **Step 3: Add the Windows `spawn` regression**

Use:

```python
ctx = multiprocessing.get_context("spawn")
barrier = ctx.Barrier(2)
result_queue = ctx.Queue()
```

Start two `ctx.Process` workers with one shared journal root and the conflicting sequence-1 events. Join each with a 20-second deadlock guard, assert both are no longer alive and both exit codes are zero, then read exactly two result tuples.

Required outcome:

```python
assert sorted(status for status, _ in results) == ["FILE_EXISTS", "SUCCESS"]
assert all(detail is None for _, detail in results)
```

Reload in the parent and assert exactly one canonical event file remains, the event is one of the contenders, and its file bytes equal `workflow_event_bytes(persisted[0])`.

- [ ] **Step 4: Run a 20-iteration process pre-commit gate**

```powershell
$test = "tests/integration/workflow/test_event_journal.py::test_windows_processes_cannot_publish_two_events_for_one_sequence"
1..20 | ForEach-Object {
    py -3.11 -m pytest -q $test
    if ($LASTEXITCODE -ne 0) {
        throw "Cross-process pre-commit iteration $_ failed"
    }
}
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py
```

Required: 20/20 PASS plus full event-journal module PASS. Any `PermissionError`, unrelated `OSError`, abnormal child exit, deadlock, or duplicate event returns the task to systematic debugging.

- [ ] **Step 5: Commit Task 3**

```powershell
git add tests/integration/workflow/test_event_journal.py
git commit -m "test: cover Windows process journal contention"
```

---

### Task 4: Run the Windows acceptance stress matrix and repository gates

**Files:**
- No planned tracked changes.
- `build/` outputs are local evidence unless an existing repository policy explicitly requires a tracked acceptance artifact.

**Interfaces:**
- Consumes exact Task 1-3 candidate HEAD.
- Produces exact environment, stress, pytest, static, and documentation-integrity evidence for Issue #80.

- [ ] **Step 1: Freeze candidate HEAD and environment**

```powershell
git status --short --branch
git rev-parse HEAD
py -3.11 --version
py -3.13 --version
[System.Environment]::OSVersion.VersionString
```

Worktree must be clean. Record the exact full HEAD and exact interpreter versions. If `py -3.13 --version` fails because Python 3.13 is not installed, record `Python 3.13: UNAVAILABLE` and omit only the 3.13 commands.

- [ ] **Step 2: Run Python 3.11 thread stress — 200 consecutive passes**

```powershell
$threadTest = "tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence"
1..200 | ForEach-Object {
    py -3.11 -m pytest -q $threadTest
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11 thread iteration $_ failed"
    }
}
```

Required: 200/200 PASS.

- [ ] **Step 3: Run Python 3.11 process stress — 100 consecutive passes**

```powershell
$processTest = "tests/integration/workflow/test_event_journal.py::test_windows_processes_cannot_publish_two_events_for_one_sequence"
1..100 | ForEach-Object {
    py -3.11 -m pytest -q $processTest
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11 process iteration $_ failed"
    }
}
```

Required: 100/100 PASS.

- [ ] **Step 4: Run the Python 3.13 stress matrix when available**

```powershell
1..200 | ForEach-Object {
    py -3.13 -m pytest -q $threadTest
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.13 thread iteration $_ failed"
    }
}
1..100 | ForEach-Object {
    py -3.13 -m pytest -q $processTest
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.13 process iteration $_ failed"
    }
}
```

Required when installed: 200/200 thread PASS and 100/100 process PASS.

- [ ] **Step 5: Run focused and workflow regressions**

```powershell
py -3.11 -m pytest -q tests/unit/workflow/test_windows_lock.py
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py
py -3.11 -m pytest -q tests/integration/workflow
```

Repeat those three commands with `py -3.13` when Python 3.13 is installed. Record exact passed/skipped/failed counts.

- [ ] **Step 6: Run full pytest on every available interpreter**

```powershell
py -3.11 -m pytest -q
```

When available:

```powershell
py -3.13 -m pytest -q
```

Any failure blocks acceptance until root-caused.

- [ ] **Step 7: Run static and bytecode gates**

```powershell
py -3.11 -m ruff check src tests
py -3.11 -m mypy src
py -3.11 -m compileall -q src scripts web_runtime tests
git diff --check
git status --short
```

Required: every command PASS and clean worktree.

- [ ] **Step 8: Run documentation integrity**

```powershell
$sha = git rev-parse --short HEAD
$output = "build/documentation-integrity-issue80-$sha.json"
Remove-Item -LiteralPath $output -ErrorAction SilentlyContinue
py -3.11 -m evidence_review documentation validate `
    --repository-root . `
    --config documentation-integrity.json `
    --output $output
```

Required: exit 0 and report status PASS. Record document/error/warning counts exactly.

- [ ] **Step 9: Reconfirm exact candidate state**

```powershell
git rev-parse HEAD
git status --short
git diff --check
```

The HEAD must match Step 1 and the worktree must remain clean. If any tracked evidence change is committed afterward, the acceptance gates required by repository policy must be rerun at the new HEAD before making final PASS claims.

---

### Task 5: Record Issue #80 evidence and open the focused PR

**Files:**
- No planned source/test changes.
- GitHub Issue #80 comment.
- PR from `agent/issue-80-event-journal-concurrency` to `main` after Task 4 passes.

**Interfaces:**
- Consumes exact diagnostic constants from the approved design and exact observed values from Task 4.
- Produces an auditable Issue #80 resolution record and focused review request.

- [ ] **Step 1: Audit branch scope**

```powershell
git fetch origin main
git status --short
git log --oneline --decorate -8
git diff --check
git diff --name-only origin/main...HEAD
```

Expected implementation files are limited to:

```text
src/ansim_review/workflow/windows_lock.py
src/ansim_review/workflow/events.py
tests/unit/workflow/test_windows_lock.py
tests/integration/workflow/test_event_journal.py
```

The approved Issue #80 spec and this plan are also valid branch documentation changes. No unrelated parser, retrieval, browser, database, rule-engine, or persistence refactor is allowed.

- [ ] **Step 2: Build the Issue #80 comment from exact recorded evidence**

Write the comment only after Task 4 has completed. Copy the exact observed values from the Task 4 transcript; do not estimate or reuse counts from an earlier HEAD. The comment must contain all of these fields:

1. `PRODUCTION_EXCEPTION` pre-fix classification.
2. Windows Python 3.11 reproduction at iteration 23.
3. `max_active_sections=1`.
4. Same `.events.lock` path for the first two intercepted opens.
5. Winner `EVT-0001`; loser `EVT-OTHER`; loser `PermissionError(13, "Permission denied")` inside `_lock_with_msvcrt`.
6. Diagnostic SHA-256 `B6FE5D487AFCDB58563F5908A5D249B7CC27CFB2E12447114806B43A99D4422E`.
7. Root cause: CRT locking could maintain mutual exclusion while violating the journal's required blocking-acquisition contract.
8. Fix: blocking exclusive `LockFileEx`/`UnlockFileEx`, persistent sibling lock file, no sentinel mutation, genuine OS errors preserved.
9. Exact final full commit SHA from Task 4.
10. Python 3.11 thread stress result `200/200 PASS` and process stress `100/100 PASS`.
11. Python 3.13 thread/process results, or the literal status `UNAVAILABLE` if that interpreter was not installed.
12. Exact focused test, event-journal module, workflow integration, and full pytest counts.
13. Ruff, mypy, compileall, diff-check, and documentation-integrity results including document/error/warning counts.
14. Literal GitHub Actions status; when no usable runner executed, write `ACTIONS_UNAVAILABLE`.

Do not post the comment if any required Task 4 gate failed.

- [ ] **Step 3: Open the focused PR with a static body**

Use this PR body:

```markdown
Fixes #80

## Root cause
Windows journal contention used CRT `msvcrt.locking(..., LK_LOCK, 1)`. The Issue #80 trace proved that mutual exclusion could remain intact while a normal contender failed in the production acquisition path with `PermissionError(13)` instead of waiting and reaching journal-level conflict detection.

## Fix
- replace the Windows CRT journal-lock backend with blocking exclusive `LockFileEx` / `UnlockFileEx`
- keep the persistent sibling `.events.lock` architecture
- keep the POSIX `flock(LOCK_EX)` path unchanged
- remove the obsolete Windows sentinel-byte mutation
- preserve genuine Win32 failures as OS errors
- replace the low-level `os.open` race test with synchronization at the actual journal-lock boundary
- add same-process GIL/blocking, Win32 error, and spawned-process regressions

## Verification
Issue #80 contains the exact Windows environment, diagnostic lineage, thread/process stress counts, full regression counts, static checks, documentation-integrity result, and GitHub Actions status for the final candidate HEAD.
```

Open as Draft if repository policy still requires a human review step. Do not close Issue #80 merely because the PR exists; closure follows successful review/merge under repository policy.

- [ ] **Step 4: Final branch-state check**

```powershell
git status --short
git rev-parse HEAD
git diff --check
```

Required: clean worktree and exact HEAD matching the Issue #80 evidence record.

---

## Final Acceptance Checklist

- [ ] The pre-fix failure remains classified `PRODUCTION_EXCEPTION`, not rewritten as a test-only flake.
- [ ] Windows journal locking uses `LockFileEx`/`UnlockFileEx`; `msvcrt.LK_LOCK` is absent from the production journal synchronization path.
- [ ] Acquire is blocking exclusive and does not use `LOCKFILE_FAIL_IMMEDIATELY`.
- [ ] Blocking uses `ctypes.WinDLL`, not `PyDLL`, and the same-process regression proves the owner can execute and release while a waiter is in the native acquisition call.
- [ ] `.events.lock` remains persistent and no sentinel byte is written solely for locking.
- [ ] Genuine Win32 acquire/release failures preserve Windows error codes and are not retried or suppressed.
- [ ] Unlock failure during body unwinding preserves the original body exception through `__context__`.
- [ ] Thread conflict requires exactly one success, one `FileExistsError`, zero normal-contention `PermissionError`, and one canonical persisted event matching the winner.
- [ ] Spawned-process conflict satisfies the same one-success/one-`FileExistsError` contract.
- [ ] Python 3.11 stress is 200/200 thread PASS and 100/100 process PASS.
- [ ] Python 3.13 stress is 200/200 thread PASS and 100/100 process PASS when available; otherwise it is explicitly `UNAVAILABLE`.
- [ ] Full focused/workflow/repository pytest, Ruff, mypy, compileall, diff check, and documentation-integrity results are recorded at the exact final candidate HEAD.
- [ ] GitHub Actions status is reported literally with no fabricated PASS.
- [ ] Final diff contains no unrelated production refactor.
- [ ] Issue #80 contains diagnostic lineage, exact final SHA, stress counts, and final verification evidence before closure.
