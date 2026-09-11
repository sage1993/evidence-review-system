# SDD ledger — plan: docs/plans/2026-09-08-ers-review-matter-architecture-migration.md

## Identity

- Issue: #186 / MIG-16
- BASE_SHA: `77acddec866b85c3fca724dd2cd94946fd93203f`
- BRANCH: `feat/mig-16-revision-impact-invalidation`
- USER_DIRTY_CHANGES_PRESERVED = YES

## Preflight scan

| Task/interface row | Files or interface relationship | Finding | Ruling/status |
|---|---|---|---|
| MIG-16 impact → invalidation events | `impact.py`, `invalidation.py`, `MatterEvent`, projection | Impact computation must stay deterministic and application must use existing atomic append-only events. | Ruling: create an immutable report/projection and route application through existing `ISSUES_INVALIDATED` semantics; no new database authority. Proceed. |
| MIG-16 impact → Matter source dependencies | `store.list_source_dependencies`, `register_issue_source_dependency` | Dependency records are mutable-work metadata and must be checked exactly; unknown graph cannot be treated as unaffected. | Proceed conservatively: exact known unchanged identities may retain, changed or unmodelled dependencies require stale/recheck. |
| MIG-16 invalidation → formalization | `snapshot.py`, required issue work states | Existing formalization must reject stale/unresolved work and must not rewrite old Formal Run/packet artifacts. | Preserve existing formalization gate; add only the missing integration boundary/regression if required. |
| MIG-16 service scope | `service.py` | Issue plan permits service modification but no exact service API is stated. | Ruling: only add a canonical service façade if necessary to expose existing invalidation atomically; otherwise leave service unchanged and record no scope expansion. |
| MIG-16 own contract | source revision/hash, dependency fan-out, uncertainty, retention | The issue and migration plan agree; no plan contradiction identified. | Proceed. |

## Status

- Pre-edit scope ruling: `SCOPE_EXPANSION_REQUIRED = NO`. Implement the deterministic impact report and apply it only through the existing `ISSUES_INVALIDATED` event/projection path; retain the existing mutable-work dependency table and immutable Formal Run/packet stores unchanged.
- Adjacent-regression scope ruling: `SCOPE_EXPANSION_REQUIRED = YES` for `tests/unit/review_matter/test_source_binding.py` only. Its prior expectation that an explicitly independent source dependency becomes stale conflicts with MIG-16's required exact-identity retention; update that assertion without changing any production authority boundary.
- Fix-round 1 scope ruling: `SCOPE_EXPANSION_REQUIRED = YES` for `schema.sql`, `store.py`, `events.py`, `projection.py`, `service.py`, and adjacent Matter tests. The review establishes that revision identity must be persisted in the existing event-owned dependency record and projected through the same atomic append path. Upgrade only that existing table/event contract, validate every raw persisted record before retention, and add a `ReviewMatterService` façade that delegates to the existing invalidation function; no new persistence authority is permitted.
- Fix-round 1 implementation: `7df379b7ed91be478093c8f37414e265b6db28af`. Focused Matter verification (`56 passed`) and targeted Ruff/mypy passed. Full Ruff/mypy/compileall were run before the final focused rerun and passed. Documentation validation is `SOURCE_MISMATCH` because the installed package resolved to the primary checkout. Full pytest is `NOT_RUN` to completion: host foreground runs stopped near 3% without a JUnit result, and the user-directed checkpoint stopped the known background PID `542236`.
- Implementer: PENDING
- Task review: PENDING
- Broad review: PENDING
- Push/PR/merge: PENDING
