# Issue #80: Deterministic Windows Event-Journal Concurrency Test Design

## Status

Approved design for Issue #80: `test: investigate intermittent Windows event-journal concurrency test`.

Base main commit at design start: `659f934d100000ad7042b58bafefa22bf6076f7d`.

## Problem statement

`tests/integration/workflow/test_event_journal.py::test_concurrent_events_cannot_publish_two_events_for_one_sequence` is intermittent on Windows. The observed failure expects exactly one `FileExistsError` from two concurrent, conflicting sequence-1 appends, but sometimes records zero `FileExistsError` outcomes.

The production invariant is stronger than the exception shape alone:

1. Two conflicting events for the same sequence must never both publish.
2. Exactly one contender may publish.
3. The losing contender must observe an immutable sequence conflict rather than silently succeed.
4. The journal must remain canonical and loadable with exactly one event.

The issue is therefore a flaky-test investigation first, not an assumption that production locking is defective.

## Current implementation context

`append_workflow_event()` creates the events directory, enters `_journal_lock(events_dir)`, reloads the journal while holding that lock, validates the next sequence, and finally creates the event file with `os.O_CREAT | os.O_EXCL`.

`_journal_lock()` itself opens a sibling lock file with `os.open()` before acquiring the platform lock (`msvcrt.locking` on Windows, `fcntl.flock` elsewhere).

The current test monkeypatches `events.os.open` globally and blocks the first two calls on a `threading.Barrier`. This couples the test to low-level call order. Because the lock file is opened before the event file, the first two intercepted `os.open()` calls can be the two lock-file opens rather than the two event-file create attempts. The test may therefore synchronize at a point different from the safety property it intends to exercise.

This is the leading hypothesis, not yet the accepted root cause. A Windows trace must confirm it.

## Goals

- Identify the actual Windows scheduling/locking path that produces the intermittent result.
- Preserve the event-journal production safety invariant.
- Replace call-count-based race orchestration with deterministic synchronization tied to the journal-lock boundary or another explicit state transition.
- Keep product-code changes out of scope unless the investigation demonstrates a real locking defect.
- Verify repeatedly on Windows Python 3.11 and Python 3.13.
- Record exact commands, environment, commit SHA, retry counts, and full-suite results in Issue #80.

## Non-goals

- Do not hide the failure with `xfail`, Windows-specific skip markers, sleeps, or retry plugins.
- Do not weaken the assertion to only `len(load_workflow_events(root)) == 1`.
- Do not increase timeouts as the primary fix.
- Do not replace `msvcrt.locking` or redesign journal persistence without evidence that the production lock is defective.
- Do not add unrelated workflow refactors.

## Investigation design

### Phase 1: Capture the failing interleaving

Add temporary test-only instrumentation around the concurrency probe. For each contender, capture ordered checkpoints using `time.monotonic_ns()` and `threading.get_ident()`:

- append entry
- lock-file open before/after
- lock acquire before/after
- journal reload and observed event count
- target event-file open before/after
- success or exception
- lock release
- thread completion

Also record the path and relevant `os.open` flags for intercepted calls.

The diagnostic output must be emitted only when the targeted probe fails or when running an explicit investigation helper; it must not become production logging.

### Phase 2: Classify the failure

Use the trace to distinguish these cases:

1. **Serialized critical sections, wrong test synchronization**
   - Only one thread holds the journal lock at a time.
   - The second contender enters after the first commit.
   - The test barrier is shown to synchronize lock-file opens rather than the intended journal state.
   - Action: fix the test only.

2. **Serialized critical sections, timeout/orchestration failure**
   - The second contender is still waiting or has not completed when assertions run.
   - Action: make test completion explicit and deterministic; do not merely extend timeout constants.

3. **Concurrent critical-section entry**
   - Both contenders are observed beyond lock acquisition at the same time.
   - Action: treat as a production locking defect and investigate `_journal_lock()` before changing the test expectation.

4. **Unexpected exception path**
   - The loser raises an exception other than `FileExistsError`.
   - Action: trace that exact exception to its source before proposing a fix.

The investigation is complete only when one case is supported by the trace.

## Preferred test design if production locking is sound

Remove synchronization based on `open_calls <= 2`.

Instead, make the test synchronize on an explicit lock-acquisition boundary. The test must ensure both contenders are ready to compete, then release them into the real journal-lock path without replacing the production lock semantics.

The exact hook should be the narrowest existing boundary that can be controlled from the test. Prefer a test-local wrapper around `_journal_lock` or a similarly explicit boundary over monkeypatching all `os.open` calls.

Conceptual sequence:

1. Thread A and Thread B both reach a pre-lock rendezvous.
2. The rendezvous releases both contenders.
3. The real `_journal_lock` selects one winner.
4. The winner loads an empty journal, validates sequence 1, and persists its event.
5. The loser acquires the lock afterward and reloads the now-nonempty journal.
6. The loser detects that sequence 1 already contains different bytes and raises `FileExistsError`.
7. Both threads terminate.
8. The journal loads successfully with one canonical event.

The test must not depend on which contender wins.

## Required assertions

The final deterministic test must verify all of the following:

- exactly two outcomes are recorded;
- exactly one outcome is success;
- exactly one outcome is `FileExistsError`;
- no worker thread remains alive after completion;
- the journal contains exactly one event;
- the persisted event has sequence `1`;
- the event directory contains exactly one canonical event JSON file;
- `load_workflow_events(root)` succeeds after the race;
- the winning event is one of the two supplied contenders, with no hybrid/corrupt bytes.

The test may not accept two successes, an arbitrary second exception, or an unfinished worker as a passing result.

## Production-code decision gate

### If the trace confirms a test defect

Expected implementation scope:

- `tests/integration/workflow/test_event_journal.py`
- optional test-only helper local to the same test module if it improves readability

Do not modify `src/ansim_review/workflow/events.py`.

### If the trace confirms a production locking defect

Stop before implementation and document the exact demonstrated defect. Then design the smallest production change that restores serialization across both threads and processes.

Potential mechanisms such as an in-process `threading.Lock`, per-path lock registry, or replacing the Windows lock API are not pre-approved. They require evidence and a separate design decision because they change persistence semantics.

## Verification strategy

### Targeted reproduction before the fix

On actual Windows, reproduce the current behavior sufficiently to capture at least one failing interleaving, or document a bounded stress run if the failure cannot be reproduced after instrumentation.

Record:

- Windows version
- Python version
- pytest version
- exact HEAD
- command
- pass/fail count
- trace for any failure

### Targeted stress after the fix

Run the single concurrency test repeatedly without adding a retry dependency.

Required minimum:

- Windows Python 3.11: 200 consecutive passes
- Windows Python 3.13: 200 consecutive passes

A single failure resets the acceptance run and returns the work to investigation.

### Regression suites

For both Python 3.11 and Python 3.13 where available:

1. `tests/integration/workflow/test_event_journal.py`
2. `tests/integration/workflow/`
3. full `pytest`

Also run repository static gates:

- Ruff
- mypy
- compileall
- documentation integrity validation if it remains part of the repository acceptance process

GitHub Actions results must be reported accurately. If Actions do not receive a runner, record that as unavailable rather than as PASS or test failure.

## Acceptance criteria mapping

Issue #80 acceptance criteria are satisfied when:

1. **Windows/filesystem scheduling condition identified**
   - Supported by recorded checkpoint trace, not inference alone.

2. **Test deterministic without weakening safety assertion**
   - No call-count race orchestration, sleeps, skips, xfail, or retry masking.
   - Exactly one success and one immutable conflict remain mandatory.

3. **Repeated Windows verification**
   - Python 3.11: 200/200 targeted passes.
   - Python 3.13: 200/200 targeted passes where the environment is available.

4. **Repository regression verification**
   - Targeted, workflow integration, and full-suite results recorded.
   - Static gates recorded.

5. **Issue evidence**
   - Exact tested commit SHA and all commands/results posted to Issue #80 before closure.

## Implementation sequence

1. Create an isolated Issue #80 branch/worktree from the current main baseline.
2. Reproduce and instrument the existing flaky test without changing production semantics.
3. Confirm one root-cause classification from the trace.
4. Write or adjust the minimal failing test that deterministically represents that root cause.
5. Implement one fix only.
6. Run the 200-iteration Windows Python 3.11 stress test.
7. Run the 200-iteration Windows Python 3.13 stress test.
8. Run regression and static gates.
9. Post exact verification evidence to Issue #80.
10. Open a focused PR linked with `Fixes #80` only after the evidence is complete.

## Risks and mitigations

### Risk: test hook changes the locking behavior being tested

Mitigation: synchronize immediately before the real lock boundary and keep the actual `_journal_lock` implementation in the exercised path.

### Risk: thread completion remains scheduler-dependent

Mitigation: use explicit synchronization and assert worker termination. Timeouts remain deadlock guards, not correctness mechanisms.

### Risk: test passes while loser fails for the wrong reason

Mitigation: require exactly one `FileExistsError` and reject all other loser outcomes.

### Risk: apparent test defect masks a real Windows lock bug

Mitigation: no test-only fix is accepted until the trace proves serialized critical-section entry on Windows.

## Final design decision

Proceed with the **investigate-first, test-only-if-proven** approach.

The leading hypothesis is that the existing test synchronizes the first two global `os.open()` calls, which are likely the lock-file opens rather than the event-file publish attempts. This hypothesis must be confirmed on Windows before implementation. Production journal code remains unchanged unless the trace demonstrates a real lock defect.
