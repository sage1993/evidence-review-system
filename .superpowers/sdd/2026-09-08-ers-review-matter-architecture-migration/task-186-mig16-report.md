# Task 186 / MIG-16 fix-round 1 report

## Identity and status

- Base implementation commit: `0a25fd0bdaa2de3127f28e1504821ab3cfc38904`
- Fix-round code commit: `7df379b7ed91be478093c8f37414e265b6db28af`
- Fix-round status: IMPLEMENTED; focused verification PASS; repository acceptance is not claimed.

## Review findings resolved

- Persisted exact `source_revision_id` in the existing event-owned dependency table, with a v3-to-v4 migration that leaves legacy missing identity fail-closed.
- Required revision identity in registration/invalidation APIs and passed persisted before/supplied after revisions to `evaluate_source_change_impact`, so same-hash revision changes stale direct and downstream issues.
- Validated every raw persisted dependency before retention: shape, identifiers, Matter membership, SHA-256, revision identity, duplicate keys, and cross-record identity consistency. Invalid metadata stales all Matter issues.
- Added `ReviewMatterService.invalidate_source_dependents`, delegating only to the existing store/event authority.
- Corrected the review-reported I001 local import ordering.

## Verification

- RED: six mutation-path integration cases failed because source-dependency registration lacked `source_revision_id`.
- Focused/elevated PASS: Matter unit/integration selection — `56 passed in 9.70s`.
- Targeted/elevated PASS: changed-file Ruff and `mypy src/evidence_review/review_matter` (`15 source files`).
- Full Ruff, mypy, and compileall were executed before the final focused rerun and passed: Ruff `src tests web_runtime`, mypy `src` (`267 source files`), and compileall `src scripts web_runtime tests`.
- `git diff --check` and staged `git diff --cached --check` passed before the code commit.

## Not-run / host limitations

- Documentation validation: `SOURCE_MISMATCH`, not PASS. The exact command resolved the installed package from `F:\2026-PJ\evidence-review-system\src\evidence_review`, not this worktree.
- Full pytest: `NOT_RUN` to completion. Foreground attempts stopped near 3% without a JUnit artifact. The user-directed checkpoint stopped known background PID `542236`; no broad pytest process was left intentionally running.
- Manual browser, protected/archival decision, timing, and release acceptance gates: `NOT_RUN`.

## Scope and authority

- The ledger records the fix-round scope ruling for the existing schema/store/event/projection/service path and adjacent tests.
- No Formalization Snapshot, Formal Run binding, review packet, evidence DB, Rule/Math, Track A/B, Human Decision, case/visual lineage, or primary-checkout file was changed.
