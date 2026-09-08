# MIG-05 implementation report

## Scope

Implemented the bounded MIG-05 foundation for exact finalized-evidence binding and conservative ReviewMatter source invalidation. Matter work remains in the separate Matter database; no evidence database or preserved source bytes are written.

## Implementation

- `bind_finalized_evidence(...)` delegates validation and provenance calculation to `finalized_evidence_provenance(...)`, then validates and persists the exact logical snapshot SHA-256, closed-file evidence database SHA-256, and schema version through the existing Matter event/projection transaction.
- Invalid, unfinalized, stale-logical-snapshot, corrupt, and sidecar-backed evidence is rejected as `MATTER_EVIDENCE_BINDING_INVALID` before Matter mutation.
- Rebinding a different finalized identity emits `EVIDENCE_REBOUND` as a new Matter revision and conservatively marks Matter issues `STALE`. Rebinding the same exact identity is a no-op, while stale expected revisions still fail with `MATTER_REVISION_CONFLICT`.
- Source dependencies retain validated source identity and SHA-256 metadata. Changed source hashes stale known dependents; issues with missing dependency modeling are also invalidated conservatively. Unchanged source identity/hash is a no-op.
- The integration test’s dynamic `__import__` was replaced with a normal `MatterIssue` import.

## Coverage

Added/extended coverage for:

- exact provenance persistence and read-only evidence behavior;
- unfinalized, sidecar-backed, and stale logical-snapshot rejection with unchanged Matter state;
- append-only rebind event/revision behavior;
- dependent and unmodelled-impact staleness;
- unchanged-source no-op;
- stale expected-revision rejection for binding and invalidation;
- exact source dependency persistence.

## Verification

- Focused MIG-05 unit/integration suite: **25 passed**.
- Final binding/invalidation subset: **11 passed**.
- Ruff on the four changed source/test files: **passed**.
- `git diff --check` on the changed files: **passed**.

The broader review_matter Ruff run still reports pre-existing issues in MIG-02/04 files (`contracts.py`, `projection.py`, and `test_concurrency.py`). Targeted mypy also reports pre-existing errors in those same migration files. A broader compileall attempt was blocked by existing Windows ACL-denied `__pycache__` files. These were not modified or staged for MIG-05.

## Scope review

Only the two MIG-05 implementation modules, their focused unit/integration tests, and this report are intended for the MIG-05 commit. User-supplied `AGENTS.md`, migration plan/report documents, and unrelated changes remain untouched and unstaged.

## Round-1 reviewer fix report

Addressed all four reviewer findings:

1. **Self-contained branch:** the implementation-owned MIG-01..04 contracts, store/schema, event/projection modules, architecture docs, and their unit/integration/documentation tests are included in the follow-up commit alongside MIG-05. `AGENTS.md`, the migration plan, the DOCX report, and the Korean report remain excluded.
2. **Conservative invalidation:** a changed named source now stales every MatterIssue unless the source hash is unchanged. Added regression coverage for an issue modeled only against another source key; it is also staled because no approved negative-impact/completeness contract exists.
3. **Deterministic metadata recovery:** `rebuild_projection` now clears and replays evidence-binding and source-dependency side effects inside the same transaction as projection rebuild. Added recovery coverage for restored binding identity and updated dependency hash.
4. **Evidence event validation:** `EVIDENCE_BOUND` and `EVIDENCE_REBOUND` now require all provenance fields, validate both SHA-256 values, require a positive schema version, and require `bound_revision` to equal the next Matter revision. Added parameterized validation coverage for both event kinds.

### Round-1 verification

- RED reproduction before implementation: 12 expected failures, 2 existing tests passed.
- Round-1 focused GREEN: **14 passed**.
- Complete ReviewMatter and migration documentation coverage: **37 passed**.
- Ruff across the self-contained ReviewMatter package and tests: **passed** after migration-only import/lint cleanup.
