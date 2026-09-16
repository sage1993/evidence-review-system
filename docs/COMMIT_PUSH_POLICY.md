# Commit, Push, and Pull Request Policy

This is the canonical policy for issue-scoped commit, push, review, and merge
work. It complements, but does not replace, the local acceptance requirements
in [Manual Acceptance and Main-Merge Policy](MANUAL_ACCEPTANCE_POLICY.md).

The public repository governance contract is:

```text
GITHUB_ACTIONS = NOT_USED_BY_POLICY
LOCAL_EXACT_SHA_VERIFICATION = AUTHORITATIVE_ACCEPTANCE
MAIN_INTEGRATION = PULL_REQUEST_ONLY
REQUIRED_STATUS_CHECKS = NONE
```

Pull-request creation is not acceptance. The PR head must equal the exact
candidate SHA that passed local verification. Any unverified remote or PR
identity is a fail-closed `HOLD`.

## Required issue workflow

1. Start from the latest exact `origin/main` SHA in an isolated issue-scoped
   branch and worktree (for example `feature/`, `fix/`, or `chore/`). Record the
   base SHA, branch, and clean-worktree state before work begins.
2. Preserve pre-existing user changes. Do not delete, overwrite, reset, clean,
   restore, or automatically stash/drop unrelated work.
3. Make only the issue-scoped change. For behavior changes, use RED → minimal
   GREEN → adjacent regression; for documentation-only work, record TDD as
   `NOT_APPLICABLE` rather than inventing a test-only change.
4. Before committing, inspect the complete change and run the required scope
   and whitespace checks:

   ```text
   git status --short
   git diff --stat
   git diff
   git diff --check
   ```

   Inspect every untracked file shown by `git status` as well; it is not
   included in `git diff`. After staging, inspect `git diff --cached --stat`,
   `git diff --cached`, and `git diff --cached --check`. Confirm that the staged
   file set exactly matches the issue scope. Stop if any file is unexpected or
   any whitespace error is reported. Run focused verification, then commit only
   the reviewed issue files with a conforming issue-specific subject.
5. Run all applicable acceptance gates from a clean checkout at that committed
   candidate SHA. The candidate must not be changed afterward; any source,
   test, documentation, or generated-file edit requires a new commit and a
   repeat of the invalidated gates.
6. Push only the issue branch, without force-push, and verify that the remote
   branch SHA equals the tested local candidate SHA.
7. Open a pull request to `main` with a valid closing reference such as
   `Closes #<N>`. Obtain independent pre-merge review of the accepted candidate
   SHA and record the review evidence. Recheck that the PR head still equals
   the accepted candidate SHA, then merge using GitHub's **Create a merge
   commit** method. Do not use squash or rebase when the candidate-ancestor
   invariant below is required.
8. After merge, verify the candidate is an ancestor of `origin/main`, confirm
   the PR is merged, confirm the issue is `CLOSED`, and record how the remote
   feature branch was handled. If any post-merge check fails, set
   `POST_MERGE_COMPLETION = HOLD` and remediate the specific verification gap;
   do not describe this as pre-merge readiness after the merge has occurred.

The required identity invariant is:

```text
TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA
```

If any value differs, acceptance is stale and merge readiness is `HOLD` until
the new candidate is verified. The GitHub merge-commit method preserves the
candidate commit as an ancestor; squash and rebase do not guarantee this
identity invariant.

## Commit subject convention

Every contributor-authored commit on the issue branch must use this exact form:

```text
<type>(issue-<N>): <concise summary>
```

`<type>` identifies the change category and `issue-<N>` identifies the issue;
both are required. Use a concrete type such as `docs`, `feat`, `fix`, `test`,
`refactor`, or `chore`. For example:

```text
docs(issue-169): codify commit and push policy
fix(issue-169): require issue closure after merge
```

The local pre-merge verifier conservatively requires this form for every commit
in the candidate issue-branch range. Platform-generated merge commits occur
after this pre-merge candidate boundary and are outside the local issue-branch
acceptance range; a merge-shaped subject in that range is not treated as proof
of platform provenance.

A contributor-authored issue-branch commit subject that omits the issue or
change type is not eligible for issue acceptance. A later commit cannot change
an earlier commit's subject. If found before push, correct the subject by
amending/rebasing before final acceptance, then verify the new candidate and
rerun all invalidated gates. If found after push, do not add a purported
corrective commit or force-push: create a replacement branch from the recorded
base with compliant commit subjects, reapply the issue-scoped change, rerun
acceptance, and open a replacement PR. Keep the published branch/history
intact; close or supersede the old PR only after the replacement is available.

