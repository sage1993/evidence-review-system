# PR-A Execution Bootstrap

This file overrides only Task 1 bootstrap mechanics in `2026-08-26-pr-a-issue-116-correctness-convergence.md`.

## Source-of-truth baseline

- Code baseline: `main@3eb45de3d6d12265d6fa75f713b42a570955e949`
- Reference implementation: PR #117 HEAD `e8e17271888b6f4833776c4200a24fe40c5d7772`
- Approved design/plan source branch: `docs/integrated-correctness-reference-viewer-design`

## Required local bootstrap

Create the worktree from current main, not from the docs branch:

```powershell
git fetch origin main docs/integrated-correctness-reference-viewer-design docs/issue-116-correctness-hardening

git worktree add F:\2026-PJ\evidence-review-system-issue116-convergence `
  agent/issue-116-correctness-convergence

Set-Location F:\2026-PJ\evidence-review-system-issue116-convergence

git rev-parse HEAD
git status --short
```

Expected HEAD before edits:

```text
3eb45de3d6d12265d6fa75f713b42a570955e949
```

The remote branch `agent/issue-116-correctness-convergence` already points to that exact baseline.

Bring only the approved execution documents into the implementation branch before code edits:

```powershell
git checkout origin/docs/integrated-correctness-reference-viewer-design -- `
  docs/superpowers/specs/2026-08-26-integrated-correctness-reference-viewer-design.md `
  docs/superpowers/plans/2026-08-26-pr-a-issue-116-correctness-convergence.md `
  docs/superpowers/plans/2026-08-26-pr-b-reference-viewer-v2.md

git add docs/superpowers/specs docs/superpowers/plans
git commit -m "docs: add approved convergence execution plans"
```

Then run the unmodified-main verification gate before any production-code port:

```powershell
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
```

Do not proceed past a real baseline failure. Environment-only deviations must be recorded before implementation.
