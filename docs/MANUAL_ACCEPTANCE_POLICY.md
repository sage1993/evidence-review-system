# Manual Acceptance and Main-Merge Policy

## Default acceptance path

GitHub Actions is not an acceptance dependency for this repository. Issue and
pull-request work is verified locally from a clean checkout at the exact
implementation HEAD. GitHub Actions is not invoked as part of the normal issue
workflow, and a workflow that is not started or has no executed steps is never
reported as a PASS.

Before merging a change into `main`, the maintainer must complete and record the
applicable manual gates:

- exact commit and clean worktree;
- documentation integrity validation;
- full pytest, Ruff, strict mypy, and compileall;
- isolated Python 3.13 wheel/install smoke when the package is changed;
- browser or other human-facing QA when the change has a UI boundary; and
- relevant artifact SHA-256 values, platform, Python version, command, and exit
  code.

For changes that publish or read evidence databases, the acceptance record must
also show the finalized lifecycle (`FINALIZED`, finalization version, logical
snapshot/retrieval hash match, and SQLite integrity), the SHA-256 of the closed
published `evidence.sqlite`, that no SQLite WAL/SHM/journal sidecar is present,
and that this exact file hash is unchanged through the bound review lifecycle.
A logical snapshot hash may match across separate rebuilds without requiring
byte-identical SQLite files.

The acceptance record must state `ACTIONS_NOT_RUN` when Actions was deliberately
excluded, or `ACTIONS_BILLING_BLOCKED` when the service was unavailable because
of account billing or spending limits. Neither status is a GitHub Actions PASS.

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
