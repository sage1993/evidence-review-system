# Release Version Policy

## Authority

Public repository governance uses GitHub for source, issue, pull-request, and
release management. It does not use GitHub Actions:

```text
GITHUB_ACTIONS = NOT_USED_BY_POLICY
LOCAL_EXACT_SHA_VERIFICATION = AUTHORITATIVE_ACCEPTANCE
MAIN_INTEGRATION = PULL_REQUEST_ONLY
```

Release or merge readiness must come from local exact-SHA verification. PR
creation is not acceptance, and the tested, committed, pushed, and PR-head SHAs
must be identical. A missing or mismatched identity is `MERGE_READINESS = HOLD`.

`pyproject.toml` is the authority for the source package version. A PEP 440
pre-release value in source metadata identifies a candidate only; it is not
proof that a public release has been published. Changelog dates and security
support statements likewise do not make an unpublished version final.

A public version exists only when a GitHub Release has been published and its
tag resolves to the exact validated commit. The source version, release tag,
and publication state must not be inferred from one another.

## Publication evidence

Before publication, the pull request evidence records the exact commit SHA,
verification states, and applicable artifact SHA-256 values. After
publication, verify the GitHub Release, tag SHA, and artifact hashes together
against that evidence and the exact validated commit.

The canonical local pre-PR command is:

```powershell
py -3.13 scripts/repository_gate.py --issue <N> --json-report "$env:TEMP\ers-repository-gate-<N>.json"
```

Historical acceptance records that say `ACTIONS_NOT_RUN` remain unchanged;
they are historical evidence and not a current Actions status.
