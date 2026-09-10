# Issue #181 / MIG-11 fix-round-6 report

## Scope

The recorded `SCOPE_EXPANSION_REQUIRED = YES` remains limited to the already
approved MatterStore schema change and its regression coverage. This round also
updates the existing formal-run/current-review authority validators and their
regressions; no drawing, visual, viewer, service, or UI path changed.

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
  now use the same full formal-run authority validator: canonical request bytes
  and derived RUN ID, complete Track A bundle bytes, complete confidence input
  bytes, and the manifest-bound final packet must all agree. When a request
  declares Matter lineage, the validator opens the supplied workspace's
  `matter.sqlite`, loads the declared persisted snapshot, and compares the
  complete request reconstructed from that snapshot. Current-review bind and
  resolve additionally require the exact persisted `formal_run_bindings` tuple
  `(matter_id, snapshot_id, run_id, packet_sha256)`. Invented, incomplete,
  copied, or unpersisted Matter claims therefore fail closed; lower-level direct
  runs with no Matter claim retain their existing selector behavior.
- MatterStore requires the exact two unique constraints for
  `formal_run_bindings`; validation preserves uniqueness, origin, partial
  status, ordered columns, and multiplicity. Any unexpected, duplicate,
  partial, or replacement unique index fails closed after restart. The table
  SQL is comment-stripped and token-normalized before policy validation, so the
  canonical default SQLite `ABORT` conflict policy cannot be bypassed by
  comments, casing, or whitespace; explicit `IGNORE`, `REPLACE`, `FAIL`, or
  `ROLLBACK` policies are rejected.

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

The round-3 RED command demonstrated that the prior column-set comparison
accepted both a partial replacement of the global `run_id` constraint and a
redundant partial `run_id` index. The new exact-index validation rejects both.
The five schema checks covering those cases, the existing extra-index cases,
and v2-to-v3 migration passed in 0.61s.

The round-4 RED command demonstrated that a finalized run with a refreshed
manifest/packet accepted a changed confidence-input artifact, and that current
review accepted a refreshed manifest/packet whose Track A bundle contained an
extra packet-irrelevant input. After the shared validator was added, both
regressions failed closed; the focused/adjacent suite passed 53 tests.

The round-5 RED command demonstrated that current review accepted a
self-consistent finalized RUN declaring invented Matter lineage, and that all
eight persisted schema variants with a non-default conflict policy were
accepted. GREEN passed the nine new checks in 1.28s. A positive regression for
a correctly bound formal RUN also passed, including separate repository and
workspace roots; the current-review regression set passed 9 tests in 1.59s.

The round-6 RED command covered comment-obfuscated `IGNORE`, `REPLACE`, `FAIL`,
and `ROLLBACK` policies on both lineage constraints plus a current-review
binding whose finalized Matter run had no persisted lineage row. It failed as
intended with 10 failures. GREEN passed all 10 regressions in 2.38s; the
focused/adjacent suite passed 87 tests in 23.66s.

## Historical round-5 verification provenance

The implementation and regression commit was `f03f07c`
(`fix(mig-11): authenticate Matter lineage and schema policy`). The exact full
suite and all static gates below were rerun after that code commit.

The later report/ledger commit was `b8a91a1` (`docs(mig-11): record round-5
verification`). After that report/ledger commit, an exact-head rerun at clean
`b8a91a1` confirmed the full Python 3.13 suite at 2,070 passed and 1 skipped in
364.26s. The static, compile, source-tree documentation, and diff checks also
passed at that exact head; the installed documentation command remained a
separate `SOURCE_MISMATCH`.

## Fix-round-6 verification

The round-6 implementation and regression commit is
`1740d9d5d999347004d760cb805fe7fa787e380a1`
(`fix(mig-11): require persisted Matter lineage`). The exact full suite and
all static gates below were run after that code commit. The report/ledger
commit containing this round-6 record was then checked again at its final
exact HEAD; results were unchanged.

## Verification

| Gate | Result |
| --- | --- |
| Round-6 regression pytest | PASS — 10 passed in 2.38s |
| Focused/adjacent Matter/current-review/formalization/finalizer pytest | PASS — 87 passed in 23.66s |
| Full Python 3.13 pytest at `1740d9d` | PASS — 2,080 passed, 1 skipped in 363.92s |
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

This round supersedes the earlier claim that current-review validation stopped
at request/Track A/confidence/packet consistency: it now authenticates declared
Matter lineage from the workspace-persisted snapshot, requires the persisted
lineage tuple, and uses the same full validator as formal binding. It also
supersedes the earlier schema claim by recording comment-obscured conflict
policy rejection in addition to exact unique-index semantics.

## Not run / unresolved

- Browser/manual acceptance: NOT_RUN.
- GitHub Actions: `ACTIONS_NOT_RUN`.
- Push, pull request creation, merge, and issue closure: NOT_RUN by request.
- The installed CLI provenance mismatch is an environment condition, not a
  candidate source failure; the normal executable gate cannot be claimed until
  that external installation points to this worktree.
