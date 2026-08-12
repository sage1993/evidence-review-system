# Issue #80 Windows Production Journal Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Windows CRT journal lock with a blocking Win32 `LockFileEx`/`UnlockFileEx` backend so normal contention waits, conflicting sequence publication resolves as one success plus one `FileExistsError`, and genuine Windows API failures remain fail-closed.

**Architecture:** Keep journal semantics and the persistent sibling `.events.lock` path in `events.py`, but isolate the Windows native file-lock primitive in `src/ansim_review/workflow/windows_lock.py`. The Windows helper converts a CRT file descriptor to a native handle, acquires byte range `[0, 1)` with blocking exclusive `LockFileEx`, and releases the same range with `UnlockFileEx`; the POSIX `flock(LOCK_EX)` path is unchanged. Regression coverage proves same-process blocking/GIL behavior, Issue #80 sequence conflict behavior, cross-process serialization, and genuine Win32 error propagation.

**Tech Stack:** Python 3.11/3.13, standard-library `ctypes`, `ctypes.wintypes`, `msvcrt.get_osfhandle`, Win32 Kernel32 `LockFileEx`/`UnlockFileEx`, `threading`, `multiprocessing`, pytest, Ruff, mypy, compileall.

## Global Constraints

- Execute on branch `agent/issue-80-event-journal-concurrency`; do not implement on `main`.
- At execution start, load `superpowers:using-git-worktrees`, create or verify an isolated worktree, fetch `origin/main`, and reconcile any branch drift before editing production code.
- Approved design spec: `docs/superpowers/specs/2026-08-12-issue-80-windows-production-lock-design.md` at or after commit `c282a6afc24bec54dd1a639b59ee0f5a361feea6`.
- Preserve the diagnostic disposition `PRODUCTION_EXCEPTION`: Windows Python 3.11 iteration 23, `max_active_sections=1`, same `.events.lock` path, winner `EVT-0001`, loser `EVT-OTHER`, `PermissionError(13)` from `_lock_with_msvcrt`, diagnostic SHA-256 `B6FE5D487AFCDB58563F5908A5D249B7CC27CFB2E12447114806B43A99D4422E`.
- Normal Windows lock contention must block until the owner releases; it must not be converted into `PermissionError`, polling, retries, sleeps, xfail, skip masking, or timeout-based correctness.
- Windows acquire uses `LockFileEx` with `LOCKFILE_EXCLUSIVE_LOCK` only; `LOCKFILE_FAIL_IMMEDIATELY` is absent; `dwReserved=0`; offset `0`; low length `1`; high length `0`.
- Windows release uses `UnlockFileEx` on the same handle, offset, and one-byte range.
- Use `ctypes.WinDLL(..., use_last_error=True)`, not `ctypes.PyDLL`, so a blocking waiter does not retain the GIL and prevent the owner thread from releasing the lock.
- Preserve genuine Win32 failures as `OSError`/`WinError` with the Windows error code; never suppress broad `OSError` or retry `PermissionError` as contention.
- Keep `.events.lock` persistent; do not delete/recreate it per critical section.
- Remove the Windows-only sentinel-byte write used by the old CRT path; lock-file contents carry no semantic state.
- Do not change journal file format, append ordering, sequence validation, canonical bytes, `O_CREAT | O_EXCL` event publication, or POSIX `fcntl.flock` behavior.
- Add no third-party dependency.
- Python 3.11 Windows verification is mandatory. Python 3.13 is required when installed; if unavailable, record `UNAVAILABLE` rather than PASS.
- One failure in a stress loop invalidates that loop and returns the work to systematic debugging.
- GitHub Actions status is reported literally. No usable runner means `ACTIONS_UNAVAILABLE`, never PASS.

---

### Task 1: Implement and unit-test the Win32 file-lock primitive

**Files:**
- Create: `src/ansim_review/workflow/windows_lock.py`
- Create: `tests/unit/workflow/test_windows_lock.py`

