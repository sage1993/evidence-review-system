# Repository Hygiene & Documentation Baseline Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely remove only remote branches proven merged or fully contained in the current `origin/main`, make the current documentation authority obvious, and align the root README with the exact current runtime contract without changing production behavior.

**Architecture:** The maintenance branch starts at the freshly fetched `origin/main` and uses a separate clean worktree. Remote branch deletion is an evidence-backed GitHub operation recorded independently from repository file changes. Documentation changes are limited to a current documentation index, a concise current README, and this historical execution record; existing historical plans and acceptance records remain immutable.

**Tech Stack:** Git and GitHub CLI/API for repository state, Markdown documentation, the repository's Python 3.13 documentation validator, pytest, Ruff, mypy, and compileall.

**Spec:** User-provided “Evidence Review System — Repository Hygiene & Documentation Baseline Closure” request in this task; no separate design document was supplied.

## Global Constraints

- Use the freshly fetched `origin/main` as the only base authority.
- Preserve all pre-existing dirty changes in `evidence-review-system-reference-viewer-v2`; do not stash, reset, checkout over, commit, or delete them.
- Delete a remote branch only when its tip is an ancestor of `origin/main` or its head is proven to be a merged GitHub PR, and only outside the explicitly protected review families `agent/*`, `codex/*`, `docs/*`, `plan/*`, `release/*`, `fix/stab-pr*`, and `fix/windows-*`; preserve unresolved, unmerged, ambiguous, open-issue-linked, and release-forensic branches.
- Do not modify production Python logic, API/schema/retrieval/review/UI behavior, tests to change behavior, or Issue #140.
- Keep `docs/MANUAL_ACCEPTANCE_POLICY.md` as current release acceptance authority.
- Current release commands are `py -3.13 scripts/validate_release.py $Workspace` and `py -3.13 scripts/build_release.py $Workspace $OutputDir`; `scripts/validate_workspace.py` is retired and `scripts/validate_legacy_ansim_workspace.py` is explicit legacy-only compatibility.
- Preserve historical documents, especially `docs/plans/*` and `docs/superpowers/plans/*`; do not rewrite old commands inside historical records.
- README claims must match `pyproject.toml`, the active `.agents/skills` entrypoints, and current workflow/release documentation.
- Any unexecuted gate is reported as `NOT_RUN`, never inferred as PASS; GitHub Actions status is reported separately.

---

### Task 1: Establish the exact base and inventory every remote branch

**Files:**
- Create outside the repository: a temporary branch inventory TSV; do not commit it.
- Preserve: the existing dirty worktree at `F:/2026-PJ/evidence-review-system-reference-viewer-v2`.

**Interfaces:**
- Consumes: freshly fetched `origin/main` and all `refs/remotes/origin/*` refs.
- Produces: base SHA, clean maintenance worktree, a row for every non-`origin/HEAD` remote branch, ancestry/unique-commit evidence, related PR state when available, and DELETE/PRESERVE/REVIEW decisions.

- [ ] **Step 1: Record the original worktree safety state.**

  Run from `F:/2026-PJ/evidence-review-system-reference-viewer-v2`:

  ```powershell
  git status --short
  git diff --stat
  git diff --name-only
  git ls-files --others --exclude-standard
  git branch --show-current
  git rev-parse HEAD
  git rev-parse origin/main
  git remote -v
  ```

  Treat the four modified tracked files and any protected pytest directories already present as user-owned and unchanged.

- [ ] **Step 2: Fetch and create the isolated maintenance worktree.**

  ```powershell
  git fetch origin --prune
  git worktree add `.worktrees\repository-hygiene-docs` -b `chore/repository-hygiene-docs` origin/main
  Set-Location `.worktrees\repository-hygiene-docs`
  git status --short
  git branch --show-current
  git rev-parse HEAD
  git rev-parse origin/main
  ```

  Require a clean worktree with `HEAD` equal to the fetched `origin/main` SHA before continuing.

- [ ] **Step 3: Build a complete remote branch inventory.**

  Enumerate `refs/remotes/origin`, exclude `origin/HEAD`, and capture branch, tip SHA, commit date, and subject with:

  ```powershell
  git for-each-ref --format="%(refname:short)|%(objectname)|%(committerdate:iso8601)|%(subject)" refs/remotes/origin
  ```

  For each branch, run both checks against the exact base:

  ```powershell
  git merge-base --is-ancestor "origin/$Branch" origin/main
  git rev-list --count "origin/main..origin/$Branch"
  ```

  Store `ANCESTOR=YES` only for exit code 0, and store the unique commit count. Do not classify by branch name alone.

