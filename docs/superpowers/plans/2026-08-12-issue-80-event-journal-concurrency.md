# Issue #80 Windows Event-Journal Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify the Windows concurrency failure path in the workflow event journal and replace the flaky race orchestration with a deterministic safety regression test without weakening the append-only journal invariant.

**Architecture:** Investigation comes first. The existing production lock remains authoritative while a test-local wrapper forces both worker threads to the same pre-lock rendezvous and records whether the real `_journal_lock()` critical sections overlap. If overlap is observed, stop this plan before modifying production code and return to design; if serialization is proven, replace the global `os.open()` call-count barrier with an explicit journal-lock-boundary rendezvous and strengthen the final journal assertions.

**Tech Stack:** Python 3.11/3.13, pytest, `threading`, `contextlib.contextmanager`, Windows `msvcrt.locking`, POSIX `fcntl.flock`, PowerShell, Ruff, mypy.

## Global Constraints

- Base design branch: `agent/issue-80-event-journal-concurrency`.
- Approved design: `docs/superpowers/specs/2026-08-12-issue-80-event-journal-concurrency-design.md`.
- Do not modify `src/ansim_review/workflow/events.py` unless Task 1 proves that two workers enter the real journal critical section concurrently.
- If real critical-section overlap is proven, stop this plan and write a separate production-lock design before any production fix.
- Do not use `sleep`, `xfail`, Windows-specific skip markers, retry plugins, or a timeout increase as the correctness fix.
- Keep exactly one successful append and exactly one `FileExistsError` mandatory for two conflicting sequence-1 events.
- The final journal must contain exactly one canonical event and remain loadable.
- Windows Python 3.11 and Python 3.13 each require 200 consecutive targeted passes when that interpreter is available.
- An unavailable interpreter must be reported as `UNAVAILABLE`; it must never be implied to have passed.
- GitHub Actions with no runner steps are reported as `ACTIONS_UNAVAILABLE`, not PASS or test failure.
- No new runtime or dev dependency is required for this issue.

---

## File Structure

**Expected final code scope if production locking is sound:**

- Modify: `tests/integration/workflow/test_event_journal.py:1-210`
  - Add `contextmanager` import.
  - Replace the existing call-count-based `os.open()` synchronization in `test_concurrent_events_cannot_publish_two_events_for_one_sequence`.
  - Keep all synchronization and diagnostics test-local.
  - Strengthen outcome, worker-termination, persisted-event, canonical-bytes, and file-count assertions.

**Explicitly out of scope under the test-defect path:**

- No change: `src/ansim_review/workflow/events.py`
- No change: `pyproject.toml`
- No new pytest plugin or dependency.

**Evidence/documentation:**

- Existing design: `docs/superpowers/specs/2026-08-12-issue-80-event-journal-concurrency-design.md`
- This plan: `docs/superpowers/plans/2026-08-12-issue-80-event-journal-concurrency.md`
- GitHub Issue #80: final root-cause and verification record.

---

### Task 1: Prove whether the real journal lock serializes the two Windows workers

**Files:**
- Modify temporarily: `tests/integration/workflow/test_event_journal.py:1-210`
- Read only: `src/ansim_review/workflow/events.py` (`_journal_lock`, `append_workflow_event`, `load_workflow_events`)

**Interfaces:**
- Consumes: `events._journal_lock(events_dir: Path)` context manager and `events.append_workflow_event(root, event)`.
- Produces: one trace-backed classification: `SERIALIZED`, `OVERLAP`, or `UNEXPECTED_EXCEPTION`.
- Gate: `OVERLAP` ends this plan before Task 2; no production code change is authorized by this plan.

- [ ] **Step 1: Create an isolated execution worktree from the approved branch**

Use the `superpowers:using-git-worktrees` skill before implementation. In the resulting worktree, confirm the exact branch and baseline:

```powershell
git status --short --branch
git rev-parse HEAD
git fetch origin main
git rev-list --left-right --count HEAD...origin/main
```

Expected before code edits:

```text
branch = agent/issue-80-event-journal-concurrency
working tree = clean
```

If `origin/main` advanced after the design branch was created, inspect the intervening commits before rebasing. Do not carry an unreviewed merge into the investigation.

- [ ] **Step 2: Add temporary critical-section trace instrumentation around the real `_journal_lock`**

