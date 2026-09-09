# MIG-06 Task 6 Report — Evidence Navigation

## Changed files

- `src/evidence_review/navigation/__init__.py`
- `src/evidence_review/navigation/models.py`
- `src/evidence_review/navigation/query.py`
- `src/evidence_review/navigation/service.py`
- `src/evidence_review/navigation/promotion.py`
- `src/evidence_review/review_matter/projection.py`

The navigation service opens only finalized evidence through `EvidenceStore(read_only=True)`, validates finalization and retrieval freshness, and returns only exact citation-backed hits. Promotion revalidates finalized artifact provenance, Matter evidence binding, retrieval-record identity, citation identity, and Matter CAS before atomically appending `EVIDENCE_SELECTED`. Projection rebuild restores the selected `MatterSourceBinding` without changing the Matter schema version.

## RED

Command:

```powershell
py -3.13 -m pytest -q tests/unit/navigation/test_service.py tests/integration/navigation/test_promotion_boundary.py --basetemp C:\Temp\mig-06-red
```

Result: `14 failed in 4.17s`, all due to the intentionally missing `evidence_review.navigation` package (`NAVIGATION_SERVICE_MISSING` / `NAVIGATION_PACKAGE_MISSING`).

The non-elevated equivalent could not create its pytest base temporary directory because of the inherited worktree ACL; the elevated-capable scratch directory above was required to observe the behavioral RED result.

## GREEN and focused verification

Initial focused GREEN command:

```powershell
py -3.13 -m pytest -q tests/unit/navigation/test_service.py tests/integration/navigation/test_promotion_boundary.py --basetemp C:\Temp\mig-06-green-2
```

Result: `14 passed in 4.16s`.

Required focused navigation and Issue-153 regression command:

```powershell
py -3.13 -m pytest -q tests/unit/navigation/test_service.py tests/integration/navigation/test_promotion_boundary.py tests/integration/review_question/test_issue_153_planner_false_no_evidence.py --basetemp C:\Temp\mig-06-final
```

Result: `18 passed in 6.46s`.

Scoped static checks:

```powershell
py -3.13 -m ruff check src\evidence_review\navigation src\evidence_review\review_matter\projection.py
py -3.13 -m compileall -q src\evidence_review\navigation src\evidence_review\review_matter\projection.py
git diff --check
```

Result: all passed.

## Concerns

- The full repository acceptance suite was not run; this task required focused navigation tests and the Issue-153 regression only.
- The supplied navigation RED tests remain untracked and unstaged because the task brief lists them as an existing behavioral contract and restricts implementation changes to the listed production files. They were not modified.
- Git emits an existing CRLF conversion warning for `review_matter/projection.py`; scoped whitespace validation passes.

## Fix round 1 — independent review findings

### Changes

- Promotion now requires `citation_id == f"CIT-{hit.evidence_id}"` before any Matter mutation. A forged frozen `NavigationResult` is rejected with `NAVIGATION_RESULT_STALE` and leaves the Matter projection and event journal unchanged.
- Navigation now skips a raw hit explicitly marked `citation_quality: PAGE_ONLY` before attempting any citation parsing. It continues to omit page-only content rather than fabricating a bounding box.
- Added regression coverage in the supplied navigation tests for both paths.

### RED

```powershell
py -3.13 -m pytest -q tests/unit/navigation/test_service.py tests/integration/navigation/test_promotion_boundary.py --basetemp C:\Temp\mig-06-fix-red
```

Result: `2 failed, 14 passed in 5.05s`.

- Page-only input attempted to parse the malformed citation and raised `ValueError: citation must be an object`.
- A forged citation ID did not raise and would have allowed selection.

### GREEN and verification

```powershell
py -3.13 -m pytest -q tests/unit/navigation/test_service.py tests/integration/navigation/test_promotion_boundary.py --basetemp C:\Temp\mig-06-fix-green
```

Result: `16 passed in 5.14s`.

```powershell
py -3.13 -m pytest -q tests/unit/navigation/test_service.py tests/integration/navigation/test_promotion_boundary.py tests/integration/review_question/test_issue_153_planner_false_no_evidence.py --basetemp C:\Temp\mig-06-fix-final
```

Result: `20 passed in 7.23s`.

### Concerns

- A Ruff run including all supplied navigation tests reports two pre-existing B017 broad-exception assertions in `tests/unit/navigation/test_service.py` (the unfinalized and stale-snapshot tests). This fix did not add or modify those assertions.
- The full repository acceptance suite was not run.

## Branch-review test cleanup

- Replaced the two broad navigation assertions with `EvidenceDatabaseNotFinalized` and `EvidenceLogicalSnapshotMismatch`, the exact validation exceptions produced by the service.
- Preserved all navigation coverage, including forged `citation_id` rejection and page-only omission.

```powershell
py -3.13 -m pytest -q tests/unit/navigation/test_service.py tests/integration/navigation/test_promotion_boundary.py tests/integration/review_question/test_issue_153_planner_false_no_evidence.py --basetemp C:\Temp\mig-06-test-cleanup
```

Result: `20 passed in 6.92s`.

Ruff over both supplied navigation test files and changed production files, plus scoped compileall and `git diff --check`, passed.

## Fix round 2 — malformed promotion result guard

- Added a Matter-boundary regression for an otherwise valid frozen navigation result whose hit has `citation=None`.
- Promotion now validates the result, hits, citation, identifiers, hashes, page numbers, bboxes, and decimal score before dereferencing fields or writing Matter state. Malformed values fail closed as `NAVIGATION_RESULT_STALE`.

RED:

```powershell
py -3.13 -m pytest -q tests/integration/navigation/test_promotion_boundary.py::test_promotion_rejects_missing_citation_without_matter_mutation --basetemp C:\Temp\mig-06-fix2-red
```

Result: `1 failed in 0.50s` with the expected pre-fix `AttributeError` from `hit.citation.citation_id`.

GREEN and focused verification:

```powershell
py -3.13 -m pytest -q tests/unit/navigation/test_service.py tests/integration/navigation/test_promotion_boundary.py tests/integration/review_question/test_issue_153_planner_false_no_evidence.py --basetemp C:\Temp\mig-06-fix2-final
```

Result: `21 passed in 7.73s`. Ruff over the supplied navigation tests and changed production files, scoped compileall, and `git diff --check` passed.

Concern: the full repository acceptance suite was not run.
