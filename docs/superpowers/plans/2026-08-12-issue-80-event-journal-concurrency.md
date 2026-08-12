# Issue #80 Windows Event-Journal Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify the actual Windows failure interleaving in the workflow event journal and, only if production locking is proven sound, replace the flaky test orchestration with a deterministic safety regression test without weakening the append-only journal invariant.

**Architecture:** Diagnosis preserves the existing flaky `events.os.open` barrier so it does not change the scheduling behavior under investigation. Test-only tracing records the intercepted open paths, real `_journal_lock()` critical-section entry/exit, worker completion, and exceptions. Only a captured failure that proves serialized production critical sections and implicates the test orchestration authorizes the test-only fix; overlap or an unexpected production-lock exception terminates this plan and requires a new design.

**Tech Stack:** Python 3.11/3.13, pytest, `threading`, `contextlib.contextmanager`, Windows `msvcrt.locking`, POSIX `fcntl.flock`, PowerShell, Ruff, mypy.

## Global Constraints

- Execution branch: `agent/issue-80-event-journal-concurrency`.
- Approved design: `docs/superpowers/specs/2026-08-12-issue-80-event-journal-concurrency-design.md`.
- Do not modify `src/ansim_review/workflow/events.py` under this plan.
- Do not change the current concurrency schedule during Task 1; preserve the existing first-two-`os.open` barrier and add observation only.
- If Task 1 proves real critical-section overlap, stop and return to brainstorming for a production-lock design before editing `events.py`.
- If Task 1 captures an exception other than the expected sequence-conflict `FileExistsError` and that exception originates from production locking/persistence rather than the test hook, stop and trace it before changing test expectations.
- Do not use `sleep`, `xfail`, Windows-specific skip markers, retry plugins, or a timeout increase as the correctness fix.
- Keep exactly one successful append and exactly one `FileExistsError` mandatory for two conflicting sequence-1 events.
- The final journal must contain exactly one canonical event and remain loadable.
- Windows Python 3.11 and Python 3.13 each require 200 consecutive targeted passes when that interpreter is available.
- An unavailable interpreter is reported as `UNAVAILABLE`; it is never implied to have passed.
- GitHub Actions with no runner steps are reported as `ACTIONS_UNAVAILABLE`, not PASS or test failure.
- No new runtime or dev dependency is required.

---

## File Structure

**Expected final code scope when Task 1 proves a test-orchestration defect:**

- Modify: `tests/integration/workflow/test_event_journal.py:1-210`
  - Add `contextmanager` import.
  - Remove global `events.os.open` call-count synchronization from the final test.
  - Synchronize both contenders explicitly at the real journal-lock boundary.
  - Keep synchronization test-local.
  - Add thread-safe outcome collection.
  - Require both workers to terminate.
  - Prove the persisted event is exactly the winner and its bytes are canonical.

**No-change files under this plan:**

- `src/ansim_review/workflow/events.py`
- `pyproject.toml`

**Documentation/evidence:**

- Design: `docs/superpowers/specs/2026-08-12-issue-80-event-journal-concurrency-design.md`
- Plan: `docs/superpowers/plans/2026-08-12-issue-80-event-journal-concurrency.md`
- Local diagnostic capture: `build/issue80-diagnostic-py311.txt` — generated only, not committed.
- GitHub Issue #80 — final root-cause and verification record.

---

### Task 1: Capture the existing flaky interleaving without changing its schedule

**Files:**
- Modify temporarily: `tests/integration/workflow/test_event_journal.py:1-210`
- Read only: `src/ansim_review/workflow/events.py` (`_journal_lock`, `_lock_with_msvcrt`, `append_workflow_event`, `load_workflow_events`)
- Generate locally: `build/issue80-diagnostic-py311.txt`

**Interfaces:**
- Consumes: the current `events.os.open` barrier, real `events._journal_lock(events_dir: Path)`, and `events.append_workflow_event(root, event)`.
- Produces exactly one evidence-backed disposition: `TEST_ORCHESTRATION_DEFECT`, `PRODUCTION_LOCK_DEFECT`, `PRODUCTION_EXCEPTION`, or `NOT_REPRODUCED`.
- Only `TEST_ORCHESTRATION_DEFECT` authorizes Task 2.

