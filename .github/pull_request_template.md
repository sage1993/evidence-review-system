## Summary

Describe the problem and the smallest implemented solution.

## Related issues

Closes #<issue-number>

## Exact identity

Record these values from the same acceptance run. PR creation is not
acceptance, and all four SHA values must be identical before merge.

```text
BASE_SHA =
REMOTE_MAIN_SHA =
LOCAL_REMOTE_MAIN_SHA =
CANDIDATE_SHA =
TESTED_SHA =
COMMITTED_SHA =
PUSHED_SHA =
REMOTE_SHA =
PR_HEAD_SHA =
SHA_PARITY =
ISSUE_BINDING =
BRANCH =
WORKTREE =
```

## Architecture / trust-boundary impact

- [ ] No source/evidence authority changes
- [ ] No network/offline-boundary changes
- [ ] No human-decision authority changes
- [ ] No release/package integrity changes

If any box above is not checked, explain the change and why the new behavior remains fail-closed.

## Validation

List exact commands actually executed and their results. Use `NOT_RUN` for anything not executed.

```text
documentation integrity:
pytest:
Ruff:
mypy:
mypy --platform win32:
compileall:
package acceptance:
wheel SHA-256:
candidate stable after testing:
issue binding:
manual browser QA:
```

The repository policy is:

```text
GITHUB_ACTIONS = NOT_USED_BY_POLICY
LOCAL_EXACT_SHA_VERIFICATION = AUTHORITATIVE_ACCEPTANCE
MAIN_INTEGRATION = PULL_REQUEST_ONLY
REQUIRED_STATUS_CHECKS = NONE
MERGE_READINESS =
```

`GITHUB_ACTIONS = NOT_USED_BY_POLICY` is valid only when the verifier observes
no workflow file. A workflow file is a policy mismatch and keeps the gate on
hold. The local verifier also requires `--issue <N>` and an external report
path; runtime/package changes require exact-candidate external package evidence.

Unexecuted applicable gates must be `NOT_RUN`, never `PASS`.

## Data safety

- [ ] No proprietary/customer PDFs or parser outputs are committed.
- [ ] No user evidence databases/page-image caches/human decisions are committed.
- [ ] No credentials, tokens, private URLs, or private keys are committed.

## Review notes

Call out migrations, compatibility behavior, performance tradeoffs, and manual reviewer steps.

## Independent review

```text
Reviewed SHA =
Reviewer identity/role =
Mechanism =
Critical =
Important =
Disposition =
```
