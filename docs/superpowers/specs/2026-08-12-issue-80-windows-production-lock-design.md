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

The temporary diagnostics and test edits were reverted after capture. This design therefore starts from the production and test code that existed before the diagnostic instrumentation.

## Problem statement

`_journal_lock()` promises to serialize workflow-journal readers and writers across threads and processes. The POSIX path uses blocking `flock(LOCK_EX)`. The Windows path currently uses CRT byte-range locking through `msvcrt.locking(..., LK_LOCK, 1)`.

The Issue #80 trace proves that the Windows path can preserve mutual exclusion while still violating the higher-level lock contract: a normal competing writer can fail during lock acquisition with `PermissionError(13)` instead of waiting for the current owner to release the lock and then continuing into the journal conflict check.

This distinction matters because the event-journal contract is not "one caller succeeds and any other exception is acceptable." For two conflicting sequence-1 appends, the required behavior is:

1. one contender acquires the journal lock and publishes one canonical event;
2. the other contender waits for the same lock;
3. after acquiring it, the loser reloads the journal;
4. the loser discovers that sequence 1 already contains different bytes;
5. the loser raises the journal-level `FileExistsError`;
6. the final journal contains exactly one canonical event.

The production defect is therefore a mismatch between the Windows lock-acquisition primitive and the repository's required blocking serialization semantics.

## Root-cause statement

The current Windows implementation delegates contention behavior to CRT `_locking` via `msvcrt.locking(..., LK_LOCK, 1)`. The observed `PermissionError(13)` occurred inside that acquisition path while the real journal critical section remained serialized (`max_active_sections=1`).

For this repository, a normal lock contender must not surface a permission-style exception merely because another thread or process currently owns the journal lock. Contention is expected control flow and must resolve by waiting for the owner to release the lock. Only actual OS, handle, parameter, or filesystem failures should escape as errors.

Issue #80 will therefore replace the Windows CRT locking backend with a Windows-native blocking exclusive byte-range lock whose semantics match the POSIX `flock(LOCK_EX)` path.

## Goals

- Preserve one cross-thread and cross-process serialization contract on both Windows and POSIX.
- Make normal Windows contention block rather than produce `PermissionError`.
- Preserve the current append-only journal conflict contract: one success and one `FileExistsError` for conflicting sequence-1 appends.
- Keep the lock path narrow and platform-specific; do not redesign event persistence.
- Preserve fail-closed behavior for genuine Windows API failures.
- Add direct Windows thread and process regression coverage.
- Verify the fix repeatedly on Windows Python 3.11 and Python 3.13 when available.

## Non-goals

- Do not replace the event-journal file format.
- Do not introduce a database or external lock service.
- Do not use a Python-only `threading.Lock` as the primary fix; it would not protect independent processes.
- Do not implement a polling loop around `PermissionError` or `msvcrt.LK_NBLCK`.
- Do not catch and suppress arbitrary `OSError` or `PermissionError`.
- Do not delete and recreate `.events.lock` for each critical section.
- Do not add a third-party locking dependency.
- Do not change POSIX `fcntl.flock` behavior unless a separate defect is found.
- Do not weaken existing journal safety assertions, add retries that mask failures, or skip the Windows regression test.

## Chosen approach

Use Win32 `LockFileEx` and `UnlockFileEx` for the Windows backend while retaining the existing persistent sibling lock-file architecture.

Conceptually:

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

The Windows acquire call must request an exclusive lock and must not request immediate failure on contention. A competing owner is therefore expected to make the caller wait until the byte range becomes available.

The lock range is byte 0 with length 1. The lock file itself is a stable synchronization anchor and remains on disk after unlock.

## Why the lock file remains persistent

The sibling `.events.lock` file must not be deleted on release.

All contenders need to open the same filesystem object and coordinate on the same kernel locking domain. Deleting and recreating the path during normal operation would introduce an unnecessary replacement race in which different handles can refer to different file objects at different times.

The existing stable lock-file path is therefore retained:

```text
<events-dir-parent>/.<events-dir-name>.lock
```

The file's contents are not semantically meaningful.

## Empty lock-file behavior

The current Windows CRT path ensures the lock file contains one null byte before locking byte 0. The Win32 backend does not need this initialization.

The new implementation should lock byte range `[0, 1)` directly on the persistent file and should not write a sentinel byte solely to make locking possible. This removes mutation that exists only to satisfy the old CRT implementation.

The lock file remains an internal synchronization artifact and is never interpreted as journal data.

## Windows backend boundary

The current helper boundary is:

```text
_journal_lock()
    -> _lock_with_msvcrt(stream, unlock=...)
```

Replace it with a Windows-native helper boundary:

```text
_journal_lock()
    -> _lock_with_win32(stream, unlock=...)
```

The public workflow/event interfaces remain unchanged.

The helper should own only the platform lock/unlock operation. `_journal_lock()` continues to own:

- lock-path construction;
- link/reparse-point rejection;
- opening and closing the sibling lock file;
- acquired-state tracking;
- the context-manager lifetime.

This keeps platform details separated from journal semantics.