- [ ] **Step 1: Create the execution worktree with the required Superpowers skill**

Invoke `superpowers:using-git-worktrees`, then confirm branch and repository state:

```powershell
git status --short --branch
git rev-parse HEAD
git fetch origin main
git rev-list --left-right --count HEAD...origin/main
```

Required before editing:

```text
branch: agent/issue-80-event-journal-concurrency
working tree: clean
```

If `origin/main` is ahead, inspect those commits and reconcile the branch before diagnosis. Do not investigate an unreviewed stale base.

- [ ] **Step 2: Add observation imports only**

At the top of `tests/integration/workflow/test_event_journal.py`, add:

```python
import time
from contextlib import contextmanager
```

Keep the existing imports and existing test logic otherwise unchanged at this step.

- [ ] **Step 3: Add a thread-safe trace recorder inside the existing concurrency test**

Immediately after `second = replace(first, event_id="EVT-OTHER")`, add:

```python
trace: list[tuple[int, int, str]] = []
trace_guard = threading.Lock()
active_sections = 0
max_active_sections = 0


def record(label: str) -> None:
    with trace_guard:
        trace.append((time.monotonic_ns(), threading.get_ident(), label))
```

- [ ] **Step 4: Instrument the existing `events.os.open` barrier without changing which calls wait**

Keep the existing:

```python
barrier = threading.Barrier(2)
original_open = events.os.open
open_calls = 0
open_calls_lock = threading.Lock()
```

Replace only the body of `synchronized_open` with the traced equivalent below. The first two calls must still wait on the same barrier exactly as before:

```python
def synchronized_open(*args, **kwargs):
    nonlocal open_calls
    path = str(args[0]) if args else "<missing-path>"
    with open_calls_lock:
        open_calls += 1
        call_number = open_calls
        should_wait = call_number <= 2
    record(f"os_open_before:{call_number}:{path}")
    if should_wait:
        record(f"os_open_barrier_enter:{call_number}:{path}")
        barrier.wait(timeout=5)
        record(f"os_open_barrier_exit:{call_number}:{path}")
    descriptor = original_open(*args, **kwargs)
    record(f"os_open_after:{call_number}:{path}")
    return descriptor
```

Keep:

```python
monkeypatch.setattr(events.os, "open", synchronized_open)
```

This step observes the current schedule; it must not move the barrier to a new location.

- [ ] **Step 5: Wrap the real `_journal_lock` only to measure critical-section overlap**

Save the current function after the `events.os.open` monkeypatch is configured:

```python
original_journal_lock = events._journal_lock
```

Add:

```python
@contextmanager
def traced_journal_lock(events_dir: Path):
    nonlocal active_sections, max_active_sections
    record("journal_lock_enter")
    with original_journal_lock(events_dir):
        with trace_guard:
            active_sections += 1
            max_active_sections = max(max_active_sections, active_sections)
            trace.append(
                (time.monotonic_ns(), threading.get_ident(), "journal_lock_acquired")
            )
        try:
            yield
        finally:
            with trace_guard:
                trace.append(
                    (time.monotonic_ns(), threading.get_ident(), "journal_lock_release")
                )
                active_sections -= 1


monkeypatch.setattr(events, "_journal_lock", traced_journal_lock)
```

The wrapper delegates to the real production lock and introduces no new rendezvous.

- [ ] **Step 6: Make outcome collection thread-safe while preserving the same two append workers**

Replace the raw shared outcome list with:

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

Keep the same two worker threads and the existing 5-second join during diagnosis:

```python
threads = [
    threading.Thread(target=append, args=(first,)),
    threading.Thread(target=append, args=(second,)),
]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join(timeout=5)
```

The current join timeout is deliberately preserved in Task 1 because changing it would alter the failure condition being investigated.

- [ ] **Step 7: Print the diagnostic state before the existing assertions**

Add:

```python
print(f"ISSUE80 max_active_sections={max_active_sections}")
print(f"ISSUE80 open_calls={open_calls}")
print(f"ISSUE80 alive={[thread.is_alive() for thread in threads]!r}")
print(f"ISSUE80 outcomes={outcomes!r}")
for entry in trace:
    print(f"ISSUE80 trace={entry!r}")
```