**Interfaces:**
- Produces: `acquire_exclusive_file_lock(stream: BinaryIO) -> None`
- Produces: `release_file_lock(stream: BinaryIO) -> None`
- Private test seams: module-level `_lock_file_ex` and `_unlock_file_ex` bound once to Kernel32 callables.
- Consumes: `stream.fileno()`, `msvcrt.get_osfhandle()`, `ctypes.get_last_error()`, `ctypes.WinError()`.

- [ ] **Step 1: Pre-flight the branch and isolated worktree**

Run in PowerShell:

```powershell
git status --short --branch
git rev-parse HEAD
git fetch origin main
git rev-list --left-right --count HEAD...origin/main
git log --oneline --decorate -8
```

If the right-hand count shows `origin/main` commits missing from the branch, rebase the clean Issue #80 branch before code changes:

```powershell
git rebase origin/main
git status --short --branch
git rev-list --left-right --count HEAD...origin/main
```

Expected before implementation: clean worktree, Issue #80 spec/plan preserved, zero commits behind `origin/main`. If a source/test conflict appears during rebase, stop the rebase resolution long enough to inspect the conflicting upstream change; do not blindly choose either side.

- [ ] **Step 2: Write the Windows-only unit tests first**

Create `tests/unit/workflow/test_windows_lock.py` with Windows-only collection and controlled native-call seams. The tests must cover exact acquire parameters, exact release parameters, acquire error propagation, and release error propagation.

Use this structure:

```python
from __future__ import annotations

import ctypes
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows file-lock backend")

if os.name == "nt":
    from ansim_review.workflow import windows_lock
else:
    windows_lock = None


def _require_windows_lock():
    assert windows_lock is not None
    return windows_lock


def test_acquire_uses_blocking_exclusive_one_byte_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _require_windows_lock()
    calls: list[tuple[int, int, int, int]] = []

    def fake_lock(handle, flags, reserved, low, high, overlapped):
        del handle, overlapped
        calls.append((int(flags), int(reserved), int(low), int(high)))
        return 1

    monkeypatch.setattr(module, "_lock_file_ex", fake_lock)
    path = tmp_path / "lock"
    with path.open("w+b") as stream:
        module.acquire_exclusive_file_lock(stream)

    assert calls == [(module.LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0)]


def test_release_uses_same_one_byte_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _require_windows_lock()
    calls: list[tuple[int, int, int]] = []

    def fake_unlock(handle, reserved, low, high, overlapped):
        del handle, overlapped
        calls.append((int(reserved), int(low), int(high)))
        return 1

    monkeypatch.setattr(module, "_unlock_file_ex", fake_unlock)
    path = tmp_path / "lock"
    with path.open("w+b") as stream:
        module.release_file_lock(stream)

    assert calls == [(0, 1, 0)]


def test_acquire_preserves_win32_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _require_windows_lock()

    def fail_lock(*args):
        del args
        ctypes.set_last_error(5)
        return 0

    monkeypatch.setattr(module, "_lock_file_ex", fail_lock)
    path = tmp_path / "lock"
    with path.open("w+b") as stream:
        with pytest.raises(OSError) as exc_info:
            module.acquire_exclusive_file_lock(stream)

    assert getattr(exc_info.value, "winerror", None) == 5


def test_release_preserves_win32_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _require_windows_lock()

    def fail_unlock(*args):
        del args
        ctypes.set_last_error(6)
        return 0

    monkeypatch.setattr(module, "_unlock_file_ex", fail_unlock)
    path = tmp_path / "lock"
    with path.open("w+b") as stream:
        with pytest.raises(OSError) as exc_info:
            module.release_file_lock(stream)

    assert getattr(exc_info.value, "winerror", None) == 6
```

If strict typing rejects the unannotated fake native callables, give each fake explicit `object` parameters rather than introducing `Any` broadly.

- [ ] **Step 3: Run the focused tests and record RED**

```powershell
py -3.11 -m pytest -q tests/unit/workflow/test_windows_lock.py
```

Expected before production implementation: collection/import failure because `ansim_review.workflow.windows_lock` does not yet exist, or focused test failures showing the required interface is absent. Record the exact RED output in the SDD task report.

