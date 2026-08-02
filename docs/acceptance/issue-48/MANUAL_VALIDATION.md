# Issue #48 Manual Rule Activation Governance Validation

## A. Basis

- Repository: `sage1993/evidence-review-system`
- Worktree: `F:\evidence-review-system-rule-governance-rerun`
- Remote branch: `origin/agent/rule-activation-governance`
- Starting HEAD: `0c36d7faec96310e34a6d81f27c68a2623896919`
- Final validated code HEAD: `29e110119b9f93436631a165e1fcb732fcfb8e5f`
- Worktree mode: detached HEAD
- Windows: `Microsoft Windows [Version 10.0.26200.8875]`
- Python 3.13: `3.13.14`
- Python 3.11: `3.11.9`
- Validation time: `2026-08-03T01:47:35+09:00`
- Timezone: `Korea Standard Time`

Environment setup command ledger:

- `py -3.13 -m venv .venv`: exit `0`.
- `python -m pip install --upgrade pip`: exit `0`.
- `python -m pip install -e ".[dev]"`: exit `0`.
- `python -m pip install build`: exit `0`.

The original worktree, the previous validation worktree, and their existing user
changes were preserved. The inherited `docs/acceptance/issue-46/` modifications were
not staged or changed. The previous failed acceptance commit `58bc6ad` was preserved
by backup branch `backup/issue48-manual-fail-58bc6ad` and was not cherry-picked.

## B. Overall decision

**MANUAL_PASS / ACTIONS_BILLING_BLOCKED**

Local manual acceptance is complete for validated code HEAD `29e1101`. GitHub Actions
was unavailable because of the repository billing/spending limit
(`ACTIONS_BILLING_BLOCKED`). This report must not be read as a GitHub Actions PASS. PR
merge, Ready-for-review transition, and Issue #48 closure were not performed during
validation.

## C. Previous three failures

The three previously failing acceptance cases were revalidated after minimal fixes:

| Case | Result | Fix/root cause |
|---|---|---|
| `test_write_failure_does_not_delete_concurrent_replacement` | PASS | The remote branch's Windows-safe test setup now closes the handle before simulating the competing replacement. |
| `test_legacy_manifest_is_blocked_without_fallback` | PASS | The governed loader now reports `RULE_GOVERNANCE_LEGACY_MANIFEST`. |
| `test_zip_member_paths_must_be_canonical_posix[folder\\file.txt]` | PASS | The verifier validates `ZipInfo.orig_filename`, preserving raw archive names before Python's normalized `filename` view. |

The local code fix was committed as `29e1101 fix: validate raw archive member paths`.
No tracked golden, approval, or active-manifest artifact was changed.

## D. Full pytest

All commands used worktree-local `--basetemp` directories to avoid unrelated global
pytest cleanup permissions. stdout, stderr, and exit-code metadata are preserved under
`build/manual-validation/logs/`.

| Command | Exit code | Result |
|---|---:|---|
| `python -m pytest -v --basetemp=build/manual-validation/pytest-tmp-full` | 0 | 713 passed, 2 skipped, 44.00s |
| `python -m pytest -q --basetemp=build/manual-validation/pytest-tmp-post-doc-full-final-2` | 0 | 713 passed, 2 skipped, 44.42s; final post-documentation rerun |
| `python -m pytest -q --basetemp=build/manual-validation/pytest-tmp-post-doc-rule-engine-final tests/unit/rule_engine tests/integration/rule_engine` | 0 | 135 passed, 1 skipped, 2.60s; final post-documentation rerun |
| `python -m pytest -q --basetemp=build/manual-validation/pytest-tmp-post-doc-workspace-final tests/integration/test_workspace_validator.py` | 0 | 3 passed, 0.30s; final post-documentation rerun |

The fast gate also passed: 25 focused tests passed, including tamper, entrypoint, and
release path coverage. The initial sandbox-only rerun could not create a new temporary
directory (`WinError 5`); the final commands above were rerun with normal Windows
filesystem permissions and are the authoritative post-documentation results.

Fast-gate command ledger: the focused pytest command, `python -m ruff check src tests`,
`python -m mypy src`, and `python -m compileall -q src scripts web_runtime tests` each
exited `0` after the minimal fix.

## E. Ruff, mypy, and compileall

- `python -m ruff check src tests`: exit 0, **PASS**.
- `python -m mypy src`: exit 0, **PASS**; 127 source files checked.
- `python -m compileall -q src scripts web_runtime tests`: exit 0, **PASS**.

## F. Golden 6/13

All six tracked fixture manifests were executed with each tracked report's
`source_commit` and `command`.