Then adapt the existing assertions only enough to account for `(event, exception)` tuples while preserving the same safety requirements:

```python
exceptions = [item[1] for item in outcomes]
assert len(outcomes) == 2
assert exceptions.count(None) == 1
assert sum(isinstance(exc, FileExistsError) for exc in exceptions) == 1
```

Do not add a new passing condition.

- [ ] **Step 8: Run the instrumented current test on actual Windows Python 3.11 and preserve all output**

```powershell
New-Item -ItemType Directory -Force build | Out-Null
$test = "tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence"
"=== environment ===" | Set-Content build/issue80-diagnostic-py311.txt
[System.Environment]::OSVersion.VersionString |
    Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
py -3.11 --version 2>&1 |
    Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
py -3.11 -m pytest --version 2>&1 |
    Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
git rev-parse HEAD |
    Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
```

Run up to 100 iterations, stopping on the first failure:

```powershell
$failed = $false
1..100 | ForEach-Object {
    if ($failed) { return }
    "=== diagnostic iteration $_ ===" |
        Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
    py -3.11 -m pytest -q -s $test 2>&1 |
        Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
    if ($LASTEXITCODE -ne 0) {
        "=== captured failure at iteration $_ ===" |
            Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
        $failed = $true
    }
}
```

- [ ] **Step 9: Classify the captured run without inference beyond the trace**

Use these exact dispositions:

```text
TEST_ORCHESTRATION_DEFECT
- a failing run is captured;
- max_active_sections never exceeds 1;
- the trace proves the first two synchronized os.open calls are lock-file opens rather than event-file create attempts;
- the observed failure is attributable to the test schedule/completion logic rather than an exception originating from the production lock/persistence path.

PRODUCTION_LOCK_DEFECT
- max_active_sections > 1 in any run.

PRODUCTION_EXCEPTION
- max_active_sections <= 1, but a failing run contains an unexpected exception originating from _journal_lock, msvcrt.locking, file creation, fsync, or journal loading rather than the test barrier itself.

NOT_REPRODUCED
- 100 instrumented iterations complete without a failing run.
```

Gate:

```text
TEST_ORCHESTRATION_DEFECT -> proceed to Task 2.
PRODUCTION_LOCK_DEFECT    -> STOP; do not edit events.py; create a new production-lock design.
PRODUCTION_EXCEPTION      -> STOP; trace the exact production exception before designing a fix.
NOT_REPRODUCED            -> STOP; do not claim root cause or modify the test yet.
```

The Issue #80 acceptance criterion requires an identified condition, so `NOT_REPRODUCED` is not sufficient to proceed.

- [ ] **Step 10: Do not commit temporary diagnostics**

`time`, the trace recorder, open-path logging, critical-section counters, diagnostic `print()` calls, and `build/issue80-diagnostic-py311.txt` are investigation-only. Do not stage or commit them.

---

### Task 2: Replace global `os.open()` call-count synchronization with an explicit journal-lock rendezvous

**Precondition:** Task 1 disposition is exactly `TEST_ORCHESTRATION_DEFECT`.

**Files:**
- Modify: `tests/integration/workflow/test_event_journal.py:1-210`
- No production file changes.

**Interfaces:**
- Consumes: the real `events._journal_lock` context manager.
- Produces: deterministic `test_concurrent_events_cannot_publish_two_events_for_one_sequence`.
- Outcome contract: one success, one `FileExistsError`, zero live workers, one canonical persisted event matching the winner.

- [ ] **Step 1: Remove all temporary diagnosis and the old global `events.os.open` hook**

Remove all Task 1-only instrumentation, including:

```text
import time
trace
trace_guard
active_sections
max_active_sections
record()
traced_journal_lock()
diagnostic print() calls
open-path trace labels
original_open
open_calls
open_calls_lock
synchronized_open()
monkeypatch.setattr(events.os, "open", ...)
```

Keep:

```python
from contextlib import contextmanager
```

- [ ] **Step 2: Replace the full concurrency test with the deterministic lock-boundary version**

