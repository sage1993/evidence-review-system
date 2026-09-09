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
