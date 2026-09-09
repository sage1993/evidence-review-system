# Issue #181 / MIG-11 implementation report

## Scope

`SCOPE_EXPANSION_REQUIRED = YES` is recorded in `progress.md`.  The expansion
is limited to the MatterStore v3 schema migration/validation and its existing
schema regression coverage, plus this required SDD record.  No drawing, visual,
protected-viewer, service, or UI paths changed.

## Implemented boundary

- `formal_run_bindings` is an append-only Matter-store table keyed by
  `(matter_id, snapshot_id)` with a unique RUN ID, persisted Matter revision,
  exact packet SHA-256, restrictive foreign keys, and deterministic listing.
- `bind_formal_run()` loads and verifies the immutable FormalizationSnapshot
  before insertion; duplicate or conflicting identities are rejected.
- `.ers/current-review.json` contains only its versioned format, exact RUN ID,
  and packet SHA-256.  Bind validates the selected run before replacing the
  pointer.  Resolution rejects missing, unsafe, malformed, noncanonical,
  stale, or hash-mismatched state, and re-verifies the canonical run-local
  packet through `verify_finalized_run()`.
- No workspace-global `final-review-packet.json` is created.  Resolved packets
  remain machine packets with `human_decision is None`; a prior run decision is
  neither copied nor projected.

## TDD evidence

The initial focused RED command collected only the expected missing-module
failures for `evidence_review.current_review_binding` and
`evidence_review.review_matter.formal_run_binding`; no host failure occurred.
Focused GREEN: 16 passed, including pointer canonicality/path safety, stale and
hash mismatch rejection, two-run lineage, duplicate/conflict rejection, and
the v2-to-v3 schema upgrade.

## Verification recorded before commit

| Gate | Result |
| --- | --- |
| Focused Matter/current-review/store pytest | PASS — 16 passed |
| Adjacent formalization and review-run pytest | PASS — 63 passed |
| Full Python 3.13 pytest | PASS — 2,052 collected tests |
| Ruff | PASS |
| mypy `src` | PASS — 258 files |
| mypy `--platform win32 src` | PASS — 258 files |
| compileall | PASS |
| Documentation integrity | PASS — errors=0, warnings=145 |
| `git diff --check` | PASS |

Python: `3.13.14`.

## Not run

- Browser/manual acceptance: NOT_RUN.
- GitHub Actions: `ACTIONS_NOT_RUN`.
- Push, pull request, merge, and issue closure: intentionally NOT_RUN per task
  authority.