- [ ] **Step 4: Enrich branch rows with GitHub PR evidence.**

  Query the public repository `sage1993/evidence-review-system` for closed and open pull requests, match exact `head.ref` values, and record `state`, `merged_at`, PR number, and head SHA. A branch with failed ancestry, unique commits, an open PR, an open-issue dependency, recent unresolved work, or unclear purpose remains `PRESERVE_FOR_REVIEW`.

- [ ] **Step 5: Produce the deletion candidate set.**

  A branch is a candidate only if `ANCESTOR=YES` and `UNIQUE_COMMITS=0`, or if its exact GitHub head is proven merged, and it is outside the protected review families. Preserve `fix/windows-oversized-413-socket-race` for review even when current evidence proves it is merged; record its ancestry, PR, unique commits, tip SHA, and recent commit date separately.

### Task 2: Delete only proven-safe remote branches and verify the result

**Files:**
- No repository files.
- Remote refs: delete only exact branch names from the approved candidate set in Task 1.

**Interfaces:**
- Consumes: the completed inventory and deletion candidate set.
- Produces: remote deletion evidence, preserved branch counts, and an after-inventory.

- [ ] **Step 1: Review candidates by logical group.**

  Prioritize `verify/stab-pr3-*` through `verify/stab-pr6-*`, then `fix/issue-130-filesystem-trust-closure`, `fix/issue-138-legacy-workspace-validator`, and `fix/issue-139-invalid-escape-warning`, but include a branch only when its recorded evidence meets the deletion rule. Treat `agent/*`, `codex/*`, `docs/*`, `plan/*`, `release/*`, `fix/stab-pr*`, and `fix/windows-*` as review-preserved regardless of contained ancestry.

- [ ] **Step 2: Delete exact proven-safe refs in small batches.**

  Set `$DeletedBranches` to the reviewed array of exact branch names, never a glob or a branch-family wildcard, and execute:

  ```powershell
  $DeletedBranches | ForEach-Object {
      git push origin --delete $_
      git fetch origin --prune
  }
  ```

  Repeat for each reviewed batch. If any deletion is rejected, retain the branch and record the failure; do not force or bypass the remote protection.

- [ ] **Step 3: Verify every deleted branch.**

  Re-run `git fetch origin --prune`, list all remaining `git branch -r` refs, and confirm every deleted name has `MERGED_IN_MAIN=YES` or `MERGED_PR=YES`. Record `REMOTE_BRANCHES_BEFORE`, `REMOTE_BRANCHES_DELETED`, `REMOTE_BRANCHES_AFTER`, `PRESERVED_UNMERGED_BRANCHES`, and `PRESERVED_REVIEW_BRANCHES`.

### Task 3: Inventory and classify the documentation tree

**Files:**
- Read: every file under `docs/`.
- Preserve unchanged: `docs/plans/*`, `docs/superpowers/plans/*`, acceptance records, migration records, examples, and reference assets unless a broken current link requires a current-index correction.

**Interfaces:**
- Consumes: the complete `docs/` file list and document contents.
- Produces: a classification map used by `docs/README.md` with the categories `CURRENT_AUTHORITY`, `CURRENT_ARCHITECTURE`, `CURRENT_OPERATIONS`, `MIGRATION_COMPATIBILITY`, `ACCEPTANCE_RECORD`, `HISTORICAL_PLAN`, `GENERATED`, `OBSOLETE_OR_DUPLICATE`, and `UNKNOWN`.

- [ ] **Step 1: Enumerate all documentation files.**

  ```powershell
  Get-ChildItem docs -Recurse -File |
      Sort-Object FullName |
      ForEach-Object { $_.FullName }
  ```

- [ ] **Step 2: Verify current authority against executable commands.**

  Read `docs/MANUAL_ACCEPTANCE_POLICY.md`, `docs/REVIEWER_WORKFLOW.md`, `docs/CODEX_WORKFLOW.md`, `docs/CHATGPT_WEB_WORKFLOW.md`, `docs/CONTRACT_GOVERNANCE.md`, and the current `.agents/skills` instructions. Confirm that the release commands and retired/legacy validator boundaries are represented consistently.

- [ ] **Step 3: Preserve historical evidence.**

  Mark both `docs/plans/` and `docs/superpowers/plans/` as historical execution records in the index. Do not mass-delete, rename, or modernize their embedded commands. Mark dated acceptance material as commit/date-specific evidence rather than current runtime authority.

### Task 4: Add the current documentation index