- [ ] **Step 4: Implement `windows_lock.py` minimally**

Create a Windows-native helper module with these concrete responsibilities:

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

On Windows, bind Kernel32 once with `ctypes.WinDLL("kernel32", use_last_error=True)`. Define explicit `argtypes`/`restype` for:

```text
LockFileEx(HANDLE, DWORD, DWORD, DWORD, DWORD, POINTER(OVERLAPPED)) -> BOOL
UnlockFileEx(HANDLE, DWORD, DWORD, DWORD, POINTER(OVERLAPPED)) -> BOOL
```

The public functions must:

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

Do not add `LOCKFILE_FAIL_IMMEDIATELY`, polling, retry loops, or an application timeout.

- [ ] **Step 5: Run unit tests and static checks for the new module**

```powershell
py -3.11 -m pytest -q tests/unit/workflow/test_windows_lock.py
py -3.11 -m ruff check src/ansim_review/workflow/windows_lock.py tests/unit/workflow/test_windows_lock.py
py -3.11 -m mypy src/ansim_review/workflow/windows_lock.py
py -3.11 -m compileall -q src/ansim_review/workflow/windows_lock.py tests/unit/workflow/test_windows_lock.py
```

Expected: all commands PASS. If Windows mypy or a later Linux/static run exposes platform-stub issues, solve them with a narrow protocol/conditional-import boundary; do not move the Win32 implementation back into `events.py`.

- [ ] **Step 6: Commit Task 1**

```powershell
git add src/ansim_review/workflow/windows_lock.py tests/unit/workflow/test_windows_lock.py
git commit -m "fix: add blocking Win32 journal lock primitive"
```

---

### Task 2: Integrate the Win32 backend into the journal and replace the flaky thread orchestration

**Files:**
- Modify: `src/ansim_review/workflow/events.py` — platform import block, old `_lock_with_msvcrt`, `_journal_lock`
- Modify: `tests/integration/workflow/test_event_journal.py` — Windows lock contract and Issue #80 conflicting-sequence regression

**Interfaces:**
- Consumes from Task 1: `acquire_exclusive_file_lock(BinaryIO) -> None`, `release_file_lock(BinaryIO) -> None`
- Preserves: `_journal_lock(events_dir: Path) -> Iterator[None]`
- Preserves: `append_workflow_event(events_dir: Path, event: WorkflowEvent) -> Path`
- Produces test contract: one thread success, one `FileExistsError`, no `PermissionError`, exactly one canonical persisted event.

- [ ] **Step 1: Add a deterministic RED integration test for backend routing**

Add a Windows-only test that injects the new helper names into `events` and proves `_journal_lock()` must call them in acquire/body/release order:

```python
def test_windows_journal_lock_routes_through_win32_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    events = _events()
    if events.os.name != "nt":
        pytest.skip("Windows journal lock backend")

    calls: list[str] = []

    def acquire(stream) -> None:
        del stream
        calls.append("acquire")

    def release(stream) -> None:
        del stream
        calls.append("release")

    monkeypatch.setattr(events, "acquire_exclusive_file_lock", acquire, raising=False)
    monkeypatch.setattr(events, "release_file_lock", release, raising=False)

    with events._journal_lock(tmp_path / "events"):
        calls.append("body")

    assert calls == ["acquire", "body", "release"]
```

- [ ] **Step 2: Run the routing test and confirm RED against the CRT path**

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py::test_windows_journal_lock_routes_through_win32_backend
```

Expected before modifying `events.py`: FAIL because the current Windows branch still calls `_lock_with_msvcrt()` and never calls the injected Task 1 helpers.

- [ ] **Step 3: Replace only the Windows lock backend in `events.py`**

Change the platform import boundary to import the Task 1 helpers only on Windows and retain `fcntl` only on non-Windows:

```python
if os.name == "nt":
    from ansim_review.workflow.windows_lock import (
        acquire_exclusive_file_lock,
        release_file_lock,
    )