Use this final function:

```python
def test_concurrent_events_cannot_publish_two_events_for_one_sequence(
    tmp_path: Path,
    monkeypatch,
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
    rendezvous = threading.Barrier(2)
    original_journal_lock = events._journal_lock

    @contextmanager
    def synchronized_journal_lock(events_dir: Path):
        rendezvous.wait(timeout=5)
        with original_journal_lock(events_dir):
            yield

    monkeypatch.setattr(events, "_journal_lock", synchronized_journal_lock)
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

    persisted = events.load_workflow_events(root)
    assert len(persisted) == 1
    assert persisted[0].sequence == 1
    assert persisted[0] == successes[0][0]
    assert persisted[0] in (first, second)

    json_files = sorted(root.glob("*.json"))
    assert len(json_files) == 1
    assert json_files[0].read_bytes() == events.workflow_event_bytes(persisted[0])
```

The test must not depend on which event wins.

- [ ] **Step 3: Run the focused test on Python 3.11**

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence
```

Expected: `1 passed`.

- [ ] **Step 4: Run the focused test on Python 3.13 when available**

```powershell
py -3.13 -m pytest -q tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence
```

Expected when available: `1 passed`. If unavailable, record exactly `Python 3.13: UNAVAILABLE`; do not substitute another interpreter.

- [ ] **Step 5: Run the entire event-journal module on each available interpreter**

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py
py -3.13 -m pytest -q tests/integration/workflow/test_event_journal.py
```

Expected: all module tests pass on each available interpreter.

- [ ] **Step 6: Review the final code diff**

```powershell
git diff -- tests/integration/workflow/test_event_journal.py
git diff --check
```

The diff must contain no production file change and no temporary diagnostic code.

- [ ] **Step 7: Commit the deterministic regression test**

```powershell
git add tests/integration/workflow/test_event_journal.py
git commit -m "test: make event journal concurrency regression deterministic"
```

---

### Task 3: Prove the deterministic test remains stable under Windows scheduling

**Files:**
- No code changes expected.
- Read: `tests/integration/workflow/test_event_journal.py`

**Interfaces:**
- Consumes: Task 2 commit.
- Produces: 200 consecutive targeted passes for each available Windows interpreter.

- [ ] **Step 1: Record exact acceptance environment**

```powershell
[System.Environment]::OSVersion.VersionString
py -3.11 --version
py -3.13 --version
py -3.11 -m pytest --version
py -3.13 -m pytest --version
git rev-parse HEAD
git status --short
```

Required: clean worktree before stress runs.

- [ ] **Step 2: Run 200 consecutive targeted passes on Windows Python 3.11**

```powershell
$test = "tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence"
1..200 | ForEach-Object {
    py -3.11 -m pytest -q $test
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11 targeted iteration $_ failed"
    }
}
```

Acceptance: `Python 3.11 targeted: 200/200 PASS`. One failure invalidates the run and returns the work to Task 1.

- [ ] **Step 3: Run 200 consecutive targeted passes on Windows Python 3.13 when available**

```powershell
1..200 | ForEach-Object {
    py -3.13 -m pytest -q $test
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.13 targeted iteration $_ failed"
    }
}
```

Acceptance when available: `Python 3.13 targeted: 200/200 PASS`. When unavailable, record exactly `Python 3.13: UNAVAILABLE`.

- [ ] **Step 4: Prove the final test contains no forbidden workaround**

```powershell
git grep -n -E "open_calls|synchronized_open|time\.monotonic_ns|pytest\.mark\.xfail|pytest\.mark\.skip|time\.sleep" -- tests/integration/workflow/test_event_journal.py
```

Expected: no matches.

Verify the intended explicit synchronization hook remains:

```powershell
git grep -n "synchronized_journal_lock" -- tests/integration/workflow/test_event_journal.py
```

Expected: the final test-local lock-boundary wrapper is present.

---

### Task 4: Run repository regression and static acceptance gates

**Files:**
- No code changes expected.
- Generate locally: documentation-integrity report under `build/` with the current short commit SHA embedded in the filename.

