# SDD ledger — MIG-11 / Issue #181

## Preflight

| Interface | Producer / consumer | Ruling |
| --- | --- | --- |
| MIG-10 Formal RUN identity → MIG-11 lineage | FormalizationSnapshot and finalized RUN identity are immutable inputs to Matter history. | Preserve exact snapshot ID, RUN ID, packet SHA, and Matter ID; do not derive authority from planner or draft state. |
| #157 run-local packet → current-review pointer | The pointer is a convenience selector, not a replacement packet authority. | Bind exact `run_id` + packet SHA and resolve only after verifying the run-local packet and canonical finalized-run authority. |
| Human Decision → new RUN | Existing decisions are packet-hash/run scoped. | Never copy or project a prior decision when resolving a new current review. |
| Matter schema → append-only history | One Matter can have multiple formal runs. | Add append-only lineage storage with deterministic ordering and duplicate/conflict rejection. |

## Acceptance checklist

- [x] Focused RED reproduces missing lineage/pointer contract without unrelated host failure
- [x] Two formal runs bind and list without overwrite/delete
- [x] Current pointer canonical bind/resolve works
- [x] Missing/stale/malformed/hash-mismatch pointer fails closed
- [x] Prior Human Decision is not reused
- [x] #157 regression passes
- [x] Focused/adjacent/static/full exact-head gates pass
- [ ] Feature branch pushed with remote SHA parity
- [ ] PR reviewed with gpt-5.6-sol-high and merged
- [ ] Issue #181 closed and post-merge ancestry verified

## Scope control

- `SCOPE_EXPANSION_REQUIRED = YES` — `MatterStore` owns schema-version migration
  and fail-closed table validation, so MIG-11 must update
  `src/evidence_review/review_matter/store.py` and its existing schema regression
  coverage. The required SDD completion report also updates this ledger directory.
- Do not modify drawing/visual, protected viewer, or ReviewMatter service/UI paths in MIG-11.

## Initial sol-high review — round 1 required

- Candidate `cb14692e404f7cdd438566a14ad352bf33cd2c69` → `155bbc4136f034d17b3b2e64029f57a30de33a67` was reviewed with verdict: spec compliance FAIL; task quality NOT APPROVED.
- Critical: `bind_formal_run()` accepts unrelated/nonexistent RUN IDs and invented packet hashes because it does not invoke canonical finalized-run verification or prove the RUN request's snapshot/Matter lineage.
- Important: current-review resolution hardcodes `repository_root/runs` while actual RUNs are workspace-scoped; separate repository/workspace roots reject valid runs.
- Important: MatterStore schema validation accepts extra unique indexes such as `UNIQUE(matter_id)`, which can block the required second run.
- Ruling: do not push/PR. Fix all three authority/migration defects and add realistic finalized-run, separate-root, and malformed-constraint regression tests. Full gates must be rerun at the final candidate.

## Fix round 1 result — round 2 required

- Candidate commit: `5daf7e8db3cfb323d4faa5466e942df99029646e`.
- Review confirmed the prior RUN authentication, separate-root pointer path, and ordinary extra-index tests, but found three remaining blockers: incomplete snapshot request/provenance comparison, request tamper not checked during pointer resolve, and partial unique indexes accepted by schema validation.
- Ruling: resume the same terra implementer for round 2; no push/PR until all three fail-closed regressions and exact-head gates pass.

## Fix round 2 result — round 3 required

- Candidate commit: `73d9652821e2ed5c82a0026f3eb4659d692d3e5c`.
- Review confirmed complete snapshot-derived request authentication, request tamper detection, and partial-index detection for a new signature.
- Remaining blocker: unique-index validation still discards partial semantics and multiplicity, allowing a partial replacement or redundant partial index matching an allowed signature.
- Ruling: fix exact unique-index semantics and add replacement/duplicate partial-index restart regressions; no push/PR until final sol-high review passes.

## Fix round 3 result — round 4 required