## Win32 API binding

Use the Python standard library only:

- `ctypes` / `ctypes.wintypes` for Win32 bindings;
- `msvcrt.get_osfhandle()` to convert the Python/CRT file descriptor to a native Windows file handle.

Do not use `ctypes.PyDLL` for blocking Win32 calls. The binding must allow the waiting thread to release the Python GIL while the OS waits for the lock, so the lock-owning Python thread can continue and release it.

The implementation should define one small Windows-only API surface that binds:

- `kernel32.LockFileEx`;
- `kernel32.UnlockFileEx`.

The bindings must use `use_last_error=True` and explicit argument/return types. The `OVERLAPPED` value is zero-initialized and represents offset 0. Both acquire and release operate on exactly one byte.

Required acquire semantics:

```text
flags = LOCKFILE_EXCLUSIVE_LOCK
FAIL_IMMEDIATELY flag = absent
range offset = 0
range length = 1
```

Required release semantics:

```text
same handle
same offset = 0
same length = 1
```

## Error handling

### Normal contention

Normal contention is not an application error.

Expected flow:

```text
caller B requests lock
caller A owns lock
caller B waits inside LockFileEx
caller A releases lock
caller B acquires lock
caller B continues journal validation
```

No `PermissionError`, synthetic retry exception, or alternate journal result should be produced merely because caller A temporarily owns the lock.

### Genuine Win32 failure

If `LockFileEx` or `UnlockFileEx` returns failure for a genuine API/handle/filesystem reason, the helper must raise an `OSError` that preserves the Windows error code.

The implementation must not turn every `PermissionError` or `OSError` into contention. Specifically forbidden:

```python
except PermissionError:
    continue
```

and:

```python
except OSError:
    pass
```

The distinction is structural: blocking `LockFileEx` handles normal contention internally, while an API failure returned to Python remains fail-closed.

### Unlock failure

Unlock failure must not be silently ignored. If the critical-section body has not already raised, an unlock error propagates as an OS error.

If the critical-section body is already unwinding because of another exception, implementation must preserve Python context chaining so the unlock failure is not silently discarded. The implementation plan should choose one deterministic exception-preservation pattern and test it if the existing context-manager structure requires special handling.

## GIL and deadlock requirement

A blocking Windows lock call must not prevent the lock-owning Python thread from running.

The design therefore requires the Win32 call binding to use a ctypes foreign-function path that releases the GIL during the native call. The test suite must contain a same-process two-thread case in which:

1. thread A acquires the real Windows journal lock;
2. thread B attempts the same lock and blocks;
3. thread A remains able to execute Python code and release the lock;
4. thread B subsequently acquires it;
5. both threads terminate without `PermissionError` or deadlock.

A design that blocks while retaining the GIL is unacceptable even if a single-process manual probe appears to work.

## Journal behavior after acquisition

No append semantics change after the lock has been acquired.

`append_workflow_event()` continues to:

1. enter `_journal_lock(events_dir)`;
2. reload the journal while holding the lock;
3. compare the requested sequence with the canonical existing sequence;
4. permit only a byte-identical retry;
5. raise `FileExistsError` for conflicting bytes at an already-occupied sequence;
6. validate the next sequence and previous state;
7. create the event file with `O_CREAT | O_EXCL`;
8. flush and `fsync()` canonical bytes.

The production fix is intentionally below these semantics.

## Test architecture

### Test A: same-process blocking lock contract

Add a Windows-specific test for the real `_journal_lock()` behavior, not a mocked lock.

Required choreography:

1. thread A acquires the journal lock and signals `owner_acquired`;
2. thread B starts and signals `waiter_started` immediately before attempting the real lock;
3. before A releases, assert B has not entered the critical section;
4. signal A to release;
5. assert B then enters and exits the critical section;
6. assert both threads terminate;
7. assert no `PermissionError` or other unexpected exception was captured.

Use `threading.Event`/`Barrier` to express state transitions. Arbitrary `sleep()` is not a correctness mechanism.

### Test B: Issue #80 conflicting event regression

Replace the old global `events.os.open` call-count race orchestration.

Both contender threads must rendezvous immediately before invoking the real journal-lock acquisition path. The real Windows lock implementation decides the winner.

Required assertions:

- exactly two worker outcomes;
- exactly one success;
- exactly one `FileExistsError`;
- zero `PermissionError` outcomes;
- zero other OS errors;
- both workers terminate;
- `load_workflow_events(root)` succeeds;
- exactly one event exists;
- the persisted event is one of the two contenders;
- persisted bytes equal the canonical bytes for the winning event;
- exactly one canonical event JSON file exists.

The test must not depend on which contender wins.

### Test C: cross-process serialization

Add a Windows process-level regression because `_journal_lock()` promises process serialization as well as thread serialization.

Use `multiprocessing` with Windows-compatible `spawn` semantics. Worker callables and data passed to child processes must be picklable and defined at module scope where required by Python's spawn model.

Two child processes race to append conflicting sequence-1 events to the same events directory.

Required assertions in the parent:

- both child processes terminate normally;
- one reported outcome is success;
- one reported outcome represents `FileExistsError`;
- no child reports `PermissionError` or an unrelated `OSError`;
- parent reloads exactly one canonical event;
- persisted event is one of the two contenders;
- persisted bytes are canonical;
- no extra event file exists.

The test must use bounded joins only as deadlock guards, not as race orchestration.

### Test D: genuine Win32 failure propagation

Unit-test the Windows helper boundary by substituting a controlled failing Win32 API binding or equivalent narrow test seam.

Required behavior:

- a failed acquire operation raises `OSError` with the Windows error available to the caller;
- no journal mutation follows failed acquisition;
- the helper does not translate the failure into `FileExistsError`;
- the failure is not silently retried forever.

If unlock has a distinct helper path, cover an unlock failure as well.

### Existing POSIX coverage

Existing POSIX tests remain valid. Add no POSIX-specific behavior change solely to mirror the Windows implementation details.

## Stress verification

After the fix, run repeated acceptance loops on actual Windows.

Minimum required when the interpreter is available:

- Python 3.11 Issue #80 thread conflict test: 200 consecutive passes;
- Python 3.13 Issue #80 thread conflict test: 200 consecutive passes;
- Python 3.11 cross-process conflict test: 100 consecutive passes;
- Python 3.13 cross-process conflict test: 100 consecutive passes.

A single failure in an acceptance loop invalidates that loop and returns the work to investigation.

If an interpreter is not installed or otherwise unavailable, record `UNAVAILABLE`; never imply a PASS.

## Regression verification

For each available supported Windows interpreter, record:

1. Windows lock helper tests;
2. full `tests/integration/workflow/test_event_journal.py`;
3. `tests/integration/workflow/`;
4. full `pytest`;
5. Ruff;
6. mypy;
7. compileall;
8. repository documentation-integrity validation if it remains an acceptance gate.

GitHub Actions status must be reported literally. A run that receives no usable runner is `ACTIONS_UNAVAILABLE`, not PASS.

## Issue #80 evidence record

Before closing Issue #80, post an exact evidence record containing:

- the pre-fix diagnostic disposition `PRODUCTION_EXCEPTION`;
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

Expected production changes are limited to the Windows locking backend in:

- `src/ansim_review/workflow/events.py`

A small new Windows-lock helper module is acceptable only if keeping the ctypes binding inside `events.py` would make the file substantially harder to understand or test. If a new module is introduced, its sole responsibility is the Windows file-lock primitive; journal semantics remain in `events.py`.

Expected test changes are limited to event-journal/lock coverage and any narrowly required test helper module.

Do not bundle unrelated workflow, persistence, parser, retrieval, or documentation refactors.

## Alternatives rejected

### Python `threading.Lock` plus the existing CRT lock

Rejected because it only fixes contention between threads in one process. Independent processes would still depend on the problematic CRT behavior.

### Retry loop around `msvcrt.locking`

Rejected because it keeps CRT contention/error semantics as the production primitive and requires new polling, timeout, and error-classification policy. It also risks confusing genuine permission/handle failures with expected contention.

### Retry on `PermissionError`

Rejected because error type alone is not a safe proof that the only cause is a temporary competing lock. Genuine OS failures must remain fail-closed.

### External locking package

Rejected because Win32 already exposes the required primitive and Issue #80 does not justify a new dependency.

## Acceptance criteria

Issue #80 is ready for closure only when all of the following hold:

1. The root cause is recorded as a Windows production lock-acquisition contract defect, not merely a flaky test.
2. The Windows journal backend no longer uses `msvcrt.LK_LOCK` / CRT `_locking` as the synchronization primitive.
3. Normal Windows thread contention blocks and later acquires without `PermissionError`.
4. Normal Windows process contention blocks and later acquires without `PermissionError`.
5. Conflicting sequence-1 appends produce exactly one success and one `FileExistsError`.
6. Final journal state contains exactly one canonical event matching the winner.
7. Genuine Win32 API failures remain visible as OS errors and do not mutate the journal.
8. Same-process blocking behavior proves the waiter does not prevent the owner from running Python code and releasing the lock.
9. Windows Python 3.11 thread stress passes 200/200 when available.
10. Windows Python 3.13 thread stress passes 200/200 when available.
11. Windows Python 3.11 process stress passes 100/100 when available.
12. Windows Python 3.13 process stress passes 100/100 when available.
13. Event-journal, workflow integration, full pytest, Ruff, mypy, compileall, and documentation-integrity results are recorded for the exact final HEAD.
14. Issue #80 contains the pre-fix diagnostic evidence and final verification evidence before closure.

## Final design decision

Replace the Windows CRT `_locking` backend with a Windows-native blocking exclusive `LockFileEx` / `UnlockFileEx` backend operating on byte range `[0, 1)` of the existing persistent sibling lock file.

The fix remains below journal semantics: lock contention waits; journal conflicts remain `FileExistsError`; genuine Windows API failures remain fail-closed. POSIX continues to use blocking `flock(LOCK_EX)` unchanged.