At the imports, add:

```python
from contextlib import contextmanager
```

Inside `test_concurrent_events_cannot_publish_two_events_for_one_sequence`, temporarily replace the existing `events.os.open` synchronization with the following diagnostic wrapper. The wrapper must call the original production lock; it does not simulate or replace lock semantics.

```python
rendezvous = threading.Barrier(2)
original_journal_lock = events._journal_lock
trace: list[tuple[int, int, str]] = []
trace_guard = threading.Lock()
active_sections = 0
max_active_sections = 0


def record(label: str) -> None:
    with trace_guard:
        trace.append((time.monotonic_ns(), threading.get_ident(), label))


@contextmanager
def traced_journal_lock(events_dir: Path):
    nonlocal active_sections, max_active_sections
    record("pre_lock")
    rendezvous.wait(timeout=5)
    record("lock_attempt")
    with original_journal_lock(events_dir):
        with trace_guard:
            active_sections += 1
            max_active_sections = max(max_active_sections, active_sections)
            trace.append(
                (time.monotonic_ns(), threading.get_ident(), "lock_acquired")
            )
        try:
            yield
        finally:
            with trace_guard:
                trace.append(
                    (time.monotonic_ns(), threading.get_ident(), "lock_release")
                )
                active_sections -= 1


monkeypatch.setattr(events, "_journal_lock", traced_journal_lock)
```

Also import `time` for this diagnostic step:

```python
import time
```

Keep the two conflicting events identical to the current test except for `event_id`.

- [ ] **Step 3: Capture worker outcomes without racing on the result list**

Use an outcome lock so diagnostic data itself is not subject to a test race:

```python
outcomes: list[tuple[object, BaseException | None]] = []
outcomes_guard = threading.Lock()


def append(event) -> None:
    try:
        events.append_workflow_event(root, event)
    except BaseException as exc:
        outcome = (event, exc)
    else:
        outcome = (event, None)
    with outcomes_guard:
        outcomes.append(outcome)
```

Join workers with a deadlock guard, then require termination:

```python
for thread in threads:
    thread.join(timeout=15)
assert all(not thread.is_alive() for thread in threads), trace
```

The 15-second value is only a deadlock guard. Correctness must not depend on waiting 15 seconds.

- [ ] **Step 4: Run the diagnostic test on actual Windows Python 3.11 until one complete classification is captured**

Run:

```powershell
$test = "tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence"
py -3.11 -m pytest -q -s $test
```

Then run a bounded probe:

```powershell
$test = "tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence"
1..50 | ForEach-Object {
    py -3.11 -m pytest -q -s $test
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Diagnostic failure at iteration $_"
        break
    }
}
```

Record Windows version, Python version, pytest version, exact HEAD, `max_active_sections`, worker outcomes, and ordered trace.

- [ ] **Step 5: Apply the root-cause gate**

Classify from evidence only:

```text
SERIALIZED:
  max_active_sections == 1
  and the loser reaches the critical section only after the winner releases it.

OVERLAP:
  max_active_sections > 1.

UNEXPECTED_EXCEPTION:
  max_active_sections == 1
  but the loser raises an exception other than FileExistsError,
  or one worker does not terminate.
```

Decision:

```text
SERIALIZED          -> continue to Task 2.
OVERLAP             -> STOP. Do not edit events.py. Write a new production-lock design.
UNEXPECTED_EXCEPTION -> STOP. Trace that exception to its source before proposing a fix.
```

- [ ] **Step 6: Commit the investigation evidence only if it is useful to preserve in branch history**

If the temporary trace code is retained as an investigation commit before replacement:

```powershell
git add tests/integration/workflow/test_event_journal.py
git commit -m "test: trace event journal concurrency interleaving"
```

If the trace is captured externally and the temporary code is immediately replaced in Task 2, do not create a throwaway commit solely for instrumentation.

---

### Task 2: Replace global `os.open()` call-count synchronization with an explicit journal-lock rendezvous

**Precondition:** Task 1 classification is `SERIALIZED`.

**Files:**
- Modify: `tests/integration/workflow/test_event_journal.py:1-210`
- No production file changes.

**Interfaces:**
- Consumes: original `events._journal_lock` context manager.
- Produces: deterministic `test_concurrent_events_cannot_publish_two_events_for_one_sequence` that drives both contenders to the real journal-lock boundary.
- Outcome contract: one success, one `FileExistsError`, zero live workers, one canonical persisted event.

