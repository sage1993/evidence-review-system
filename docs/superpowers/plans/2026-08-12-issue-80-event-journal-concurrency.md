# Issue #80 Windows Event-Journal Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify the Windows concurrency failure path in the workflow event journal and replace the flaky race orchestration with a deterministic safety regression test without weakening the append-only journal invariant.

**Architecture:** Investigation comes first. A test-local wrapper forces both worker threads to the same pre-lock rendezvous, then delegates to the real production `_journal_lock()` and measures whether its critical sections overlap. If overlap or an unexpected loser failure is observed, this plan stops before any production edit; if serialization is proven, the final test replaces the global `os.open()` call-count barrier with an explicit journal-lock-boundary rendezvous and stronger persistence assertions.

**Tech Stack:** Python 3.11/3.13, pytest, `threading`, `contextlib.contextmanager`, Windows `msvcrt.locking`, POSIX `fcntl.flock`, PowerShell, Ruff, mypy.

## Global Constraints

- Execution branch: `agent/issue-80-event-journal-concurrency`.
- Approved design: `docs/superpowers/specs/2026-08-12-issue-80-event-journal-concurrency-design.md`.
- Do not modify `src/ansim_review/workflow/events.py` under this plan.
- If Task 1 proves real critical-section overlap, stop and return to brainstorming for a separate production-lock design before editing `events.py`.
- If Task 1 produces an exception other than the expected `FileExistsError`, stop and trace that exception before changing the test expectation.
- Do not use `sleep`, `xfail`, Windows-specific skip markers, retry plugins, or a timeout increase as the correctness fix.
- Keep exactly one successful append and exactly one `FileExistsError` mandatory for two conflicting sequence-1 events.
- The final journal must contain exactly one canonical event and remain loadable.
- Windows Python 3.11 and Python 3.13 each require 200 consecutive targeted passes when that interpreter is available.
- An unavailable interpreter is reported as `UNAVAILABLE`; it is never implied to have passed.
- GitHub Actions with no runner steps are reported as `ACTIONS_UNAVAILABLE`, not PASS or test failure.
- No new runtime or dev dependency is required.

---

## File Structure

**Expected final code scope when Task 1 proves production locking is sound:**

- Modify: `tests/integration/workflow/test_event_journal.py:1-210`
  - Add `contextmanager` import.
  - Replace `events.os.open` call-count synchronization in `test_concurrent_events_cannot_publish_two_events_for_one_sequence`.
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

### Task 1: Prove whether the real journal lock serializes the two Windows workers

**Files:**
- Modify temporarily: `tests/integration/workflow/test_event_journal.py:1-210`
- Read only: `src/ansim_review/workflow/events.py` (`_journal_lock`, `append_workflow_event`, `load_workflow_events`)
- Generate locally: `build/issue80-diagnostic-py311.txt`

**Interfaces:**
- Consumes: `events._journal_lock(events_dir: Path)` and `events.append_workflow_event(root, event)`.
- Produces exactly one classification: `SERIALIZED`, `OVERLAP`, or `UNEXPECTED_EXCEPTION`.
- Only `SERIALIZED` authorizes Task 2.

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

If `origin/main` is ahead, inspect those commits and reconcile the branch before investigation. Do not begin diagnosis on an unreviewed stale base.

- [ ] **Step 2: Replace the current race hook temporarily with a trace wrapper around the real `_journal_lock`**

Add these imports while diagnosing:

```python
from contextlib import contextmanager
import time
```

Inside `test_concurrent_events_cannot_publish_two_events_for_one_sequence`, keep `first`, `second`, `root`, and the two worker threads, but replace the existing `events.os.open` monkeypatch with:

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

This wrapper must delegate to `original_journal_lock`; it is not a fake lock.

- [ ] **Step 3: Make diagnostic outcome capture thread-safe**

Replace the shared outcome list logic with:

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


threads = [
    threading.Thread(target=append, args=(first,)),
    threading.Thread(target=append, args=(second,)),
]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join(timeout=15)
```

Then emit diagnostic data before assertions:

```python
print(f"ISSUE80 max_active_sections={max_active_sections}")
print(f"ISSUE80 outcomes={outcomes!r}")
for entry in trace:
    print(f"ISSUE80 trace={entry!r}")

assert all(not thread.is_alive() for thread in threads), trace
```

The 15-second join is a deadlock guard only; it is not the correctness mechanism.

- [ ] **Step 4: Run the diagnostic test on actual Windows Python 3.11 and preserve the output**

```powershell
New-Item -ItemType Directory -Force build | Out-Null
$test = "tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence"
py -3.11 -m pytest -q -s $test 2>&1 | Tee-Object -FilePath build/issue80-diagnostic-py311.txt
```

Then execute a bounded 50-run probe, appending all output to the same local evidence file:

```powershell
1..50 | ForEach-Object {
    "=== diagnostic iteration $_ ===" | Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
    py -3.11 -m pytest -q -s $test 2>&1 |
        Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
    if ($LASTEXITCODE -ne 0) {
        "=== stopped on iteration $_ ===" |
            Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
        break
    }
}
```

Also capture the environment in the same file:

```powershell
"=== environment ===" | Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
[System.Environment]::OSVersion.VersionString |
    Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
