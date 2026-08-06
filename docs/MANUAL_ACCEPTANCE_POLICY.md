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
- isolated Python 3.11 and 3.13 wheel/install smoke when the package is changed;
- browser or other human-facing QA when the change has a UI boundary; and
- relevant artifact SHA-256 values, platform, Python version, command, and exit
  code.

The acceptance record must state `ACTIONS_NOT_RUN` when Actions was deliberately
excluded, or `ACTIONS_BILLING_BLOCKED` when the service was unavailable because
of account billing or spending limits. Neither status is a GitHub Actions PASS.

This policy does not permit bypassing branch protection or an explicit
maintainer requirement for a particular external check. Such a check remains a
separate release or merge gate and must be reported separately from local
manual verification.