- [ ] **Step 1: Remove the old global `os.open()` race orchestration**

Delete all of the following from the test:

```python
original_open = events.os.open
open_calls = 0
open_calls_lock = threading.Lock()


def synchronized_open(*args, **kwargs):
    nonlocal open_calls
    with open_calls_lock:
        open_calls += 1
        should_wait = open_calls <= 2
    if should_wait:
        barrier.wait(timeout=5)
    return original_open(*args, **kwargs)


monkeypatch.setattr(events.os, "open", synchronized_open)
```

Do not replace it with another low-level call-count hook.

- [ ] **Step 2: Write the final lock-boundary synchronization wrapper**

Keep `from contextlib import contextmanager` and use the production lock itself:

```python
rendezvous = threading.Barrier(2)
original_journal_lock = events._journal_lock


@contextmanager
def synchronized_journal_lock(events_dir: Path):
    rendezvous.wait(timeout=5)
    with original_journal_lock(events_dir):
        yield


monkeypatch.setattr(events, "_journal_lock", synchronized_journal_lock)
```

This is the only synchronization hook required in the final test.

- [ ] **Step 3: Keep thread-safe outcome capture and make winner identity explicit**

Use:

```python
outcomes: list[tuple[object, BaseException | None]] = []
outcomes_guard = threading.Lock()


def append(event) -> None:
    try:
        events.append_workflow_event(root, event)
    except BaseException as exc:
        outcome = (event, exc)
    else:
        outcome = (event, None)
    with outcomes_guard:
        outcomes.append(outcome)
```

The test must not rely on thread A or thread B winning.

- [ ] **Step 4: Require worker completion before examining outcomes**

Use:

```python
for thread in threads:
    thread.start()
for thread in threads:
    thread.join(timeout=15)

assert all(not thread.is_alive() for thread in threads)
assert len(outcomes) == 2
```

Again, the timeout is a deadlock guard only.

- [ ] **Step 5: Restore the original lock before loading the journal in the main test thread**

The synchronized wrapper contains a two-party barrier and must not intercept the subsequent single-threaded read:

```python
monkeypatch.setattr(events, "_journal_lock", original_journal_lock)
```

Do this after both workers have terminated and before `load_workflow_events(root)`.

- [ ] **Step 6: Strengthen the safety assertions**

Use explicit success/failure partitions:

```python
successes = [item for item in outcomes if item[1] is None]
failures = [item for item in outcomes if item[1] is not None]

assert len(successes) == 1
assert len(failures) == 1
assert isinstance(failures[0][1], FileExistsError)

persisted = events.load_workflow_events(root)
assert len(persisted) == 1
assert persisted[0].sequence == 1
assert persisted[0] == successes[0][0]

json_files = sorted(root.glob("*.json"))
assert len(json_files) == 1
assert json_files[0].read_bytes() == events.workflow_event_bytes(persisted[0])
assert persisted[0] in (first, second)
```

These assertions preserve the existing exception contract and additionally prove that no hybrid or corrupt bytes were published.

- [ ] **Step 7: Run the focused test once on Python 3.11 and Python 3.13**

Run:

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence
py -3.13 -m pytest -q tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence
```

Expected for each available interpreter:

```text
1 passed
```

If an interpreter is not installed, record `UNAVAILABLE` rather than changing the test matrix.

- [ ] **Step 8: Run the full event-journal test module**

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py
py -3.13 -m pytest -q tests/integration/workflow/test_event_journal.py
```

Expected: all tests in the module pass on every available interpreter.

- [ ] **Step 9: Commit the deterministic regression test**

```powershell
git add tests/integration/workflow/test_event_journal.py
git commit -m "test: make event journal concurrency regression deterministic"
```

---

### Task 3: Prove the fix is stable under repeated Windows scheduling

**Files:**
- No code changes expected.
- Read: `tests/integration/workflow/test_event_journal.py`

**Interfaces:**
- Consumes: final deterministic concurrency test from Task 2.
- Produces: 200/200 targeted verification evidence for each available Windows interpreter.

- [ ] **Step 1: Record exact execution environment**

