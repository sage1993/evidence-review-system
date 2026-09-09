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

## Round-1 takeover result — 2026-09-10

- `bind_formal_run()` now requires a workspace root, verifies the run-local
  finalized packet through `verify_finalized_run()`, validates canonical
  request/RUN and Track-A-bundle identity, and proves the request's snapshot,
  Matter ID, and Matter revision before appending lineage.
- Current review now resolves workspace-scoped runs through an explicit
  workspace root while the repository pointer remains restricted to its
  canonical run ID and packet SHA fields.
- MatterStore now rejects any extra unique formal-run-binding index after a
  persisted restart; required v3 constraints remain accepted.
- TDD RED: nonexistent/invented RUN was accepted, an extra
  `UNIQUE(matter_id)` index was accepted, and current-review lacked the
  separate-workspace API. GREEN: focused suite PASS (19), adjacent suite PASS
  (145), full Python 3.13 pytest PASS (2,054 passed, 1 skipped), Ruff PASS,
  mypy POSIX/Win32 PASS, compileall PASS, and source-tree documentation
  integrity PASS (0 errors, 145 warnings).
- Standard documentation CLI invocation is `SOURCE_MISMATCH` because the
  installed executable points to `F:\2026-PJ\evidence-review-system`; source
  validation of this worktree passed. Browser/manual acceptance remains
  `NOT_RUN`; GitHub Actions remains `ACTIONS_NOT_RUN`.