- Candidate commit: `5949ce55e5da3d25ca62ef1b5a9bfd5dfae69c71`.
- Review confirmed exact unique-index semantics and partial replacement/duplicate regressions, and prior lineage/pointer blockers appeared fixed.
- Remaining blockers: confidence-input is not compared to the request-derived deterministic value, and Track A bundle derivation is not cross-checked against the request; both can be tampered while updating manifest/packet hashes.
- Ruling: resume the same terra implementer for round 4; no push/PR until shared cross-artifact validation and regressions pass final review.

## Fix round 4 result — round 5 required

- Candidate commit: `d621d326edd04b4d221e4c83f921817d77fdb1eb`.
- Review confirmed request/Track A/confidence/packet cross-artifact tamper checks, but found two remaining authority blockers: current-review resolution still does not authenticate the request against MatterStore/FormalizationSnapshot lineage, and schema validation still accepts altered SQLite `ON CONFLICT` policies.
- The review also found that exact-head gate claims need to be regenerated/recorded after the final code commit rather than relying on earlier artifacts.
- Ruling: fix current-review Matter lineage authentication and exact schema conflict-policy validation in round 5; rerun and record final gates after the final candidate is committed.

## Fix round 4 result — 2026-09-10

- The shared finalized-run validator now verifies the canonical request and
  derived RUN ID, rebuilds and byte-compares the complete request-derived Track
  A bundle, and byte-compares the complete request-derived confidence input.
  Formal binding adds the complete persisted Matter-snapshot request
  comparison; current-review bind and resolve use the same shared validator.
- TDD RED reproduced both review blockers: refreshed manifest/packet bytes could
  carry a changed confidence input, and current review accepted a packet-
  irrelevant Track A bundle input. GREEN passed both regressions in 1.15s.
- Focused/adjacent pytest passed 53 tests in 18.65s. Exact full Python 3.13
  pytest passed 2,060 tests with 1 skipped in 370.60s. Ruff, mypy POSIX/Win32,
  compileall, source-tree documentation validation, and diff check passed.
- Source-tree documentation validation reported 50 documents, 0 errors, and
  145 warnings. The installed documentation executable remains
  `SOURCE_MISMATCH` because it points to `F:\2026-PJ\evidence-review-system`.
  Browser/manual acceptance remains `NOT_RUN`; GitHub Actions remains
  `ACTIONS_NOT_RUN`.
- This round does not alter the pointer shape, append-only lineage, MatterStore
  schema validation, finalizer authority, or any drawing/visual/viewer/service/
  UI path.

## Round-1 takeover result — 2026-09-10 (superseded)

- The first takeover implementation addressed the initial three review findings,
  but its snapshot authentication compared only three request fields and its
  schema check excluded partial indexes. The final review correctly kept this
  candidate open for another fix round.

## Fix-round-2 result — 2026-09-10 (superseded)

- `bind_formal_run()` now compares the complete canonical request reconstructed
  from the persisted `FormalizationSnapshot`, review scope, selected evidence,
  and finalized evidence provenance. A realistic finalized direct run that
  copies `formalization_snapshot_id`, `matter_id`, and `matter_revision` while
  changing question/evidence/provenance fails closed.
- Current-review bind and resolve share the canonical run-local request/RUN
  verifier in addition to final-packet verification. The pointer remains
  limited to exact `run_id` and packet SHA, and separate repository/workspace
  roots remain supported.
- MatterStore rejected unexpected column signatures, including a new partial
  signature, but still discarded partial semantics and multiplicity. The final
  review kept the candidate open for fix round 3.
- TDD RED reproduced all three blockers; GREEN passed the three regressions in
  1.44s. Focused/adjacent pytest passed 62 tests; exact full Python 3.13
  pytest passed 2,056 with 1 skipped in 410.89s. Ruff, mypy POSIX/Win32,
  compileall, source-tree documentation validation, and final diff check passed.
- Source-tree documentation validation reported 50 documents, 0 errors, and
  145 warnings. The installed documentation executable remains
  `SOURCE_MISMATCH` because it points to `F:\2026-PJ\evidence-review-system`.
  Browser/manual acceptance remains `NOT_RUN`; GitHub Actions remains
  `ACTIONS_NOT_RUN`.