else:
    import fcntl
```

Remove the `_MsvcrtApi` protocol and `_lock_with_msvcrt()` helper if they are no longer referenced. Preserve the existing `_FcntlApi`/`_lock_with_fcntl()` path.

Replace only the Windows body inside `_journal_lock()` so it becomes:

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

Delete the old Windows-only sentinel logic:

```python
stream.seek(0, os.SEEK_END)
if stream.tell() == 0:
    stream.write(b"\0")
    stream.flush()
stream.seek(0)
```

Do not change lock-path construction, link/reparse checks, `os.open(..., O_RDWR | O_CREAT, 0o600)`, or journal append semantics.

- [ ] **Step 4: Run the routing test GREEN**

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py::test_windows_journal_lock_routes_through_win32_backend
```

Expected: PASS.

- [ ] **Step 5: Add a real same-process blocking/GIL regression**

Add a Windows-only test using the real `_journal_lock()` without mocking the native lock. Use `threading.Event` for choreography: owner acquires; waiter announces it is about to attempt; owner confirms waiter has not entered; owner releases; waiter enters. Use bounded waits only as deadlock guards.

Required assertions:

```text
owner acquired before waiter entered
waiter did not enter while owner held the lock
owner remained able to execute Python and release
waiter entered after release
both threads terminated
no PermissionError
no unexpected exception
```

Use a thread-safe list or guarded tuple list for captured exceptions. No `sleep()` call is permitted.

- [ ] **Step 6: Replace the old Issue #80 `os.open` call-count barrier test**

Remove the global `events.os.open` monkeypatch and its `open_calls <= 2` barrier. Synchronize the two contenders immediately before the real `_journal_lock` boundary instead:

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

Capture `(event, exception)` pairs under a `threading.Lock`, join both workers with a bounded deadlock guard, assert both are dead, then restore the real `_journal_lock` before calling `load_workflow_events()`.

Required assertions after restoration:

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

The test must not assert which event wins.

- [ ] **Step 7: Add failed-acquisition/no-mutation regression**

On Windows, monkeypatch `events.acquire_exclusive_file_lock` to raise a controlled `OSError` before the critical section and call `append_workflow_event()`.

Assert:

```text
same OSError class/error detail propagates
no *.json event file exists
journal reload is empty after restoring the real helper
failure is not translated to FileExistsError
```

This proves genuine OS failures stay fail-closed.

- [ ] **Step 8: Run the focused thread/journal tests**

```powershell
$tests = @(
  "tests/integration/workflow/test_event_journal.py::test_windows_journal_lock_routes_through_win32_backend",
  "tests/integration/workflow/test_event_journal.py::test_windows_journal_lock_blocks_competing_thread_until_release",
  "tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence",
  "tests/integration/workflow/test_event_journal.py::test_windows_journal_lock_acquire_failure_does_not_publish_event"
)
py -3.11 -m pytest -q $tests
```

Expected: all focused tests PASS with the real Win32 backend.

- [ ] **Step 9: Run the complete event-journal module and static checks**

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py
py -3.11 -m ruff check src/ansim_review/workflow/events.py tests/integration/workflow/test_event_journal.py
py -3.11 -m mypy src/ansim_review/workflow/events.py src/ansim_review/workflow/windows_lock.py
py -3.11 -m compileall -q src/ansim_review/workflow/events.py src/ansim_review/workflow/windows_lock.py tests/integration/workflow/test_event_journal.py
```

Expected: PASS.

- [ ] **Step 10: Commit Task 2**

```powershell
git add src/ansim_review/workflow/events.py tests/integration/workflow/test_event_journal.py
git commit -m "fix: use blocking Win32 lock for workflow journal"
```

---

### Task 3: Prove cross-process serialization under Windows spawn semantics

**Files:**
- Modify: `tests/integration/workflow/test_event_journal.py`

**Interfaces:**
- Consumes the real Task 2 `_journal_lock()` and `append_workflow_event()` behavior.
- Produces a module-scope spawn-safe worker returning one of `SUCCESS`, `FILE_EXISTS`, or `ERROR:<type>:<message>` through a multiprocessing queue.

- [ ] **Step 1: Add spawn-safe process test helpers at module scope**

Define small test-only protocols for the synchronization/result objects so strict mypy does not require importing private multiprocessing implementation types:

```python
class _BarrierLike(Protocol):
    def wait(self, timeout: float | None = None) -> int:
        ...


