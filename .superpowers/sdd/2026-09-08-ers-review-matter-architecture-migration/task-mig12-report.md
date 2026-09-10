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
45.15s. Final exact-head gates will be recorded after the implementation and
this report/ledger update are committed.

## Not run

- Browser/manual acceptance: `NOT_RUN`.
- GitHub Actions: `ACTIONS_NOT_RUN`.
- Independent gpt-5.6-sol-high review: `NOT_RUN`.
- Push, remote SHA parity, PR, merge, and Issue #182 closure: `NOT_RUN`.
