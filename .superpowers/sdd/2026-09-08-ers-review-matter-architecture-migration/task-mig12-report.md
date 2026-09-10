# MIG-12 / Issue #182 — ReviewMatter application service and CLI report

## Scope and authority

Base SHA: `b766707`; branch: `feat/mig-12-review-matter-cli`.

`ReviewMatterService` is the sole application boundary for Matter mutations.
The CLI only parses arguments, invokes the service, and emits canonical JSON.
It uses the explicitly supplied, trust-validated workspace and only fixed,
repository-defined children: `matter.sqlite` and `evidence/evidence.sqlite`.
It neither searches for a workspace nor accepts caller-provided authority
hashes or timestamps.

The deliberate scope expansion is recorded in the ledger:
`projection.py` now supports the append-only `ISSUE_ADDED` event required for
`add-issue`. No Matter schema, evidence authority, Formal Run, Track A/B,
finalizer, Workbench, or Human Decision behavior changed.

## Delivered behavior

- `review-matter create/status/add-issue/bind-evidence/search/select-evidence/formalize`
  is available through the canonical dispatcher.
- Every existing-Matter mutation requires an expected revision and uses the
  existing atomic Matter event/projection compare-and-swap path. A stale
  revision reports `MATTER_REVISION_CONFLICT` with no event or projection write.
- Navigation remains read-only until `select-evidence`, which re-runs the
  bounded navigation request and promotes only its current, exact hit.
- `formalize` freezes the exact Matter revision into a persisted immutable
  `FormalizationSnapshot`, then delegates to the existing formal-review
  preparation boundary. Its CLI response keeps mutable Matter revision separate
  from snapshot and run identities.
- Existing `review-question` and `review-run` command regressions continue to
  pass.

## TDD and verification

The focused RED command initially failed only because `review-matter` was not a
known command (2 failures in 0.96s). The initial sandboxed pytest invocation
could not create its temporary root due to Windows ACLs; it was rerun in a
fresh elevated temp base and was not treated as functional RED evidence.

Focused GREEN: 2 passed in 1.33s. Adjacent Matter/navigation/formal CLI:
183 passed in 45.84s. Full Python 3.13 pytest at implementation candidate
`1d44346ef3e21e8a3a11a6e3fbeee4dc35b5fa9f`: 2097 passed, 1 skipped in
391.20s.

Ruff, mypy (`src`), mypy (`--platform win32 src`), compileall, source-tree
documentation validation (50 documents, 0 errors, 145 warnings), and
`git diff --check` passed at that candidate.

## Fix round

The RED fix-round tests reproduced two independent blockers: every
existing-Matter operation could fall through to MatterStore's create-on-open
behavior, and navigation sidecar trust raised `RuntimeError` beyond the
ReviewMatter CLI handler. The implementation now separates create-only from
existing-file-only store resolution, validates Matter existence before
evidence/navigation work, and maps navigation authority `RuntimeError` to the
stable CLI failure path.

Fix-round RED: 8 failed and 2 passed in 2.22s. Fix-round GREEN: 11 passed in
3.04s. Adjacent Matter/navigation/formal CLI regressions: 192 passed in
45.15s.

Fix-round exact-head verification at implementation commit
`2f6af66e2353a68a63d988abf8f8c265a750b0ba`:

- Focused CLI flow: 11 passed in 2.02s.
- Adjacent Matter/navigation/formal CLI regressions: 192 passed in 45.80s.
- Full Python 3.13 pytest: 2106 passed, 1 skipped in 377.81s.
- Ruff: PASS.
- mypy `src`: PASS, 260 source files.
- mypy `--platform win32 src`: PASS, 260 source files.
- compileall (`src scripts web_runtime tests`): PASS.
- Source-tree documentation validation: PASS, 50 documents, 0 errors, 145
  warnings.
- `git diff --check`: PASS.

The first documentation invocation selected an unrelated installed checkout and
returned `SOURCE_MISMATCH`; the source-tree invocation with this worktree's
`src` on `PYTHONPATH` passed and is the recorded gate result.

## Fix round 2

Sol-high review identified two further service-boundary gaps. `create` validated
the Matter identity only after opening the create-capable store, and `add-issue`
validated dependencies against a synthetic Matter containing only the candidate
issue. The fix validates all create inputs before store creation, rejects
self-dependency, and validates the candidate with the actual current Matter so
existing dependency IDs and source/formal lineage remain intact.

Fix-round-2 RED: 3 failed and 11 passed in 3.68s. GREEN: 14 passed in 3.22s.
The exact code candidate was
`9afa848e3dcc667c0f207fe98e2efa6e571d0998`; focused verification passed 14 in
2.32s and adjacent Matter/navigation/formal verification passed 195 in 47.94s.

Exact Python 3.13 verification at `9afa848e3dcc667c0f207fe98e2efa6e571d0998`:

- Full pytest: 2109 passed, 1 skipped in 372.33s.
- Ruff: PASS.
- mypy `src`: PASS, 260 source files.
- mypy `--platform win32 src`: PASS, 260 source files.
- compileall (`src scripts web_runtime tests`): PASS.
- Source-tree documentation validation: PASS, 50 documents, 0 errors, 145
  warnings.
- `git diff --check`: PASS.

## Fix round 3

Sol-high review found that `CASE-*` Matter IDs were rejected only by the
canonical Matter decoder after `create()` had already opened the create-capable
store. The focused RED regression reproduced the leak. The service now imports
and uses the canonical Matter contract identifier rule before any store
creation, preserving valid Matter IDs and all prior behavior.

Fix-round-3 RED: 1 failed and 14 passed in 2.62s. GREEN: 15 passed in 2.32s.
Adjacent Matter/navigation/formal regressions passed 196 in 45.23s before the
code commit. The exact verified code head is
`baf1bf8a57c789ae4f61aef5a241fb6dc6d3af44`; its focused verification passed 15
in 2.25s and adjacent verification passed 196 in 47.54s.

Exact Python 3.13 verification at
`baf1bf8a57c789ae4f61aef5a241fb6dc6d3af44`:

- Full pytest: 2110 passed, 1 skipped in 393.66s.
- Ruff: PASS.
- mypy `src`: PASS, 260 source files.
- mypy `--platform win32 src`: PASS, 260 source files.
- compileall (`src scripts web_runtime tests`): PASS.
- Source-tree documentation validation: PASS, 50 documents, 0 errors, 145
  warnings.
- `git diff --check`: PASS.

The initial code commit `b0fe527` passed the full suite but required a
formatting-only import-order follow-up; all exact final statuses above are at
`baf1bf8`.

## Not run

- Browser/manual acceptance: `NOT_RUN`.
- GitHub Actions: `ACTIONS_NOT_RUN`.
- Independent gpt-5.6-sol-high review: PASS/APPROVED; no Critical, Important,
  or Minor findings.
- Push, remote SHA parity, PR, merge, and Issue #182 closure: `NOT_RUN`.