class _QueueLike(Protocol):
    def put(self, value: tuple[str, str | None]) -> None:
        ...
```

Define a module-scope worker. Inside the spawned child, import the production events module, wrap its real `_journal_lock` with a child-local rendezvous, and then call `append_workflow_event()`:

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

    events._journal_lock = synchronized_journal_lock
    try:
        events.append_workflow_event(Path(root), event)
    except FileExistsError:
        result_queue.put(("FILE_EXISTS", None))
    except BaseException as exc:
        result_queue.put(("ERROR", f"{type(exc).__name__}: {exc}"))
    else:
        result_queue.put(("SUCCESS", None))
```

If assigning to the private module attribute is rejected by type checking, use `setattr(events, "_journal_lock", synchronized_journal_lock)` in the child process.

- [ ] **Step 2: Add the Windows spawn regression test**

Use an explicit Windows-compatible context:

```python
ctx = multiprocessing.get_context("spawn")
barrier = ctx.Barrier(2)
result_queue = ctx.Queue()
```

Start two `ctx.Process` instances with the same journal root and conflicting sequence-1 events. Join each with a bounded 20-second deadlock guard, assert neither remains alive, and require zero abnormal exit codes.

Read exactly two result tuples from the queue and assert:

```python
assert sorted(status for status, _ in results) == ["FILE_EXISTS", "SUCCESS"]
assert all(detail is None for _, detail in results)
```

Then reload the journal in the parent and require exactly one canonical event file whose bytes match the persisted event.

- [ ] **Step 3: Run the cross-process test repeatedly before committing**

```powershell
$test = "tests/integration/workflow/test_event_journal.py::test_windows_processes_cannot_publish_two_events_for_one_sequence"
1..20 | ForEach-Object {
    py -3.11 -m pytest -q $test
    if ($LASTEXITCODE -ne 0) {
        throw "Cross-process pre-commit iteration $_ failed"
    }
}
```

Expected: 20/20 PASS. If any iteration reports `PermissionError`, another `OSError`, abnormal child exit, or more than one event, stop and return to `superpowers:systematic-debugging`; do not weaken the assertion.

- [ ] **Step 4: Re-run the full event-journal module**

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```powershell
git add tests/integration/workflow/test_event_journal.py
git commit -m "test: cover Windows process journal contention"
```

---

### Task 4: Execute the Windows acceptance stress matrix and repository regression gates

**Files:**
- No planned source changes.
- Local-only evidence outputs under `build/` are not committed unless an existing repository acceptance policy explicitly requires a tracked artifact.

**Interfaces:**
- Consumes the exact final implementation HEAD from Tasks 1-3.
- Produces exact command/result evidence for Issue #80 and PR review.