py -3.11 --version 2>&1 |
    Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
py -3.11 -m pytest --version 2>&1 |
    Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
git rev-parse HEAD |
    Tee-Object -FilePath build/issue80-diagnostic-py311.txt -Append
```

- [ ] **Step 5: Apply the root-cause gate from the captured evidence**

Use these exact classifications:

```text
SERIALIZED
- max_active_sections == 1 on completed runs;
- exactly one append succeeds;
- the other completed append raises FileExistsError;
- both workers terminate.

OVERLAP
- max_active_sections > 1 in any completed run.

UNEXPECTED_EXCEPTION
- max_active_sections == 1, but a worker raises an exception other than FileExistsError;
- or a worker remains alive after the deadlock guard;
- or the diagnostic wrapper itself cannot complete consistently.
```

Gate:

```text
SERIALIZED           -> proceed to Task 2.
OVERLAP              -> STOP this plan; do not edit events.py; create a new production-lock design.
UNEXPECTED_EXCEPTION -> STOP this plan; trace that exact exception before proposing a change.
```

Do not reinterpret `OVERLAP` as a flaky-test-only defect.

- [ ] **Step 6: Do not commit temporary diagnostics**

`time`, `trace`, `active_sections`, `max_active_sections`, diagnostic `print()` calls, and `build/issue80-diagnostic-py311.txt` are investigation-only. Task 2 replaces the temporary code with the final regression test. Do not stage or commit the generated diagnostic file.

---

### Task 2: Replace global `os.open()` call-count synchronization with an explicit journal-lock rendezvous

**Precondition:** Task 1 classification is exactly `SERIALIZED`.

**Files:**
- Modify: `tests/integration/workflow/test_event_journal.py:1-210`
- No production file changes.

**Interfaces:**
- Consumes: the real `events._journal_lock` context manager.
- Produces: deterministic `test_concurrent_events_cannot_publish_two_events_for_one_sequence`.
- Outcome contract: one success, one `FileExistsError`, zero live workers, one canonical persisted event matching the winner.

- [ ] **Step 1: Remove all temporary diagnosis and the old `events.os.open` hook**

Remove:

```text
import time
trace
trace_guard
active_sections
max_active_sections
record()
traced_journal_lock()
diagnostic print() calls
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

Use this final function body:

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

Expected:

```text
1 passed
```

- [ ] **Step 4: Run the focused test on Python 3.13 when available**

```powershell
py -3.13 -m pytest -q tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence
```

Expected when available:

```text
1 passed
```

If the Python launcher reports that 3.13 is unavailable, record exactly `Python 3.13: UNAVAILABLE`; do not substitute another interpreter.

- [ ] **Step 5: Run the entire event-journal test module on each available interpreter**

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py
py -3.13 -m pytest -q tests/integration/workflow/test_event_journal.py
```

Expected: all tests in the module pass on each available interpreter.

- [ ] **Step 6: Review the diff before committing**

```powershell
git diff -- tests/integration/workflow/test_event_journal.py
git diff --check
```

The diff must contain no production file changes and no temporary diagnostic trace code.

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

Acceptance:

```text
Python 3.11 targeted: 200/200 PASS
```

One failure invalidates the run and returns the work to Task 1 investigation.

- [ ] **Step 3: Run 200 consecutive targeted passes on Windows Python 3.13 when available**

```powershell
1..200 | ForEach-Object {
    py -3.13 -m pytest -q $test
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.13 targeted iteration $_ failed"
    }
}
```

Acceptance when available:

```text
Python 3.13 targeted: 200/200 PASS
```

When unavailable:

```text
Python 3.13: UNAVAILABLE
```

- [ ] **Step 4: Prove the final test contains no forbidden workaround**

```powershell
git grep -n -E "open_calls|synchronized_open|time\.monotonic_ns|pytest\.mark\.xfail|pytest\.mark\.skip|time\.sleep" -- tests/integration/workflow/test_event_journal.py
```

Expected: no matches.

Then verify the expected explicit hook remains:

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

Expected when available: PASS. Otherwise record `Python 3.13 workflow integration: UNAVAILABLE`.

- [ ] **Step 3: Run the full repository suite on Python 3.11**

```powershell
py -3.11 -m pytest -q
```

Expected: PASS with only repository-approved skips.

- [ ] **Step 4: Run the full repository suite on Python 3.13 when available**

```powershell
py -3.13 -m pytest -q
```

Expected when available: PASS with only repository-approved skips. Otherwise record `Python 3.13 full pytest: UNAVAILABLE`.

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

Expected: PASS with `0 errors`. Record the warning count exactly; do not omit it.

- [ ] **Step 9: Confirm exact final HEAD and clean worktree**

```powershell
git rev-parse HEAD
git status --short
git diff --check
```

Required:

```text
working tree: clean
git diff --check: no output
```

Generated `build/` evidence must remain untracked or ignored and must not be committed as part of the code fix.

---

### Task 5: Record acceptance evidence in Issue #80 and prepare the focused PR

**Files:**
- No repository code changes expected.
- GitHub Issue #80 comment.
- Pull request from `agent/issue-80-event-journal-concurrency` to `main`.

**Interfaces:**
- Consumes: Task 1 classification and all exact Task 3-4 command results.
- Produces: auditable Issue #80 evidence and a focused PR linked with `Fixes #80`.