- Fixture manifests: **6/6 PASS**.
- Golden cases: **13/13 PASS**.
- Failed cases: `0`.
- Generated report bytes equal tracked report bytes: **PASS for all 6**.
- Actual bytes equal expected bytes: **PASS for all 13**.
- `actual_sha256 == expected_sha256`: **PASS for all 13**.

Generated reports are under `build/manual-validation/golden-reports/`; actuals are under
`build/rules/golden/actual/`.

The six invocations of `evidence-review.exe rules run-golden` used the tracked fixture
manifest, `source_commit`, and command fields; all six exited `0`.

## G. Activation 6/6

- CLI exit code: `0`.
- Status: `ACTIVATED`.
- Approval count: `6`.
- Activated rule count: `6`.
- Findings: `[]`.
- Generated active manifest bytes equal `rules/manifests/active.json`: **PASS**.
- Generated activation report bytes equal
  `docs/acceptance/issue-48/activation-report.json`: **PASS**.
- Active manifest SHA-256:
  `c4d41a402d39fea712a7ba6d80568595ef7be6fc1acc9cb63416b8c75020af76`.

`evidence-review.exe rules build-active-manifest` exited `0`; both
`evidence-review.exe rules select` invocations exited `0`.

## H. Runtime selection

- ANSIM context: exit `0`, `SELECTED`, exactly `6` selected rules, zero exclusions,
  zero reasons; generated bytes equal the tracked ANSIM selection artifact.
- Non-ANSIM context: exit `0`, `ABSTAIN`, zero selected rules, six `SCOPE_MISMATCH`
  exclusions, reason exactly `NO_APPLICABLE_ACTIVE_RULE`; generated bytes equal the
  tracked abstention artifact.
- Installed-wheel selection under both Python 3.13 and Python 3.11 produced the same
  non-ANSIM `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE` result.

## I. Tamper matrix

The focused tamper/entrypoint/CLI run passed **25/25** tests. It covered active
manifest, approval, golden report, candidate, approved rule, fixture manifest,
fixture, expected bytes, path traversal, duplicate rule IDs, symlinks, duplicate JSON
keys, canonical CLI behavior, and blocked exit behavior.

Partial fallback was not observed. Candidate directories and unmanifested approved
rules were not scanned. Normal scope mismatch remained `ABSTAIN`; `BLOCKED` was not
downgraded to `ABSTAIN`.

The tamper/entrypoint/CLI pytest command exited `0`; all 25 collected tests passed.

## J. Wheel 3.13/3.11

- `python -m build --wheel`: exit `0`; wheel built as
  `dist/evidence_review_system-0.1.0-py3-none-any.whl`.
- Python 3.13 wheel venv: install, `evidence-review`, `rules --help`, `ansim-review`,
  module help, canonical resources, and installed-wheel selection all exited `0`.
- Python 3.11 wheel venv: the same checks all exited `0`.
- Canonical resources resolved from the installed wheel:
  `ansim_review/evidence/schema.sql`, `ansim_review/llm_layer/templates/`, and
  `ansim_review/review_packet/assets/`.
- No `PYTHONPATH` or source-checkout import path was used for installed-wheel checks.

## K. Acceptance documents and commits

This document and `README.md` were written from the new passing rerun; commit
`58bc6ad` was not cherry-picked.

- Code fix: `29e1101 fix: validate raw archive member paths`.
- Initial passing acceptance record: `5425150 docs: record passing manual rule governance validation`.
- Command and exit-code ledger: `3c61cf5 docs: record passing manual rule governance validation`.

The full post-documentation validation listed above passed before the acceptance
commits were pushed. Later wording-only consistency corrections do not modify the
validated runtime code, golden artifacts, approvals, or active manifest. The current
branch must pass the documentation test, Ruff, mypy, and compileall before integration.

## L. Push, PR, and Issue status

- Push: completed through remote commit `3c61cf5fdc5708996bbcac30e642c9ba361d8f73` before wording-only consistency corrections.
- Wording-only consistency corrections were pushed after `3c61cf5`; the remote Git history is the authoritative final-head record.
- PR #49: remained Draft and was not merged during validation.
- Issue #48: remained open during validation.
- GitHub Actions: unavailable due `ACTIONS_BILLING_BLOCKED`; no CI PASS is claimed.

## M. Unverified items and limitations

- `reviewer_id` is an auditable field in the approval artifact, but reviewer identity
  is not cryptographically verified by this workflow.
- Machine rule results are not human legal decisions. Final legal judgment remains a
  human responsibility and is not claimed by this acceptance report.
- Grist Desktop screen acceptance is not applicable to this PR #49 rule-governance
  rerun; this is a local rule-engine acceptance, not a PDF/Grist database build.