**Interfaces:**
- Consumes: exact final code HEAD from Task 3.
- Produces: workflow, full-suite, Ruff, mypy, compileall, and documentation-integrity evidence.

- [ ] **Step 1: Run workflow integration tests on Python 3.11**

```powershell
py -3.11 -m pytest -q tests/integration/workflow/
```

Expected: PASS.

- [ ] **Step 2: Run workflow integration tests on Python 3.13 when available**

```powershell
py -3.13 -m pytest -q tests/integration/workflow/
```

Expected when available: PASS. Otherwise record exactly `Python 3.13 workflow integration: UNAVAILABLE`.

- [ ] **Step 3: Run the full repository suite on Python 3.11**

```powershell
py -3.11 -m pytest -q
```

Expected: PASS with only repository-approved skips.

- [ ] **Step 4: Run the full repository suite on Python 3.13 when available**

```powershell
py -3.13 -m pytest -q
```

Expected when available: PASS with only repository-approved skips. Otherwise record exactly `Python 3.13 full pytest: UNAVAILABLE`.

- [ ] **Step 5: Run Ruff**

```powershell
py -3.11 -m ruff check src tests
```

Expected: PASS.

- [ ] **Step 6: Run strict mypy**

```powershell
py -3.11 -m mypy src
```

Expected: `Success: no issues found`.

- [ ] **Step 7: Run compileall**

```powershell
py -3.11 -m compileall -q src tests
if ($LASTEXITCODE -ne 0) { throw "compileall failed" }
```

Expected: exit code `0`.

- [ ] **Step 8: Run documentation-integrity validation to a fresh local output**

```powershell
New-Item -ItemType Directory -Force build | Out-Null
$sha = git rev-parse --short HEAD
$out = "build/documentation-integrity-issue80-$sha.json"
if (Test-Path $out) { Remove-Item $out }
py -3.11 -m evidence_review documentation validate `
  --repository-root . `
  --config documentation-integrity.json `
  --output $out
```

Expected: PASS with `0 errors`. Record the warning count exactly.

- [ ] **Step 9: Confirm exact final HEAD and clean worktree**

```powershell
git rev-parse HEAD
git status --short
git diff --check
```

Required: clean working tree and no `git diff --check` output. Generated `build/` evidence must not be committed.

---

### Task 5: Record acceptance evidence in Issue #80 and prepare the focused PR

**Files:**
- No repository code changes expected.
- GitHub Issue #80 comment.
- Pull request from `agent/issue-80-event-journal-concurrency` to `main`.

**Interfaces:**
- Consumes: Task 1 disposition and all exact Task 3-4 command results.
- Produces: auditable Issue #80 evidence and a focused PR linked with `Fixes #80`.

- [ ] **Step 1: Recheck branch scope against current main**

```powershell
git fetch origin main
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
```

Under the `TEST_ORCHESTRATION_DEFECT` path, the only expected repository paths are:

```text
tests/integration/workflow/test_event_journal.py
docs/superpowers/specs/2026-08-12-issue-80-event-journal-concurrency-design.md
docs/superpowers/plans/2026-08-12-issue-80-event-journal-concurrency.md
```

Any `src/` path blocks PR creation under this plan.

- [ ] **Step 2: Post an Issue #80 verification comment using only observed results**

The comment must contain these sections and no blank result fields:

```markdown
## Issue #80 verification

### Verified revision
- Full commit SHA from `git rev-parse HEAD`
- Windows version from `[System.Environment]::OSVersion.VersionString`
- Python and pytest versions used

### Root cause
- Critical disposition: `TEST_ORCHESTRATION_DEFECT`
- State the exact first two `os.open` paths shown in the captured failing trace.
- State the measured `max_active_sections` from the captured failing trace.
- State the exact losing-worker outcome from that trace.
- Explain why those observations identify the test orchestration rather than production locking as the defect.
- State that production `events.py` is unchanged.

### Targeted stress
- Copy the exact Python 3.11 200-run result.
- Copy the exact Python 3.13 200-run result, or the literal `Python 3.13: UNAVAILABLE`.

### Regression
- Copy the exact event-journal module result.
- Copy the exact workflow-integration result for each available interpreter.
- Copy the exact full-pytest result for each available interpreter.
- Record Ruff, mypy, compileall, and documentation-integrity results including documentation warnings.

### Safety invariant
- exactly one conflicting sequence-1 append succeeds;
- exactly one contender receives `FileExistsError`;
- both workers terminate;
- exactly one canonical event JSON remains;
- the reloaded journal event equals the winning contender.

### GitHub Actions
- Record exact workflow status if a runner executed.
- If jobs have no executed runner steps, record `ACTIONS_UNAVAILABLE` and do not claim PASS.
```

