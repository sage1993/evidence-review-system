# Commit, Push, and Pull Request Policy

This is the canonical policy for issue-scoped commit, push, review, and merge
work. It complements, but does not replace, the local acceptance requirements
in [Manual Acceptance and Main-Merge Policy](MANUAL_ACCEPTANCE_POLICY.md).

## Required issue workflow

1. Start from the latest exact `origin/main` SHA in an isolated `feature/` or
   `fix/` branch and worktree. Record the base SHA, branch, and clean-worktree
   state before work begins.
2. Preserve pre-existing user changes. Do not delete, overwrite, reset, clean,
   restore, or automatically stash/drop unrelated work.
3. Make only the issue-scoped change. For behavior changes, use RED → minimal
   GREEN → adjacent regression; for documentation-only work, record TDD as
   `NOT_APPLICABLE` rather than inventing a test-only change.
4. Run focused verification, then commit only the reviewed issue files with an
   issue-specific subject.
5. Run all applicable acceptance gates from a clean checkout at that committed
   candidate SHA. The candidate must not be changed afterward; any source,
   test, documentation, or generated-file edit requires a new commit and a
   repeat of the invalidated gates.
6. Push only the issue branch, without force-push, and verify that the remote
   branch SHA equals the tested local candidate SHA.
7. Open a pull request to `main`, obtain independent pre-merge review, and
   merge only when the PR head still equals the accepted candidate SHA.
8. After merge, verify the candidate is an ancestor of `origin/main`, confirm
   the PR is merged, confirm the issue is `CLOSED`, and record how the remote
   feature branch was handled. If candidate ancestry, PR merge, or issue
   closure cannot be confirmed, merge readiness is `HOLD`.

The required identity invariant is:

```text
TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA
```

If any value differs, acceptance is stale and merge readiness is `HOLD` until
the new candidate is verified.

## Commit subject convention

Every issue commit subject must use this exact form:

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

A commit subject that omits the issue or change type is not eligible for issue
acceptance until corrected in a new commit.

## Commit, acceptance, and PR evidence

Do not accept a dirty worktree or include unrelated files in an issue commit.
Do not report an unrun command as passing. The PR evidence must record:

- issue, base SHA, candidate SHA, remote SHA, and PR-head SHA;
- branch, worktree cleanliness, and the exact changed files;
- exact validation commands and results, OS, Python version, and applicable
  artifact hashes;
- manual-QA state; and
- the actual Actions state defined below.

Record exactly one applicable Actions state:

- `ACTIONS_NOT_RUN` — Actions was deliberately not started;
- `ACTIONS_UNAVAILABLE` — an Actions execution or service was unavailable for
  a non-billing reason;
- `ACTIONS_BILLING_BLOCKED` — Actions was unavailable because of account
  billing or spending limits; or
- an observed workflow result, recorded as observed.

None of `ACTIONS_NOT_RUN`, `ACTIONS_UNAVAILABLE`, or
`ACTIONS_BILLING_BLOCKED` means PASS. An observed workflow result is evidence
only of that observed result; local/manual acceptance is never inferred to be
a GitHub Actions pass.

Required package, browser, evidence, security, or platform gates remain
applicable when their change boundary requires them.

## Prohibited actions and fail-closed conditions

Never directly push to `main`, force-push, delete `main`, use a dirty
worktree for acceptance, or hide unrelated changes in an issue commit. Never
claim that a SHA was tested when a different SHA is pushed or is the PR head.

Fail closed and stop for a stale or unknown base, dirty candidate, unexpected
file, failed or unrun applicable gate, local/remote SHA mismatch, missing
independent review, changed PR head, candidate not in `origin/main`, PR not
merged, issue not `CLOSED`, ambiguous protection state, or unresolved
security/provenance concern. Do not bypass a repository control or an explicit
maintainer-required check.

## GitHub `main` protection is separate

The repository settings are server-enforced controls; this policy is the
operator process. As verified on 2026-09-12 for issue #162 / PR #221, `main`
requires pull requests, enforces the rule for administrators, requires zero
approvals, permits no bypass, has no required status checks, and disables both
force-push and branch deletion.

Zero required GitHub approvals does not waive the independent pre-merge review
in this process. Likewise, successful local acceptance does not create a
GitHub status check. See
[Manual Acceptance and Main-Merge Policy](MANUAL_ACCEPTANCE_POLICY.md) for the
local acceptance gates and their distinction from these settings.
