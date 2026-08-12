# Issue #80 Windows Production Journal Lock Design

## Status

Approved replacement design for the Windows production locking path discovered during Issue #80 diagnosis.

The earlier flaky-test plan stopped correctly after a Windows Python 3.11 diagnostic run classified the failure as `PRODUCTION_EXCEPTION`.

Observed evidence supplied from that diagnostic run:

- failure reproduced on Windows Python 3.11 at iteration 23;
- `max_active_sections=1`;
- the first two intercepted `os.open` paths were the same sibling lock file, `.events.lock`;
- `EVT-0001` completed successfully;
- `EVT-OTHER` failed with `PermissionError(13, "Permission denied")`;
- the exception originated inside `_journal_lock()` while acquiring the Windows lock through `_lock_with_msvcrt()`;
- diagnostic artifact: `build/issue80-diagnostic-py311.txt`;
- diagnostic SHA-256: `B6FE5D487AFCDB58563F5908A5D249B7CC27CFB2E12447114806B43A99D4422E`.

The temporary diagnostics and test edits were reverted after capture. This design starts from the pre-diagnostic production and test code.

## Problem statement

`_journal_lock()` promises to serialize workflow-journal readers and writers across threads and processes. The POSIX path uses blocking `flock(LOCK_EX)`. The Windows path currently uses CRT byte-range locking through `msvcrt.locking(..., LK_LOCK, 1)`.

The Issue #80 trace proves that the Windows path can preserve mutual exclusion while still violating the higher-level contract: a normal competing writer can fail during lock acquisition with `PermissionError(13)` instead of waiting for the current owner to release the lock and then continuing into the journal conflict check.

For two conflicting sequence-1 appends the required behavior is:

1. one contender acquires the journal lock and publishes one canonical event;
2. the other contender waits for the same lock;
3. after acquiring it, the loser reloads the journal;
4. the loser discovers that sequence 1 already contains different bytes;
5. the loser raises the journal-level `FileExistsError`;
6. the final journal contains exactly one canonical event.

The production defect is therefore a mismatch between the Windows lock-acquisition primitive and the repository's required blocking serialization semantics.

## Root-cause statement

The current Windows implementation delegates contention behavior to CRT `_locking` through `msvcrt.locking(..., LK_LOCK, 1)`. The observed `PermissionError(13)` occurred inside that acquisition path while the real journal critical section remained serialized (`max_active_sections=1`).

For this repository, temporary lock ownership by another thread or process is expected control flow. A normal contender must wait for release and must not surface a permission-style exception merely because the lock is busy. Only genuine OS, handle, parameter, or filesystem failures should escape as errors.

Issue #80 will therefore replace the Windows CRT locking backend with a Windows-native blocking exclusive byte-range lock whose semantics match the POSIX `flock(LOCK_EX)` path.

## Goals

- Preserve one cross-thread and cross-process serialization contract on Windows and POSIX.
- Make normal Windows contention block rather than produce `PermissionError`.
- Preserve the journal conflict contract: one success and one `FileExistsError` for conflicting sequence-1 appends.
- Keep the production change below journal semantics; do not redesign persistence.
- Preserve fail-closed behavior for genuine Windows API failures.
- Add direct Windows thread and process regression coverage.
- Verify repeatedly on Windows Python 3.11 and Python 3.13 when available.

## Non-goals

- Do not replace the event-journal file format.
- Do not introduce a database or external lock service.
- Do not use a Python-only `threading.Lock` as the primary fix; it would not protect independent processes.
- Do not implement a polling loop around `PermissionError` or `msvcrt.LK_NBLCK`.
- Do not catch and suppress arbitrary `OSError` or `PermissionError`.
- Do not delete and recreate `.events.lock` for each critical section.
- Do not add a third-party locking dependency.
- Do not change POSIX `fcntl.flock` behavior unless a separate defect is found.
- Do not weaken journal safety assertions, add retry masking, or skip the Windows regression.

## Chosen architecture

Use Win32 `LockFileEx` and `UnlockFileEx` for the Windows backend while retaining the existing persistent sibling lock-file architecture.

```text
POSIX
    open persistent sibling lock file
        -> flock(LOCK_EX)
        -> journal critical section
        -> flock(LOCK_UN)

Windows
    open persistent sibling lock file
        -> convert CRT fd to OS HANDLE
        -> LockFileEx(exclusive, blocking, offset 0, length 1)
        -> journal critical section
        -> UnlockFileEx(offset 0, length 1)
```

The acquire call requests an exclusive lock and does not request immediate failure on contention. A competing owner therefore causes the waiter to remain inside the native lock call until the byte range becomes available or a genuine API failure occurs.