## Fix-round-3 result — 2026-09-10

- MatterStore now validates the exact required unique-index descriptors for
  `formal_run_bindings`: uniqueness, origin (`pk`/`u`), non-partial status,
  ordered columns, and exact multiplicity. Partial replacements and redundant
  partial duplicates now fail closed after restart; normal v3 and v2-to-v3
  migration remain accepted.
- TDD RED reproduced both remaining blockers: partial replacement and redundant
  partial duplicate were accepted. GREEN passed five schema/migration checks in
  0.61s. Focused/adjacent pytest passed 64 tests; exact full Python 3.13
  pytest passed 2,058 with 1 skipped in 370.95s. Ruff, mypy POSIX/Win32,
  compileall, source-tree documentation validation, and final diff check passed.
- Source-tree documentation validation reported 50 documents, 0 errors, and
  145 warnings. The installed documentation executable remains
  `SOURCE_MISMATCH` because it points to `F:\2026-PJ\evidence-review-system`.
  Browser/manual acceptance remains `NOT_RUN`; GitHub Actions remains
  `ACTIONS_NOT_RUN`.

## Fix-round-5 result — 2026-09-10

- `f03f07c` adds one shared formal-run authority validator for formal binding
  and current-review bind/resolve. Declared Matter identity is now resolved
  from the workspace `matter.sqlite` and persisted `FormalizationSnapshot`,
  then the complete snapshot-derived request is compared; copied or invented
  request identity cannot authenticate a RUN. Direct runs with no Matter claim
  retain the existing lower-level current-review selector behavior.
- MatterStore now validates the canonical table SQL constraint syntax and
  rejects every explicit non-default SQLite conflict policy (`IGNORE`,
  `REPLACE`, `FAIL`, and `ROLLBACK`) on either required lineage constraint,
  while retaining exact unique-index semantics and v2-to-v3 migration support.
- TDD RED reproduced the invented Matter declaration and all eight altered
  conflict-policy cases; GREEN passed 9 regressions in 1.28s. A positive
  correctly-bound formal current-review regression passed with separate roots;
  focused/adjacent pytest passed 76 tests in 20.23s.
- Exact full Python 3.13 pytest was rerun after `f03f07c`: 2,070 passed, 1
  skipped, 2,071 collected, in 364.54s. Ruff, mypy POSIX/Win32, and compileall
  passed at the same SHA. Source-tree documentation validation passed with 50
  documents, 0 errors, and 145 warnings. The installed documentation
  executable remains `SOURCE_MISMATCH` because it points to
  `F:\2026-PJ\evidence-review-system`.
- Browser/manual acceptance remains `NOT_RUN`; GitHub Actions remains
  `ACTIONS_NOT_RUN`. No drawing, visual, viewer, service, or UI path changed.

## Fix round 6 result

- Round-5 implementation/verification was at `f03f07c`; the later report/ledger
  commit was `b8a91a1`.
- An exact-head rerun after `b8a91a1` passed the full Python 3.13 suite:
  `2070 passed, 1 skipped` in `364.26s`; Ruff, default/win32 mypy, compileall,
  source-tree docs, and diff check also passed. Installed docs remained a
  separate `SOURCE_MISMATCH`.
- Round-6 code/tests are committed at
  `1740d9d5d999347004d760cb805fe7fa787e380a1`. Round-6 regressions passed 10
  tests; focused/adjacent pytest passed 87 tests.
- Round-6 closes comment-obfuscated non-default conflict policies and requires
  the exact persisted Matter lineage tuple before current-review resolution;
  direct non-Matter current-review behavior remains supported.
- Full pytest, Ruff, default/win32 mypy, compileall, source-tree docs, and diff
  check were rerun after the report/ledger record was committed at the final
  exact HEAD. Browser/manual acceptance remains `NOT_RUN`; GitHub Actions
  remains `ACTIONS_NOT_RUN`.