**Files:**
- Create: `docs/README.md`.
- Modify: `documentation-integrity.json` only to classify the existing plan directories as historical roots.

**Interfaces:**
- Consumes: Task 3 classification map and actual repository-relative paths.
- Produces: a single entrypoint that distinguishes current authority, architecture/contracts, operations, migration compatibility, acceptance records, and historical plans.

- [ ] **Step 1: Write the index with only existing links.**

  Include current authority links to `MANUAL_ACCEPTANCE_POLICY.md`, `REVIEWER_WORKFLOW.md`, `CODEX_WORKFLOW.md`, and `CHATGPT_WEB_WORKFLOW.md`; architecture/contract links to the existing question-planning, contract, source-batch, parser, rule, and numeric grammar documents; operations links to offline execution and the relevant operational documents; migration links to the existing schema, lineage, and legacy visual records; dated acceptance links to the existing acceptance record; and historical links to both `plans/` and `superpowers/plans/`.

- [ ] **Step 1a: Make the integrity metadata match the historical boundary.**

  Keep `README.md`, `AGENTS.md`, `docs`, and `skills` as current roots, and add `docs/plans` and `docs/superpowers/plans` to `historical_roots`. The validator's most-specific-root rule then classifies the existing plan directories as `HISTORICAL` without changing their bytes. Prefix links from current documents to those records with `Historical:` so current-to-historical references remain explicit.

- [ ] **Step 2: State release authority and retired command boundaries.**

  Explicitly identify `docs/MANUAL_ACCEPTANCE_POLICY.md` as release acceptance authority and show:

  ```powershell
  py -3.13 scripts/validate_release.py $Workspace
  py -3.13 scripts/build_release.py $Workspace $OutputDir
  ```

  Explain that `scripts/validate_workspace.py` is retired and `scripts/validate_legacy_ansim_workspace.py` is legacy migration/acceptance only.

### Task 5: Rewrite the root README as the current user/developer entrypoint

**Files:**
- Modify: `README.md`.
- Cross-check only: `pyproject.toml`, `.agents/skills/ers-pdf/SKILL.md`, `.agents/skills/ers-review/SKILL.md`, `documentation-integrity.json`, and the current docs authority files.

**Interfaces:**
- Consumes: exact project metadata, active workflow skills, and current documentation index.
- Produces: a concise README covering overview, guarantees, installation, `$ERS_PDF`, `$ERS_REVIEW`, Review Workspace, `READY_FOR_HUMAN_REVIEW`, current limitations, developer verification, and documentation.

- [ ] **Step 1: Align metadata and supported runtime.**

  State version `0.2.0` and Python `>=3.13,<3.14` exactly as in `pyproject.toml`. Do not present Python 3.11 or 3.12 as supported.

- [ ] **Step 2: Align the user workflows.**

  Document `$ERS_PDF` as the reference-document preparation and source/hash/page-image binding flow, and `$ERS_REVIEW` as the mandatory formal flow through active-workspace validation, Question Planner, QuestionPlan validation, retrieval, Track A, Track B, final packet, Review Workspace, and separate human decision. State that users do not hand-author intermediate JSON artifacts.

- [ ] **Step 3: Align trust and status boundaries.**

  Include user-level descriptions of source/hash binding, immutable evidence/review artifacts, canonical filesystem trust and verified regular-file boundaries, fail-closed validation, protected localhost presentation/image delivery, append-only human decisions, and the meaning of `READY_FOR_HUMAN_REVIEW`. Link contract-level detail to `docs/README.md`, `docs/OFFLINE_EXECUTION.md`, and the current workflow docs.

- [ ] **Step 4: Align release authority and repository structure.**

  List the current release validation/build commands, link to `docs/MANUAL_ACCEPTANCE_POLICY.md`, identify `scripts/validate_workspace.py` as retired and the ANSIM validator as legacy-only, and point to `.agents/skills/README.md` rather than presenting the legacy `skills/` path as the active skill tree.

- [ ] **Step 5: Remove stale current-facing material without rewriting history.**

  Remove duplicated stabilization history, obsolete current instructions, and historical release claims from the active README. Keep any genuinely useful version/release context concise and link detailed records through `docs/README.md`; do not edit historical plan files to achieve this.

### Task 6: Validate links, stale commands, documentation integrity, and full gates

**Files:**
- Read/validate: `README.md`, `docs/`, scripts, and repository documentation configuration.
- No source/test/runtime modifications permitted.

**Interfaces:**
- Consumes: completed documentation changes and exact maintenance HEAD.
- Produces: fresh verification evidence and a final scope report.