## Commit, acceptance, and PR evidence

Do not accept a dirty worktree or include unrelated files in an issue commit.
Do not report an unrun command as passing. The PR evidence must record:

- issue, base SHA, candidate SHA, remote SHA, and PR-head SHA;
- branch, worktree cleanliness, and the exact changed files;
- exact validation commands and results, OS, Python version, and applicable
  artifact hashes;
- independent review's exact reviewed SHA, reviewer identity/role and
  mechanism (including model and reasoning level for agent review), verdict,
  findings, and disposition of every finding;
- manual-QA state; and
- the actual Actions state defined below.

When no workflow file is observed, the current Actions state is:

```text
GITHUB_ACTIONS = NOT_USED_BY_POLICY
```

The local verifier observes `.github/workflows/*.yml` and `.yaml` files. The
value above is valid only when no workflow file is present; an observed
workflow is reported as `POLICY_MISMATCH` and keeps merge readiness at `HOLD`.
The verifier also requires an explicit `--issue N` binding and checks the
issue-scoped branch, contributor commit subject, PR head branch, and a
`Closes`, `Fixes`, or `Resolves #N` reference in the PR body.

`--json-report` outputs are external to the checkout. Package-affecting
changes require an external exact-candidate package evidence record with
PASS results for wheel build, isolated install, `pip check`, and runtime
smoke, together with the wheel SHA-256.

Do not create or enable workflows, add required Actions checks, or treat PR
creation as acceptance. Historical acceptance reports may retain
`ACTIONS_NOT_RUN`; those records are not rewritten. If an older report records
`ACTIONS_UNAVAILABLE` or `ACTIONS_BILLING_BLOCKED`, preserve that historical
fact as well. None of those historical values is a current PASS.

Required package, browser, evidence, security, or platform gates remain
applicable when their change boundary requires them.

## Prohibited actions and fail-closed conditions

Never directly push to `main`, force-push, delete `main`, use a dirty
worktree for acceptance, or hide unrelated changes in an issue commit. Never
claim that a SHA was tested when a different SHA is pushed or is the PR head.

Before merge, fail closed and stop for a stale or unknown base, dirty
candidate, unexpected file, failed or unrun applicable gate, local/remote SHA
mismatch, missing independent review evidence, unresolved review finding,
changed PR head, missing/invalid issue-closing reference, nonconforming
contributor-authored issue-branch commit subject, ambiguous protection state,
or unresolved security/provenance concern. After merge, if the candidate is
not in `origin/main`, the PR is not merged, or the issue is not `CLOSED`, set
`POST_MERGE_COMPLETION = HOLD` and resolve the specific post-merge gap. Do not
bypass a repository control or an explicit maintainer-required check.

## GitHub `main` protection is separate

The repository settings are server-enforced controls; this policy is the
operator process. The authenticated GitHub UI audit observed the following on
2026-09-16:

```text
MAIN_BRANCH_PROTECTED = YES
DIRECT_MAIN_PUSH = PROHIBITED (pull request required)
FORCE_PUSH_TO_MAIN = PROHIBITED
MAIN_BRANCH_DELETE = PROHIBITED
PULL_REQUEST_REQUIRED = YES
REQUIRE_CONVERSATION_RESOLUTION = YES
ADMIN_BYPASS = PROHIBITED
REQUIRED_STATUS_CHECKS = NONE
RULESETS = NONE
```

The audit must observe, rather than infer, those values. When the GitHub API or
UI cannot expose them, record:

```text
BRANCH_PROTECTION_DETAIL = NOT_OBSERVABLE_WITH_CURRENT_API_PERMISSION
```

The target policy remains direct push prohibited, force-push prohibited,
`main` deletion prohibited, pull-request-only integration, and zero required
status checks. Conversation resolution is now required by the protected main
branch. Zero required GitHub approvals does not waive
independent pre-merge review, and local acceptance does not create a GitHub
status check. See
[Manual Acceptance and Main-Merge Policy](MANUAL_ACCEPTANCE_POLICY.md) for the
local gates and their distinction from server settings.

Run the local verifier before opening or updating a PR:

```powershell
py -3.13 scripts/repository_gate.py --issue <N> --json-report "$env:TEMP\ers-repository-gate-<N>.json"
```