The lock range is byte 0 with length 1. The persistent lock file is a synchronization anchor and remains on disk after unlock.

## File and module structure

The Windows ctypes binding is isolated from journal semantics in a new module:

- Create: `src/ansim_review/workflow/windows_lock.py`
- Modify: `src/ansim_review/workflow/events.py`
- Create: `tests/unit/workflow/test_windows_lock.py`
- Modify: `tests/integration/workflow/test_event_journal.py`

`windows_lock.py` has one responsibility: acquire and release one exclusive blocking Windows file lock for a Python binary stream.

Its production interface is fixed as:

```python
from typing import BinaryIO


def acquire_exclusive_file_lock(stream: BinaryIO) -> None:
    ...


def release_file_lock(stream: BinaryIO) -> None:
    ...
```

`events.py` imports these helpers only on the Windows branch and continues to own lock-path construction, reparse-point checks, file opening/closing, context-manager lifetime, and journal semantics.

No journal code outside `_journal_lock()` depends on the Win32 module.

## Persistent lock-file rule

The sibling `.events.lock` file must not be deleted on release.

All contenders must open the same stable synchronization path. Deleting and recreating the lock file would add an unnecessary replacement race in which handles obtained at different times can refer to different file objects.

The path remains:

```text
<events-dir-parent>/.<events-dir-name>.lock
```

Its contents are not journal data and carry no semantic state.

## Empty lock-file behavior

The old CRT path writes one null byte before locking byte 0. The new Win32 backend does not need that sentinel.

`_journal_lock()` will stop mutating an empty lock file solely for Windows locking. `LockFileEx` operates on range `[0, 1)` of the persistent synchronization file. No application data is written to the lock file.

## Win32 binding design

`src/ansim_review/workflow/windows_lock.py` uses only Python standard-library APIs:

- `ctypes` and `ctypes.wintypes`;
- `msvcrt.get_osfhandle()` to convert `stream.fileno()` to a native file handle.

The module binds `kernel32` through `ctypes.WinDLL("kernel32", use_last_error=True)`. It must not use `ctypes.PyDLL` for the blocking native call.

The module defines the Windows `OVERLAPPED` layout explicitly, including pointer-sized `Internal` and `InternalHigh` fields, the offset/pointer union, and `hEvent`. A zero-initialized `OVERLAPPED` represents file offset 0.

The native callables are bound once at module import with explicit `argtypes` and `restype`:

- private `_lock_file_ex` -> `kernel32.LockFileEx`;
- private `_unlock_file_ex` -> `kernel32.UnlockFileEx`.

These private callable names are the narrow unit-test seam for controlled Win32 failure injection. Production code must not replace them dynamically.

Required acquire parameters:

```text
flags = LOCKFILE_EXCLUSIVE_LOCK
LOCKFILE_FAIL_IMMEDIATELY = absent
dwReserved = 0
range offset = 0
range length low = 1
range length high = 0
```

Required release parameters:

```text
same OS handle
same offset = 0
same length low = 1
same length high = 0
```

## GIL and deadlock requirement

A blocking waiter must not prevent the lock-owning Python thread from running and releasing the lock.

The Win32 binding therefore uses `ctypes.WinDLL`, not `ctypes.PyDLL`. The implementation must preserve the normal ctypes foreign-call behavior that releases the GIL around the native call.

The acceptance suite must prove this behavior with two real Python threads:

1. thread A acquires the real Windows journal lock;
2. thread B attempts the same lock and blocks;
3. thread A continues executing Python code and releases the lock;
4. thread B subsequently acquires the lock;
5. both threads terminate without `PermissionError` or deadlock.

Any implementation that waits while preventing the owner thread from executing is rejected.

## Error handling

### Normal contention

Normal contention is handled inside blocking `LockFileEx`:

```text
caller B requests lock
caller A owns lock
caller B waits
caller A releases lock
caller B acquires lock
caller B continues journal validation
```

No `PermissionError`, synthetic retry exception, or alternate journal result is produced merely because caller A temporarily owns the lock.

### Genuine acquire failure

If `LockFileEx` returns false, `acquire_exclusive_file_lock()` raises `ctypes.WinError(ctypes.get_last_error())` or an equivalent `OSError` preserving the Windows error code.

The helper does not translate that failure into `FileExistsError`, does not retry it as contention, and does not permit journal mutation after failed acquisition.

### Genuine release failure

If `UnlockFileEx` returns false, `release_file_lock()` raises an `OSError` preserving the Windows error code.

`_journal_lock()` keeps its current acquired-state discipline: release is attempted only after successful acquisition.

If the journal critical-section body has already raised and unlock also fails, the unlock `OSError` becomes the propagated exception and Python's normal exception chaining retains the body exception in `__context__`. No custom dual-exception wrapper is introduced.