- [ ] **Step 1: Run the repository's documentation validator.**

  ```powershell
  $DocValidationOutput = Join-Path $env:TEMP "ers-doc-integrity-repository-hygiene.json"
  py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output $DocValidationOutput
  ```

  Inspect all errors and warnings. Classify historical-command warnings rather than modifying historical evidence. The current documentation gate is PASS only with `ERRORS = 0`.

- [ ] **Step 2: Search the required stale/current strings.**

  ```powershell
  git grep -n "validate_workspace.py"
  git grep -n "validate_legacy_ansim_workspace.py"
  git grep -n "validate_release.py"
  git grep -n "build_release.py"
  git grep -n "READY_FOR_HUMAN_REVIEW"
  git grep -n "0.2.0"
  git grep -n "Python 3.12"
  git grep -n "Python 3.11"
  ```

  Confirm historical-plan references are preserved, current README/docs references are accurate, and no stale current-facing command remains.

- [ ] **Step 3: Run the exact Python 3.13 verification gates.**

  ```powershell
  py -3.13 -m pytest
  py -3.13 -m ruff check src tests web_runtime
  py -3.13 -m mypy src
  py -3.13 -m mypy --platform win32 src
  py -3.13 -m compileall -q src scripts web_runtime tests
  git diff --check origin/main...HEAD
  ```

  If pytest fails, reproduce the same command on exact `origin/main` and classify an identical failure as `PRE_EXISTING_BASELINE`; classify a maintenance-only failure as `REGRESSION` and stop with `HOLD`. Do not alter production or test behavior to hide a baseline failure.

- [ ] **Step 4: Inspect final scope and issue preservation.**

  Confirm the diff contains only `README.md`, `docs/README.md`, `documentation-integrity.json`, and this plan/record (plus any narrowly justified current-doc correction), with zero changes under `src/`, `tests/`, `web_runtime/`, contracts, or Issue #140.

### Task 7: Commit the scoped documentation change and prepare review

**Files:**
- Stage only: `README.md`, `docs/README.md`, `documentation-integrity.json`, `docs/superpowers/plans/2026-09-07-repository-hygiene-documentation-baseline.md`, and any explicitly verified current-doc correction.

**Interfaces:**
- Consumes: fresh green or accurately classified verification evidence and remote cleanup report.
- Produces: a scoped commit on `chore/repository-hygiene-docs`, pushed branch, and a PR targeting `main`; never merge automatically.

- [ ] **Step 1: Stage and inspect only documentation files.**

  ```powershell
  git add README.md docs
  git diff --cached --stat
  git diff --cached --name-only
  git diff --cached --check
  git diff --cached --name-only | Select-String '^(src|tests|web_runtime|contracts)/'
  ```

  The last command must return no production/test/runtime paths.

- [ ] **Step 2: Commit the scoped change.**

  ```powershell
  git commit -m "docs: align repository documentation with current main"
  ```

- [ ] **Step 3: Push and create a review-only PR.**

  ```powershell
  git push -u origin chore/repository-hygiene-docs
  ```

  Create a PR titled `docs: align repository documentation and clean stale branches`, include the before/deleted/after branch counts, preserved branch counts, documentation/link status, exact verification statuses, `PRODUCTION_CODE_CHANGE = 0`, `ISSUE_140_CHANGE = 0`, and `MERGE = NOT_RUN`. Do not merge without explicit user approval.

- [ ] **Step 4: Perform the final verification-before-completion review.**

  Re-read this plan, inspect `git status --short`, `git log -1`, the final diff, and the PR state. Report any unrun gate as `NOT_RUN`, report GitHub Actions as its observed state, and use `READY_FOR_REVIEW` only when all required evidence supports that status.

---

## Self-review checklist

- [ ] Every remote branch was inventoried and classified using ancestry/unique-commit evidence and available PR evidence.
- [ ] No unresolved, unmerged, ambiguous, open-issue-linked, or forensic branch was deleted.
- [ ] Historical plans and acceptance records remain present and unchanged.
- [ ] `docs/README.md` is the current documentation entrypoint and links only to existing files.
- [ ] Root README metadata, workflows, architecture, trust boundaries, status meaning, active skills, and release commands match the current repository.
- [ ] Documentation integrity reports zero errors; current broken links and stale current commands are zero.
- [ ] Full verification results are fresh and accurately classified.
- [ ] No production, test, runtime, contract, or Issue #140 changes are staged or committed.
- [ ] The PR is review-only and merge remains `NOT_RUN`.
