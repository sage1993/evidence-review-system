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