- [ ] **Step 1: Freeze and record the candidate HEAD/environment**

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse origin/agent/issue-80-event-journal-concurrency 2>$null
py -3.11 --version
py -3.13 --version
[System.Environment]::OSVersion.VersionString
```

The worktree must be clean before stress verification. If Python 3.13 is not installed, record `Python 3.13: UNAVAILABLE` and skip only the 3.13 commands below.

- [ ] **Step 2: Run the mandatory Python 3.11 thread stress loop**

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

- [ ] **Step 3: Run the mandatory Python 3.11 process stress loop**

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

- [ ] **Step 4: Run the same stress matrix on Python 3.13 when available**

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

Required when installed: 200/200 thread and 100/100 process PASS.

- [ ] **Step 5: Run focused and workflow regressions on every available interpreter**

```powershell
py -3.11 -m pytest -q tests/unit/workflow/test_windows_lock.py
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py
py -3.11 -m pytest -q tests/integration/workflow
```

When Python 3.13 is available, repeat the three commands with `py -3.13`.

- [ ] **Step 6: Run the full repository suite**

```powershell
py -3.11 -m pytest -q
```

When Python 3.13 is available:

```powershell
py -3.13 -m pytest -q
```

Record exact passed/skipped/failed counts and duration. Any failure invalidates final acceptance until root-caused.

- [ ] **Step 7: Run static and bytecode gates at the exact candidate HEAD**

```powershell
py -3.11 -m ruff check src tests
py -3.11 -m mypy src
py -3.11 -m compileall -q src scripts web_runtime tests
git diff --check
git status --short
```

Expected: PASS and clean worktree.

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

Expected: exit code 0 and report status PASS. Record warning count exactly; warnings are not silently converted into errors or hidden.

- [ ] **Step 9: Re-check candidate immutability**

```powershell
git rev-parse HEAD
git status --short
git diff --check
```

The HEAD used for all reported acceptance results must be the same implementation HEAD. If evidence-only documentation is committed after verification, re-run the repository gates required by the repository's acceptance policy at the new HEAD rather than claiming the old HEAD results for the new commit.

---

### Task 5: Record Issue #80 evidence and open a focused PR

**Files:**
- No production/test changes planned.
- GitHub Issue #80 comment.
- New PR from `agent/issue-80-event-journal-concurrency` to `main` only after Task 4 passes.

**Interfaces:**
- Consumes exact diagnostic evidence and exact Task 4 results.
- Produces the final review package without closing Issue #80 prematurely.

- [ ] **Step 1: Audit the final branch diff before publishing evidence**

```powershell
git fetch origin main
git status --short
git log --oneline --decorate -8
git diff --check
git diff --name-only origin/main...HEAD
git diff -- src/ansim_review/workflow/events.py src/ansim_review/workflow/windows_lock.py tests/unit/workflow/test_windows_lock.py tests/integration/workflow/test_event_journal.py
```

Expected implementation scope:

```text
src/ansim_review/workflow/windows_lock.py
src/ansim_review/workflow/events.py
tests/unit/workflow/test_windows_lock.py
tests/integration/workflow/test_event_journal.py
```

The approved spec and implementation plan are also valid branch documentation changes. No unrelated parser, retrieval, browser, database, or rule-engine production changes are allowed.

- [ ] **Step 2: Post the Issue #80 evidence comment**

The comment must state the root cause as a production locking backend defect, not a flaky-test-only defect. Include:

```markdown
## Issue #80 production-lock resolution

### Pre-fix diagnosis
- disposition: `PRODUCTION_EXCEPTION`
- Windows Python 3.11 reproduction: iteration 23
- `max_active_sections=1`
- first two intercepted `os.open` paths: same `.events.lock`
- winner: `EVT-0001`
- loser: `EVT-OTHER`
- loser exception: `PermissionError(13, "Permission denied")`
- exception origin: `_journal_lock` -> `_lock_with_msvcrt`
- diagnostic SHA-256: `B6FE5D487AFCDB58563F5908A5D249B7CC27CFB2E12447114806B43A99D4422E`

### Root cause
The CRT `msvcrt.locking(..., LK_LOCK, 1)` backend could preserve mutual exclusion while surfacing a normal contender as `PermissionError` instead of providing the blocking serialization contract required by the workflow journal. The production Windows backend was replaced with blocking exclusive `LockFileEx`/`UnlockFileEx` over the persistent sibling lock file. Normal contention now waits; genuine Win32 failures remain fail-closed.

### Safety contract
- one conflicting sequence-1 append succeeds
- the other reaches journal validation and raises `FileExistsError`
- no normal-contention `PermissionError`
- exactly one canonical event remains
- same contract verified across threads and Windows spawned processes
- POSIX `flock` path unchanged

