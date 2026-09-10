# Issue #181 / MIG-11 fix-round-2 report

## Scope

The recorded `SCOPE_EXPANSION_REQUIRED = YES` remains limited to
`review_matter/store.py`, its schema regression coverage, and this SDD record.
No drawing, visual, viewer, service, or UI path changed.

## Implemented authority fixes

- `bind_formal_run()` now requires an explicit workspace root and authenticates
  the requested run from its run-local artifacts. It calls
  `verify_finalized_run()`, checks the canonical final packet hash, recomputes
  the canonical request/RUN identity, rebuilds the Track A bundle, and compares
  the complete canonical request reconstructed from the persisted snapshot,
  review scope, selected evidence, and finalized evidence provenance. The
  request's self-declared identity fields are not treated as authentication.
- Formal lineage now rejects nonexistent RUN IDs, invented packet hashes,
  unrelated direct-review RUNs even when they copy the three snapshot/Matter
  identity fields, wrong snapshot or Matter lineage, and missing packets before
  any Matter-store write. Listing also revalidates the same run-local authority.
- Current-review bind/resolve takes an explicit workspace root. The
  repository-local pointer remains canonical control state containing only the
  versioned format, exact `run_id`, and exact packet SHA-256; it stores no
  workspace path and does not recreate a global packet. Both bind and resolve
  verify the run-local request's canonical bytes and derived RUN ID in addition
  to the manifest-bound final packet.
- MatterStore requires the exact two unique constraints for
  `formal_run_bindings`; any extra unique index, including partial indexes and
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

The round-2 RED command covered the three new regressions and failed as
intended: the copied-identity direct run, tampered request, and partial unique
index were each accepted by the pre-fix candidate. After the changes, the same
three tests passed in 1.44s. The focused and adjacent candidate suite passed 62
tests.

## Verification

| Gate | Result |
| --- | --- |
| Round-2 regression pytest | PASS — 3 passed in 1.44s |
| Focused/adjacent Matter/current-review/formalization/store pytest | PASS — 62 passed in 20.13s |
| Full Python 3.13 pytest | PASS — 2,056 passed, 1 skipped in 410.89s |
| Ruff `src tests web_runtime` | PASS — all checks passed |
| mypy `src` | PASS — 258 source files |
| mypy `--platform win32 src` | PASS — 258 source files |
| compileall `src scripts web_runtime tests` | PASS |
| Source-tree documentation integrity | PASS — 50 documents, errors=0, warnings=145 |
| `git diff --check` | PASS — final pre-commit check |

Python: `3.13.14`.

The normal documentation command first returned `SOURCE_MISMATCH`: the
installed `evidence-review.exe` imports a different checkout at
`F:\2026-PJ\evidence-review-system`. The same repository-root validation was
therefore rerun against this candidate's `src` tree, with output created under
the ignored `.acceptance/` directory; it passed as recorded above.

The previous round's report described the three copied request identity fields
and non-partial extra-index check as sufficient. That description is superseded
by this round: full snapshot-derived request equality and rejection of partial
unique indexes are now covered and verified.

## Not run / unresolved

- Browser/manual acceptance: NOT_RUN.
- GitHub Actions: `ACTIONS_NOT_RUN`.
- Push, pull request creation, merge, and issue closure: NOT_RUN by request.
- The installed CLI provenance mismatch is an environment condition, not a
  candidate source failure; the normal executable gate cannot be claimed until
  that external installation points to this worktree.