- [ ] **Step 1: Recheck branch scope against current main**

```powershell
git fetch origin main
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
```

Under the `SERIALIZED` path, the only expected repository paths are:

```text
tests/integration/workflow/test_event_journal.py
docs/superpowers/specs/2026-08-12-issue-80-event-journal-concurrency-design.md
docs/superpowers/plans/2026-08-12-issue-80-event-journal-concurrency.md
```

Any `src/` path in the diff blocks PR creation under this plan.

- [ ] **Step 2: Post an Issue #80 verification comment using only observed results**

The comment must contain these sections and no blank result fields:

```markdown
## Issue #80 verification

### Verified revision
- Full commit SHA from `git rev-parse HEAD`
- Windows version from `[System.Environment]::OSVersion.VersionString`
- Python and pytest versions used

### Root cause
- Critical-section classification: `SERIALIZED`
- State that the real `_journal_lock` serialized the two contenders in the Windows trace.
- State that the removed test orchestration synchronized global `os.open()` call order instead of an explicit journal-lock boundary.
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

Do not post `SERIALIZED` if Task 1 did not prove it.

- [ ] **Step 3: Open the focused PR only after all available local acceptance gates pass**

Use this title exactly:

```text
test: make Windows event-journal concurrency regression deterministic (#80)
```

Use this fixed body, selecting the correct literal Python 3.13 line from the two choices below:

```markdown
Fixes #80

- replaces global `os.open()` call-count synchronization with an explicit rendezvous at the real journal-lock boundary
- keeps production event-journal code unchanged because the Windows trace proved serialized critical sections
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

If Python 3.13 was unavailable, replace only this line:

```text
- Windows Python 3.13 targeted stress: 200/200 PASS
```

with:

```text
- Windows Python 3.13 targeted stress: UNAVAILABLE
```

Do not change a failed validation into `UNAVAILABLE`.

- [ ] **Step 4: Keep #80 open until exact-PR-HEAD review remains clean**

Before merge, run:

```powershell
py -3.11 -m pytest -q tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence
git diff --check origin/main...HEAD
git rev-parse HEAD
```

If the PR HEAD changes after the recorded acceptance run, refresh the Issue #80 evidence for the new HEAD before merge or closure.

---

## Self-Review Mapping

- Windows root-cause evidence: Task 1.
- Explicit stop gate for production-lock defects: Task 1 Step 5.
- Removal of global `os.open` call-count race: Task 2 Steps 1-2.
- Exactly one success and one `FileExistsError`: Task 2 Step 2 assertions.
- Worker termination: Task 2 Step 2 assertions.
- Canonical one-event persistence: Task 2 Step 2 assertions.
- Python 3.11/3.13 200-run requirement: Task 3.
- No retry/skip/sleep masking: Task 3 Step 4.
- Workflow/full/static/documentation regression: Task 4.
- Exact-head Issue evidence and PR linkage: Task 5.

No production code change is authorized by this implementation plan. A proven production-lock defect terminates this plan and requires a new approved design.

## Completion Definition

Issue #80 is implementation-ready for review only when all of the following are true:

1. Task 1 proves `SERIALIZED` critical-section behavior on actual Windows.
2. The final test no longer monkeypatches global `events.os.open` or uses call-count synchronization.
3. Exactly one append succeeds and exactly one conflicting append raises `FileExistsError`.
4. Both workers terminate and exactly one canonical journal event remains.
5. Python 3.11 targeted stress is 200/200 PASS when available.
6. Python 3.13 targeted stress is 200/200 PASS when available, otherwise explicitly `UNAVAILABLE`.
7. Workflow integration, full pytest, Ruff, mypy, compileall, and documentation integrity are recorded for the exact final HEAD.
8. Issue #80 contains the trace-backed root-cause summary and exact verification evidence.
9. The focused PR links `Fixes #80` and contains no unauthorized production-lock change.