### Verification
- exact HEAD: `<paste exact SHA>`
- Windows/Python 3.11 thread stress: `200/200 PASS`
- Windows/Python 3.11 process stress: `100/100 PASS`
- Windows/Python 3.13 thread stress: `<200/200 PASS or UNAVAILABLE>`
- Windows/Python 3.13 process stress: `<100/100 PASS or UNAVAILABLE>`
- Windows lock unit tests: `<exact count>`
- event-journal module: `<exact count>`
- workflow integration: `<exact count>`
- full pytest 3.11: `<exact count>`
- full pytest 3.13: `<exact count or UNAVAILABLE>`
- Ruff: `<PASS/FAIL>`
- mypy: `<PASS/FAIL and source count if reported>`
- compileall: `<PASS/FAIL>`
- documentation integrity: `<PASS/FAIL, errors, warnings>`
- GitHub Actions: `<literal status; use ACTIONS_UNAVAILABLE when no usable runner executed>`
```

Replace every angle-bracket field with the exact observed value before posting; do not post the template with unresolved fields.

- [ ] **Step 3: Open the focused PR**

Use this body after all fields are known:

```markdown
Fixes #80

## Root cause
Windows journal contention used CRT `msvcrt.locking(..., LK_LOCK, 1)`. The Issue #80 trace proved that mutual exclusion could remain intact while a normal contender failed in the production lock acquisition path with `PermissionError(13)` instead of waiting and reaching journal-level conflict detection.

## Fix
- replace the Windows CRT journal-lock backend with blocking exclusive `LockFileEx` / `UnlockFileEx`
- keep the persistent sibling `.events.lock` architecture
- keep the POSIX `flock(LOCK_EX)` path unchanged
- remove the obsolete Windows sentinel-byte mutation
- preserve genuine Win32 failures as OS errors
- replace the low-level `os.open` race test with synchronization at the actual journal-lock boundary
- add same-process blocking/GIL, Win32 error, and spawned-process regressions

## Verification
Issue #80 contains the exact Windows environment, diagnostic lineage, thread/process stress counts, full regression counts, static checks, documentation-integrity result, and GitHub Actions status for the final candidate HEAD.
```

Open as Draft if any external/human acceptance step remains. Do not close Issue #80 merely because the PR exists; closure follows successful review/merge under repository policy.

- [ ] **Step 4: Final branch-state check**

```powershell
git status --short
git rev-parse HEAD
git diff --check
```

Expected: clean worktree and exact HEAD matching the evidence record.

---

## Final Acceptance Checklist

- [ ] The pre-fix Windows failure remains classified as `PRODUCTION_EXCEPTION`, not rewritten as a test-only flake.
- [ ] The Windows production primitive is `LockFileEx`/`UnlockFileEx`; journal locking no longer uses `msvcrt.LK_LOCK`.
- [ ] Acquire is blocking exclusive and does not use `LOCKFILE_FAIL_IMMEDIATELY`.
- [ ] The blocking native call uses `ctypes.WinDLL`, not `PyDLL`, and the same-process regression proves the owner thread can run and release while another thread waits.
- [ ] `.events.lock` remains persistent and no sentinel byte is written solely for locking.
- [ ] Genuine Win32 acquire/release errors preserve their Windows error code and are not retried or suppressed.
- [ ] The Issue #80 conflict regression requires exactly one success, exactly one `FileExistsError`, zero normal-contention `PermissionError`, and exactly one canonical persisted event matching the winner.
- [ ] Windows spawned-process contention satisfies the same one-success/one-`FileExistsError` contract.
- [ ] Python 3.11 thread stress is 200/200 PASS and process stress is 100/100 PASS.
- [ ] Python 3.13 thread/process stress passes at 200/200 and 100/100 when available; otherwise availability is recorded as `UNAVAILABLE`.
- [ ] Full event-journal, workflow, repository pytest, Ruff, mypy, compileall, diff check, and documentation-integrity results are recorded at the exact final candidate HEAD.
- [ ] GitHub Actions status is reported literally with no fabricated PASS.
- [ ] Final diff contains no unrelated production refactor.
- [ ] Issue #80 contains the diagnostic lineage, exact final SHA, stress counts, and final verification evidence before closure.