### Forbidden handling

The implementation must not contain patterns equivalent to:

```python
except PermissionError:
    continue
```

or:

```python
except OSError:
    pass
```

Normal contention is distinguished structurally by choosing a blocking native lock primitive, not by guessing from exception classes after failure.

## `_journal_lock()` after the change

The Windows branch of `_journal_lock()` becomes conceptually:

```text
open .events.lock with O_RDWR | O_CREAT
enter fdopen lifetime
acquire_exclusive_file_lock(stream)
mark acquired
execute journal critical section
release_file_lock(stream)
close stream
```

The old empty-file sentinel write and `_lock_with_msvcrt()` call are removed.

The POSIX branch remains:

```text
flock(LOCK_EX)
critical section
flock(LOCK_UN)
```

## Journal semantics remain unchanged

`append_workflow_event()` continues to:

1. enter `_journal_lock(events_dir)`;
2. reload the journal while holding the lock;
3. compare the requested sequence with the existing canonical sequence;
4. permit only a byte-identical retry;
5. raise `FileExistsError` for conflicting bytes at an occupied sequence;
6. validate next sequence and previous state;
7. create the event file with `O_CREAT | O_EXCL`;
8. flush and `fsync()` canonical bytes.

The fix is intentionally below these semantics.

## Test architecture

### Unit test module: `tests/unit/workflow/test_windows_lock.py`

This module is Windows-only. On non-Windows it skips at module level before importing `ansim_review.workflow.windows_lock`.

It covers the native wrapper contract without journal logic.

Required tests:

1. **Acquire failure propagation**
   - replace private `_lock_file_ex` with a controlled callable that sets a known last-error code and returns false;
   - call `acquire_exclusive_file_lock()` on a real temporary binary stream;
   - assert an `OSError`/`WinError` exposes that error code;
   - assert no retry loop occurs.

2. **Release failure propagation**
   - replace private `_unlock_file_ex` similarly;
   - call `release_file_lock()`;
   - assert the Windows error is preserved.

The unit test does not fake successful locking semantics; real contention is covered by integration tests.

### Integration test A: same-process blocking contract

Add a Windows-specific real-lock test in `tests/integration/workflow/test_event_journal.py`.

Required choreography uses `threading.Event` or `Barrier`, not arbitrary sleeps:

1. thread A acquires `_journal_lock(root)` and signals `owner_acquired`;
2. thread B signals `waiter_started` immediately before attempting the same real lock;
3. while A still owns the lock, assert B has not signaled `waiter_acquired`;
4. signal A to release;
5. assert B then acquires and exits;
6. assert both threads terminate;
7. assert no captured `PermissionError` or unrelated exception.

The test proves both blocking semantics and absence of a GIL deadlock.

### Integration test B: Issue #80 conflicting event regression

Replace the old global `events.os.open` call-count race orchestration.

Both contender threads rendezvous immediately before entering the real journal-lock acquisition path. The real platform lock decides the winner.

Required assertions:

- exactly two worker outcomes;
- exactly one success;
- exactly one `FileExistsError`;
- zero `PermissionError` outcomes;
- zero unrelated `OSError` outcomes;
- both workers terminate;
- `load_workflow_events(root)` succeeds;
- exactly one event exists;
- persisted event is one of the supplied contenders;
- persisted event equals the winning contender;
- persisted file bytes equal canonical bytes for the winner;
- exactly one canonical event JSON file exists.

The test must not depend on which contender wins.

### Integration test C: cross-process serialization

Add a Windows process-level regression to `tests/integration/workflow/test_event_journal.py` because `_journal_lock()` promises process serialization.

Use `multiprocessing.get_context("spawn")`. Any worker callable used by child processes is defined at module scope so it is picklable under Windows spawn semantics.

Two child processes race to append conflicting sequence-1 events to the same events directory.

Required parent assertions:

- both child processes terminate normally;
- one child reports success;
- one child reports `FileExistsError`;
- no child reports `PermissionError` or unrelated `OSError`;
- parent reloads exactly one canonical event;
- persisted event is one of the contenders and matches the reported winner;
- persisted bytes are canonical;
- exactly one event JSON file exists.

Bounded joins are deadlock guards only; they are not race orchestration.

### POSIX coverage

Existing POSIX locking behavior remains unchanged. The Issue #80 conflict regression should continue to pass on POSIX, but the new native Windows wrapper and Windows process-contention tests may be Windows-specific where appropriate.

## Stress verification

After the fix, run repeated acceptance loops on actual Windows.

Minimum required when each interpreter is available:

