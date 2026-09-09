# Issue #181 / MIG-11 round-1 fix report

## Scope

The recorded `SCOPE_EXPANSION_REQUIRED = YES` remains limited to
`review_matter/store.py`, its schema regression coverage, and this SDD record.
No drawing, visual, viewer, service, or UI path changed.

## Implemented authority fixes

- `bind_formal_run()` now requires an explicit workspace root and authenticates
  the requested run from its run-local artifacts. It calls
  `verify_finalized_run()`, checks the canonical final packet hash, recomputes
  the canonical request/run identity, rebuilds the Track A bundle, and requires
  the request's `formalization_snapshot_id`, Matter ID, and Matter revision to
  match the persisted supplied snapshot.
- Formal lineage now rejects nonexistent RUN IDs, invented packet hashes,
  unrelated direct-review RUNs, wrong snapshot or Matter lineage, and missing
  packets before any Matter-store write. Listing also revalidates the same
  run-local authority.
- Current-review bind/resolve takes an explicit workspace root. The
  repository-local pointer remains canonical control state containing only the
  versioned format, exact `run_id`, and exact packet SHA-256; it stores no
  workspace path and does not recreate a global packet.
- MatterStore requires the exact two unique constraints for
  `formal_run_bindings`; any extra unique index, including
  `UNIQUE(matter_id)`, fails closed after restart.

## TDD evidence

The round-1 RED command ran the three new focused regressions before production
changes. It failed as intended:

- nonexistent RUN/invented hash: `Failed: DID NOT RAISE ValueError`;
- extra unique Matter constraint: `Failed: DID NOT RAISE MatterSchemaError`;
- separate repository/workspace roots: missing `workspace_root` API
  (`TypeError`).

The first sandboxed attempts could not complete pytest teardown because their
temporary roots inherited a Windows ACL that denied directory enumeration. The
same RED command was then run in a fresh system-temporary root outside the
sandbox and produced the failures above. All subsequent pytest runs used fresh
system-temporary roots and the generated directories were removed afterward.

## Verification

| Gate | Result |
| --- | --- |
| Focused Matter/current-review/store pytest | PASS — 19 passed |
| Focused Ruff | PASS — all checks passed |
| Adjacent Matter/formalization/review-run/finalizer pytest | PASS — 145 passed |
| Full Python 3.13 pytest | PASS — 2,054 passed, 1 skipped in 359.40s |
| Ruff `src tests web_runtime` | PASS — all checks passed |
| mypy `src` | PASS — 258 source files |
| mypy `--platform win32 src` | PASS — 258 source files |
| compileall `src scripts web_runtime tests` | PASS |
| Documentation integrity | PASS — errors=0, warnings=145 |
| `git diff --check` before report update | PASS |

Python: `3.13.14`.

The normal documentation command first returned `SOURCE_MISMATCH`: the
installed `evidence-review.exe` imports a different checkout at
`F:\2026-PJ\evidence-review-system`. The same repository-root validation was
therefore rerun against this candidate's `src` tree, with output created under
the ignored `.acceptance/` directory; it passed as recorded above.

## Not run / unresolved

- Browser/manual acceptance: NOT_RUN.
- GitHub Actions: `ACTIONS_NOT_RUN`.
- Push, pull request creation, merge, and issue closure: NOT_RUN by request.
- The installed CLI provenance mismatch is an environment condition, not a
  candidate source failure; the normal executable gate cannot be claimed until
  that external installation points to this worktree.