```powershell
[System.Environment]::OSVersion.VersionString
py -3.11 --version
py -3.13 --version
py -3.11 -m pytest --version
py -3.13 -m pytest --version
git rev-parse HEAD
git status --short
```

Expected: clean worktree before the acceptance loops.

- [ ] **Step 2: Run 200 consecutive passes on Windows Python 3.11**

```powershell
$test = "tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence"
1..200 | ForEach-Object {
    py -3.11 -m pytest -q $test
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11 targeted iteration $_ failed"
    }
}
```

Acceptance:

```text
200/200 PASS
```

A single failure invalidates the run and returns the work to Task 1 investigation.

- [ ] **Step 3: Run 200 consecutive passes on Windows Python 3.13**

```powershell
$test = "tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence"
1..200 | ForEach-Object {
    py -3.13 -m pytest -q $test
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.13 targeted iteration $_ failed"
    }
}
```

Acceptance:

```text
200/200 PASS
```

If Python 3.13 is unavailable, record:

```text
Python 3.13: UNAVAILABLE
```

Do not substitute another version.

- [ ] **Step 4: Confirm no test-only diagnostic instrumentation remains**

Inspect the diff:

```powershell
git diff origin/main...HEAD -- tests/integration/workflow/test_event_journal.py
```

Final test code must not contain:

```text
time.monotonic_ns diagnostic trace
max_active_sections diagnostic counters
events.os.open monkeypatch
open_calls call counter
sleep
xfail
skip
retry plugin
```

The explicit `_journal_lock` rendezvous and outcome lock are expected to remain.

---

### Task 4: Run repository regression and static acceptance gates

**Files:**
- No code changes expected unless a genuine regression is found.
- Generated local report: `build/documentation-integrity-issue80-<short-sha>.json` using a computed SHA in the command below; do not commit the generated report unless repository policy requires it.

**Interfaces:**
- Consumes: exact final HEAD from Task 3.
- Produces: module, workflow, full-suite, Ruff, mypy, compileall, and documentation-integrity results.

- [ ] **Step 1: Run workflow integration tests on Python 3.11**

```powershell
py -3.11 -m pytest -q tests/integration/workflow/
```

Expected: PASS.

- [ ] **Step 2: Run workflow integration tests on Python 3.13**

```powershell
py -3.13 -m pytest -q tests/integration/workflow/
```

Expected: PASS when Python 3.13 is available; otherwise record `UNAVAILABLE`.

- [ ] **Step 3: Run the full repository suite on Python 3.11**

```powershell
py -3.11 -m pytest -q
```

Expected: PASS with only repository-approved skips.

- [ ] **Step 4: Run the full repository suite on Python 3.13**

```powershell
py -3.13 -m pytest -q
```

Expected: PASS with only repository-approved skips when Python 3.13 is available; otherwise record `UNAVAILABLE`.

- [ ] **Step 5: Run Ruff**

```powershell
py -3.11 -m ruff check src tests
```

Expected:

```text
PASS
```

- [ ] **Step 6: Run strict mypy**

```powershell
py -3.11 -m mypy src
```

Expected:

```text
Success: no issues found
```

- [ ] **Step 7: Run compileall**

```powershell
py -3.11 -m compileall -q src tests
if ($LASTEXITCODE -ne 0) { throw "compileall failed" }
```

Expected: exit code `0`.

- [ ] **Step 8: Run documentation integrity validation with a fresh output path**

The repository validation command is:

```powershell
$sha = git rev-parse --short HEAD
$out = "build/documentation-integrity-issue80-$sha.json"
if (Test-Path $out) { Remove-Item $out }
py -3.11 -m evidence_review documentation validate `
  --repository-root . `
  --config documentation-integrity.json `
  --output $out
```

Expected: validation PASS with `0 errors`. Record warnings separately; warnings are not silently converted to errors or ignored.

- [ ] **Step 9: Confirm exact final HEAD and clean worktree**

```powershell
git rev-parse HEAD
git status --short
git diff --check
```

Expected:

```text
working tree = clean
git diff --check = no output
```

---

### Task 5: Record acceptance evidence in Issue #80 and prepare the focused PR

**Files:**
- No repository code changes expected.
- GitHub Issue #80 comment.
- Focused pull request from `agent/issue-80-event-journal-concurrency` to `main`.

**Interfaces:**
- Consumes: exact final HEAD and all Task 1-4 evidence.
- Produces: auditable Issue #80 verification record and a PR linked with `Fixes #80`.