Do not post `TEST_ORCHESTRATION_DEFECT` unless Task 1 captured evidence satisfying that disposition.

- [ ] **Step 3: Open the focused PR only after all available local acceptance gates pass**

Use this title exactly:

```text
test: make Windows event-journal concurrency regression deterministic (#80)
```

Use this body when Python 3.13 completed the acceptance run:

```markdown
Fixes #80

- replaces global `os.open()` call-count synchronization with an explicit rendezvous at the real journal-lock boundary
- keeps production event-journal code unchanged because the captured Windows failure showed a test-orchestration defect with serialized production critical sections
- preserves exactly-one-success / exactly-one-`FileExistsError` safety assertions
- verifies canonical single-event persistence after the race

Validation:
- Windows Python 3.11 targeted stress: 200/200 PASS
- Windows Python 3.13 targeted stress: 200/200 PASS
- workflow integration: PASS on every available interpreter
- full pytest: PASS on every available interpreter
- Ruff: PASS
- mypy: PASS
- compileall: PASS
- documentation integrity: PASS
```

If Python 3.13 was unavailable, change only the Python 3.13 validation line to:

```text
- Windows Python 3.13 targeted stress: UNAVAILABLE
```

Do not change a failed validation into `UNAVAILABLE`.

- [ ] **Step 4: Keep #80 open until exact-PR-HEAD verification remains clean**

Before merge, run:

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence
git diff --check origin/main...HEAD
git rev-parse HEAD
```

If the PR HEAD changes after the acceptance run, refresh Issue #80 evidence for the new HEAD before merge or closure.

---

## Self-Review Mapping

- Existing flaky schedule preserved during root-cause capture: Task 1 Steps 2-8.
- Actual `os.open` paths captured: Task 1 Step 4 and Step 8.
- Real critical-section overlap measured: Task 1 Step 5.
- Explicit production-defect stop gates: Task 1 Step 9.
- Removal of global `os.open` call-count race: Task 2 Steps 1-2.
- Exactly one success and one `FileExistsError`: Task 2 Step 2 assertions.
- Worker termination: Task 2 Step 2 assertions.
- Canonical one-event persistence: Task 2 Step 2 assertions.
- Python 3.11/3.13 200-run requirement: Task 3.
- No retry/skip/sleep masking: Task 3 Step 4.
- Workflow/full/static/documentation regression: Task 4.
- Exact-head Issue evidence and PR linkage: Task 5.

No production code change is authorized by this implementation plan. Any `PRODUCTION_LOCK_DEFECT`, `PRODUCTION_EXCEPTION`, or `NOT_REPRODUCED` disposition terminates the test-only implementation path.

## Completion Definition

Issue #80 is implementation-ready for review under this plan only when all of the following are true:

1. Task 1 captures an actual failing Windows interleaving and classifies it `TEST_ORCHESTRATION_DEFECT` from trace evidence.
2. The final test no longer monkeypatches global `events.os.open` or uses call-count synchronization.
3. Exactly one append succeeds and exactly one conflicting append raises `FileExistsError`.
4. Both workers terminate and exactly one canonical journal event remains.
5. Python 3.11 targeted stress is 200/200 PASS when available.
6. Python 3.13 targeted stress is 200/200 PASS when available, otherwise explicitly `UNAVAILABLE`.
7. Workflow integration, full pytest, Ruff, mypy, compileall, and documentation integrity are recorded for the exact final HEAD.
8. Issue #80 contains the captured root-cause trace summary and exact verification evidence.
9. The focused PR links `Fixes #80` and contains no unauthorized production-lock change.
