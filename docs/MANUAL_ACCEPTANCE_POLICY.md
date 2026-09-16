# Manual Acceptance and Main-Merge Policy

The current public-repository policy is:

```text
GITHUB_ACTIONS = NOT_USED_BY_POLICY
LOCAL_EXACT_SHA_VERIFICATION = AUTHORITATIVE_ACCEPTANCE
MAIN_INTEGRATION = PULL_REQUEST_ONLY
REQUIRED_STATUS_CHECKS = NONE
```

Opening a pull request is not acceptance. The local candidate must be tested
at an exact clean HEAD, and the pushed branch and PR head must be rechecked
against that same SHA. Any mismatch or unavailable identity is `HOLD`.

## ReviewMatter authority modes

Release acceptance distinguishes **Evidence Navigation**, which is
non-authoritative exploration, from the Workbench's **mutable ReviewMatter
work state**. **Formalization** is the exclusive promotion of a bound Matter
revision and finalized evidence snapshot into **Formal Review**. Only Formal
Review retains the deterministic Track/final-packet boundary and the separate
packet-bound Human Decision; user Matter data is not a release artifact.

## Default acceptance path

GitHub Actions is not an acceptance dependency for this repository. Issue and
pull-request work is verified locally from a clean checkout at the exact
implementation HEAD. GitHub Actions is not invoked as part of the normal issue
workflow and is recorded as `GITHUB_ACTIONS = NOT_USED_BY_POLICY` only when no
workflow file is present. If a workflow file is observed, the local verifier
reports `POLICY_MISMATCH` and holds; historical reports are not rewritten.

Run the one-command local verifier:

```powershell
py -3.13 scripts/repository_gate.py --issue <N> --json-report "$env:TEMP\ers-repository-gate-<N>.json"
```

The verifier runs documentation integrity, full pytest, Ruff, both mypy
platform checks, and compileall. It also checks branch ancestry, worktree
cleanliness, diff whitespace, candidate stability, remote branch SHA, and PR
head SHA. It exits nonzero and prints `MERGE_READINESS = HOLD` for any failed,
unrun, dirty, unknown, or mismatched condition.

## GitHub-enforced `main` controls and process-level gates

The authenticated GitHub UI audit observed the following on 2026-09-16:

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

The live audit must observe these values. If the current API or UI does not
expose them, record:

```text
BRANCH_PROTECTION_DETAIL = NOT_OBSERVABLE_WITH_CURRENT_API_PERMISSION
```

A prior observation (including the 2026-09-12 issue #162 / PR #221 record) is
historical evidence and is not silently promoted to a current PASS. The target
operating policy is direct push prohibited, force-push prohibited, branch
deletion prohibited, PR-only integration, and no required status checks.
Conversation resolution is required by the protected main branch. The zero
approval count does not make self-approval a
substitute for review.

Those are GitHub-enforced repository settings. They are distinct from the
operator process and local acceptance gates in
[Commit, Push, and Pull Request Policy](COMMIT_PUSH_POLICY.md): policy text
does not configure, replace, or itself prove GitHub settings, and a local PASS
does not become a GitHub status check.

The zero GitHub approval count does not waive the process-level requirement
for an independent pre-merge review. The PR workflow must obtain that review
and complete the applicable local manual acceptance gates below against the
exact candidate HEAD. Neither process-level review nor local acceptance is a
GitHub branch-protection status check.

Before merging a change into `main`, the maintainer must complete and record the
applicable manual gates:

- exact tested/candidate/pushed commit SHA and clean worktree state;
- documentation integrity validation;
- full pytest, Ruff, strict mypy, and compileall;
- isolated Python 3.13 wheel/install smoke when the package is changed;
- browser or other human-facing QA when the change has a UI boundary; and
- each exact command run and its result or exit code, the operating system,
  Python version, manual QA state, and relevant artifact SHA-256 values.

For changes that publish or read evidence databases, the acceptance record must
also show the finalized lifecycle (`FINALIZED`, finalization version, logical
snapshot/retrieval hash match, and SQLite integrity), the SHA-256 of the closed
published `evidence.sqlite`, that no SQLite WAL/SHM/journal sidecar is present,
and that this exact file hash is unchanged through the bound review lifecycle.
A logical snapshot hash may match across separate rebuilds without requiring
byte-identical SQLite files.

The acceptance record must state:

```text
GITHUB_ACTIONS = NOT_USED_BY_POLICY
```

Historical acceptance records may retain `ACTIONS_NOT_RUN`,
`ACTIONS_UNAVAILABLE`, or `ACTIONS_BILLING_BLOCKED`; do not rewrite them. Those
historical values are not current policy states and do not mean PASS.

This policy does not permit bypassing branch protection or an explicit
maintainer requirement for a particular external check. Such a check remains a
separate release or merge gate and must be reported separately from local
manual verification.

## Workspace and release validation authority

The current Evidence Review System release gates are:

```powershell
py -3.13 scripts/validate_release.py <workspace> --run-id <RUN-ID>
py -3.13 scripts/build_release.py <workspace> <output-dir> --run-id <RUN-ID>
```

`scripts/validate_workspace.py` is a retired ambiguous entrypoint and must not
be used as a current release gate. It exits fail-closed and points operators to
the current release commands above.

The historical ANSIM/Grist validator is preserved only for explicit legacy
acceptance or migration work as `scripts/validate_legacy_ansim_workspace.py`.
It is not a current release gate and must not be substituted for
`validate_release.py` or `build_release.py`.

## Platform-specific mypy boundary

Linux `mypy src` remains a required acceptance check. The standard-library
Linux type stubs do not expose the Windows-only `ctypes` symbols used by the
three platform-bound launcher/lock implementations. Only the exact
symbol-level `attr-defined,unused-ignore` annotations at those calls are
permitted; file-wide ignores, `ignore_errors`, and global weakening are not.

The Windows implementation must also be checked explicitly with the same
Python 3.13 toolchain:

```powershell
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
```

The first command proves the Linux source tree remains type-checked, and the
second proves the guarded Windows API path remains type-checked against the
Windows platform stubs.