- [ ] **Step 1: Recheck branch scope against current main**

```powershell
git fetch origin main
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
```

Expected code scope under the test-defect path:

```text
tests/integration/workflow/test_event_journal.py
docs/superpowers/specs/2026-08-12-issue-80-event-journal-concurrency-design.md
docs/superpowers/plans/2026-08-12-issue-80-event-journal-concurrency.md
```

Any production file in the diff requires explicit review against the Task 1 gate before proceeding.

- [ ] **Step 2: Post the root-cause and verification record to Issue #80**

Use this structure, replacing values only with observed evidence:

```markdown
## Issue #80 verification

Verified HEAD: `<full-sha>`
Environment: `<Windows version>`

### Root cause
- Critical-section classification: `SERIALIZED`
- The production `_journal_lock` serialized the two contenders during the captured Windows probe.
- The flaky test synchronized the first two global `os.open()` calls rather than an explicit journal-lock boundary.
- The test now rendezvous both workers immediately before the real `_journal_lock` and leaves the production lock semantics unchanged.

### Targeted stress
- Python 3.11: `200/200 PASS`
- Python 3.13: `200/200 PASS` or `UNAVAILABLE`

### Regression
- `tests/integration/workflow/test_event_journal.py`: `<result>`
- `tests/integration/workflow/` Python 3.11: `<result>`
- `tests/integration/workflow/` Python 3.13: `<result or UNAVAILABLE>`
- Full pytest Python 3.11: `<result>`
- Full pytest Python 3.13: `<result or UNAVAILABLE>`
- Ruff: `PASS`
- mypy: `PASS`
- compileall: `PASS`
- Documentation integrity: `<PASS, errors, warnings>`

### Safety invariant
- exactly one conflicting sequence-1 append succeeds;
- exactly one contender receives `FileExistsError`;
- both workers terminate;
- exactly one canonical event JSON remains;
- the journal reloads successfully and matches the winning event.

GitHub Actions status: `<PASS or ACTIONS_UNAVAILABLE with exact evidence>`
```

Do not post `SERIALIZED` unless Task 1 trace proved it. If Task 1 classified `OVERLAP` or `UNEXPECTED_EXCEPTION`, this plan should already have stopped.

- [ ] **Step 3: Open a focused PR only after all available local acceptance gates pass**

PR title:

```text
test: make Windows event-journal concurrency regression deterministic (#80)
```

PR body must include:

```markdown
Fixes #80

- replaces global `os.open()` call-count synchronization with an explicit rendezvous at the real journal-lock boundary
- keeps production event-journal code unchanged because Windows tracing proved serialized critical sections
- preserves exactly-one-success / exactly-one-`FileExistsError` safety assertions
- verifies canonical single-event persistence after the race

Validation:
- Windows Python 3.11 targeted stress: 200/200 PASS
- Windows Python 3.13 targeted stress: 200/200 PASS or UNAVAILABLE
- workflow integration: PASS on each available interpreter
- full pytest: PASS on each available interpreter
- Ruff: PASS
- mypy: PASS
- compileall: PASS
- documentation integrity: PASS
```

- [ ] **Step 4: Do not merge or close #80 until PR review and exact-head verification remain clean**

Before merge, re-run at minimum the single targeted test and `git diff --check` on the exact PR HEAD. If the PR changes after verification, the acceptance evidence must be refreshed for the new HEAD.

---

## Completion Definition

Issue #80 is implementation-complete only when all of the following are true:

1. Windows evidence proves `SERIALIZED` critical-section behavior under the test-defect path.
2. The final test no longer monkeypatches global `events.os.open` or uses call-count synchronization.
3. Exactly one append succeeds and exactly one conflicting append raises `FileExistsError`.
4. Both workers terminate and the journal contains exactly one canonical event matching the winner.
5. Python 3.11 targeted stress is 200/200 PASS when available.
6. Python 3.13 targeted stress is 200/200 PASS when available, otherwise explicitly `UNAVAILABLE`.
7. Workflow integration, full pytest, Ruff, mypy, compileall, and documentation integrity results are recorded for the exact final HEAD.
8. Issue #80 contains the root-cause trace summary and exact verification evidence.
9. The focused PR links `Fixes #80` and contains no unauthorized production-lock change.
