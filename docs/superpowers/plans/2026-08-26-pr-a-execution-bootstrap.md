# PR-A Execution Bootstrap

This file overrides only Task 1 bootstrap mechanics in `2026-08-26-pr-a-issue-116-correctness-convergence.md`.

## Source-of-truth baseline

- Code baseline parent: `main@3eb45de3d6d12265d6fa75f713b42a570955e949`
- Execution branch bootstrap commit: `54469e72b4ca89cbe2e264b31c935babf9499b65`
- Reference implementation: PR #117 HEAD `e8e17271888b6f4833776c4200a24fe40c5d7772`
- Approved design/plan source branch: `docs/integrated-correctness-reference-viewer-design`

The bootstrap commit changes documentation only. Production code must still match the exact `3eb45de3d6d12265d6fa75f713b42a570955e949` baseline before selective porting begins.

## Required local bootstrap

Use the already-created remote execution branch:

```powershell
git fetch origin main agent/issue-116-correctness-convergence docs/integrated-correctness-reference-viewer-design docs/issue-116-correctness-hardening

git worktree add F:\2026-PJ\evidence-review-system-issue116-convergence `
  origin/agent/issue-116-correctness-convergence

Set-Location F:\2026-PJ\evidence-review-system-issue116-convergence

git switch -c agent/issue-116-correctness-convergence --track origin/agent/issue-116-correctness-convergence

git rev-parse HEAD
git status --short
git diff --quiet 3eb45de3d6d12265d6fa75f713b42a570955e949 HEAD -- src tests web_runtime .agents skills AGENTS.md
```

Expected:

```text
HEAD = bootstrap/document-only commits derived from 3eb45de3d6d12265d6fa75f713b42a570955e949
working tree clean
production-code diff command exits 0
```

Bring only the approved design and implementation plans into the execution branch before code edits:

```powershell
git checkout origin/docs/integrated-correctness-reference-viewer-design -- `
  docs/superpowers/specs/2026-08-26-integrated-correctness-reference-viewer-design.md `
  docs/superpowers/plans/2026-08-26-pr-a-issue-116-correctness-convergence.md `
  docs/superpowers/plans/2026-08-26-pr-b-reference-viewer-v2.md

git add docs/superpowers/specs docs/superpowers/plans
git commit -m "docs: add approved convergence execution plans"
```

Then run the unchanged-production baseline gate before any production-code port:

```powershell
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
```

Do not proceed past a real baseline failure. Environment-only deviations must be recorded before implementation.
