# PR-A Execution Bootstrap

This file overrides Task 1 bootstrap mechanics in `2026-08-26-pr-a-issue-116-correctness-convergence.md`.

## Source-of-truth baseline

- Code baseline parent: `main@3eb45de3d6d12265d6fa75f713b42a570955e949`
- Reference implementation: PR #117 HEAD `e8e17271888b6f4833776c4200a24fe40c5d7772`
- Actual PR #117 branch: `docs/issue-116-correctness-hardening-plan`
- Approved design/plan branch: `docs/integrated-correctness-reference-viewer-design`
- Execution branch: `agent/issue-116-correctness-convergence`

The execution branch contains documentation-only bootstrap commits. Production code must still match `main@3eb45de3d6d12265d6fa75f713b42a570955e949` before selective porting.

## Correct local bootstrap

From the primary checkout:

```powershell
Set-Location F:\2026-PJ\evidence-review-system

git fetch --prune origin

git branch -r --list `
  "origin/agent/issue-116-correctness-convergence" `
  "origin/docs/integrated-correctness-reference-viewer-design" `
  "origin/docs/issue-116-correctness-hardening-plan"
```

All three refs must be listed. Verify PR #117 reference SHA:

```powershell
git rev-parse origin/docs/issue-116-correctness-hardening-plan
```

Expected:

```text
e8e17271888b6f4833776c4200a24fe40c5d7772
```

Remove only an empty failed target directory:

```powershell
$wt = "F:\2026-PJ\evidence-review-system-issue116-convergence"
if (Test-Path $wt) {
  if (@(Get-ChildItem -Force $wt).Count -eq 0) {
    Remove-Item -Force $wt
  } else {
    throw "Worktree target is not empty: $wt"
  }
}
```

Create and enter the worktree. The earlier failed commands did not create a local branch, so create it while tracking the remote execution branch:

```powershell
git worktree add -b agent/issue-116-correctness-convergence `
  $wt `
  origin/agent/issue-116-correctness-convergence

Set-Location $wt

git status --short
git branch --show-current
git rev-parse HEAD
```

Do not run a second `git switch -c`; `git worktree add -b` already creates and checks out the local branch.

Verify production code is unchanged from current main:

```powershell
git diff --quiet origin/main HEAD -- src tests web_runtime .agents skills AGENTS.md
$LASTEXITCODE
```

Expected: `0`.

Bring only the approved spec and implementation plans into the execution branch:

```powershell
git checkout origin/docs/integrated-correctness-reference-viewer-design -- `
  docs/superpowers/specs/2026-08-26-integrated-correctness-reference-viewer-design.md `
  docs/superpowers/plans/2026-08-26-pr-a-issue-116-correctness-convergence.md `
  docs/superpowers/plans/2026-08-26-pr-b-reference-viewer-v2.md

git add docs/superpowers/specs docs/superpowers/plans
git commit -m "docs: add approved convergence execution plans"
```

Then run the unchanged-production baseline gate:

```powershell
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
```

Do not proceed past a real baseline failure. Environment-only deviations must be recorded before implementation.