- Python 3.11 Issue #80 thread conflict test: 200 consecutive passes;
- Python 3.13 Issue #80 thread conflict test: 200 consecutive passes;
- Python 3.11 cross-process conflict test: 100 consecutive passes;
- Python 3.13 cross-process conflict test: 100 consecutive passes.

A single failure invalidates that acceptance loop and returns the work to investigation.

If an interpreter is unavailable, record `UNAVAILABLE`; never imply a PASS.

## Regression verification

For each available supported Windows interpreter, record:

1. `tests/unit/workflow/test_windows_lock.py`;
2. full `tests/integration/workflow/test_event_journal.py`;
3. `tests/integration/workflow/`;
4. full `pytest`;
5. Ruff;
6. mypy;
7. compileall;
8. repository documentation-integrity validation if it remains an acceptance gate.

GitHub Actions status is reported literally. A run with no usable runner is `ACTIONS_UNAVAILABLE`, not PASS.

## Issue #80 evidence record

Before closing Issue #80, post an exact record containing:

- pre-fix disposition `PRODUCTION_EXCEPTION`;
- diagnostic reproduction iteration 23 on Python 3.11;
- `max_active_sections=1`;
- first two `os.open` paths resolving to the same `.events.lock` path;
- winner `EVT-0001`;
- loser `EVT-OTHER` with `PermissionError(13)` inside `_lock_with_msvcrt`;
- diagnostic artifact SHA-256 `B6FE5D487AFCDB58563F5908A5D249B7CC27CFB2E12447114806B43A99D4422E`;
- final implementation commit SHA;
- exact targeted stress commands and counts;
- Python 3.11/3.13 availability and results;
- cross-process stress results;
- full regression and static-gate results;
- GitHub Actions status.

## Production-code scope

Authorized production changes are limited to:

- new `src/ansim_review/workflow/windows_lock.py`;
- the Windows `_journal_lock()` wiring in `src/ansim_review/workflow/events.py`.

Authorized test changes are limited to:

- new `tests/unit/workflow/test_windows_lock.py`;
- event-journal thread/process coverage in `tests/integration/workflow/test_event_journal.py`;
- `tests/unit/workflow/__init__.py` only if required by repository test-package conventions.

Do not bundle unrelated workflow, persistence, parser, retrieval, packaging, or documentation refactors.

## Alternatives rejected

### Python `threading.Lock` plus the existing CRT lock

Rejected because it only serializes threads in one process. Independent processes would still depend on the problematic CRT behavior.

### Retry loop around `msvcrt.locking`

Rejected because it retains CRT contention/error semantics and creates new polling, timeout, and error-classification policy. It can also confuse genuine permission/handle failures with expected contention.

### Retry on `PermissionError`

Rejected because exception type alone does not prove the cause is temporary lock ownership. Genuine OS failures must remain fail-closed.

### External locking package

Rejected because Windows already exposes the required primitive and Issue #80 does not justify a new dependency.

## Acceptance criteria

Issue #80 is ready for closure only when all of the following hold:

1. Root cause is recorded as a Windows production lock-acquisition contract defect, not merely a flaky test.
2. Windows journal synchronization no longer uses `msvcrt.LK_LOCK` / CRT `_locking`.
3. Windows uses blocking exclusive `LockFileEx` and matching `UnlockFileEx` on byte range `[0, 1)` of the persistent sibling lock file.
4. Normal same-process thread contention blocks and later acquires without `PermissionError`.
5. The blocking waiter does not prevent the owner Python thread from running and releasing the lock.
6. Normal Windows process contention blocks and later acquires without `PermissionError`.
7. Conflicting sequence-1 appends produce exactly one success and one `FileExistsError`.
8. Final journal state contains exactly one canonical event matching the winner.
9. Genuine Win32 acquire and release failures preserve their Windows error information and remain fail-closed.
10. Windows Python 3.11 thread stress passes 200/200 when available.
11. Windows Python 3.13 thread stress passes 200/200 when available.
12. Windows Python 3.11 process stress passes 100/100 when available.
13. Windows Python 3.13 process stress passes 100/100 when available.
14. Event-journal, workflow integration, full pytest, Ruff, mypy, compileall, and documentation-integrity results are recorded for the exact final HEAD.
15. Issue #80 contains both pre-fix diagnostic evidence and final verification evidence before closure.

## Final design decision

Create a dedicated `ansim_review.workflow.windows_lock` module that wraps blocking exclusive `LockFileEx` / `UnlockFileEx` for byte range `[0, 1)` of the existing persistent sibling lock file. Wire `_journal_lock()` to that module only on Windows and leave POSIX `flock(LOCK_EX)` unchanged.

The production contract is explicit: lock contention waits; journal conflicts remain `FileExistsError`; genuine Windows API failures remain visible and fail-closed.