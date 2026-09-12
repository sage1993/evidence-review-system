# Stabilization Closure Round 2 — forensic closure record

Issue: #167
Record date: 2026-09-12
Scope: documentation-only consolidation of the exact-main automated evidence and
the separately scoped MIG-20 real-environment record. This is not a release
attestation, publication, or a substitute for any outstanding gate.

## Candidate and scope

| Field | Value |
| --- | --- |
| Exact `main` / base SHA | `b7ed1b87bc2c4c6f5db616b3134a03f6efece6ee` |
| Platform | Windows (`win32`) |
| Python | `3.13.14` |
| Repository visibility | Public |
| Issue state | #167 is open pending its PR merge |

The prerequisite issue matrix is closed: #152–#166, #180–#190, #162, #163, and
#169 are all `CLOSED`. This status records issue state; it does not turn an
unexecuted acceptance gate into a pass.

## Exact-main automated evidence

The following commands were run from the exact SHA above unless a row says
otherwise.

| Command / gate | Result | Recorded evidence |
| --- | --- | --- |
| `py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output .ers-review-docs-issue167-main.json` | `PASS` | 54 documents: 25 current, 27 historical, 2 generated; 0 errors; 150 warnings. The ignored task-local plan existed during this baseline run and has since been removed. The generated report was removed after recording SHA-256 `2DA65318333534D68FC8FD5048F31DAD23AFE3057BC38ABB5E341595DC09E059`. |
| Candidate closure report draft: `py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output .ers-review-docs-issue167-postreview.json` | `PASS` (pre-commit draft) | 54 documents: 26 current, 26 historical, 2 generated; 0 errors; 151 warnings. The generated output was removed. Repeat on the clean committed PR-head SHA; record its exact output SHA-256 in the PR acceptance evidence. |
| `py -3.13 -m pytest -v` (baseline run started from this SHA) | `PASS, but NOT_ACCEPTED as candidate gate` | `2246 passed, 1 skipped, 1 warning in 651.91s`. The report draft was added while this run was in progress, so the worktree ceased to be clean. The warning was Pillow's corrupt-EXIF warning from the malformed TIFF decoder test. This result is retained as baseline only; a full run from the clean committed PR-head SHA is required and must be recorded in the PR acceptance evidence before merge. |
| `py -3.13 -m ruff check src tests web_runtime` | `PASS` | Exact-main static check. |
| `py -3.13 -m mypy src` | `PASS` | 270 files. |
| `py -3.13 -m mypy --platform win32 src` | `PASS` | 270 files. |
| `py -3.13 -m compileall -q src scripts web_runtime tests` | `PASS` | Exact-main bytecode compilation. |
| `py -3.13 scripts/validate_release.py $releaseWorkspace --run-id $runId --output (Join-Path $releaseWorkspace 'release-validation.json')` | `PASS` | Actual validator CLI on the isolated reproducible workspace created by the helper command below; observed run ID `RUN-D337BEB6AABA73CE4868`; report SHA-256 `861828831EC4331C842A72C5A2FBE0EBE380E85567FFC8519D1DBFCF95050A0B`. The fixture was cleaned. This is not a real user workspace, publication, or release-readiness attestation. |

The fixture and CLI were invoked from the repository root with:

```powershell
$taskScratchRoot = Join-Path $env:TEMP 'ers-issue167-release-validation-b7ed1b87'
$releaseWorkspace = Join-Path $taskScratchRoot 'workspace'
$env:PYTHONPATH = (Join-Path (Get-Location) 'src') + ';' + (Join-Path (Get-Location) 'tests')
$runId = py -3.13 -c "import sys; from pathlib import Path; from tests.integration.release.test_no_network_runtime import _workspace; print(_workspace(Path(sys.argv[1])))" $releaseWorkspace
py -3.13 scripts/validate_release.py $releaseWorkspace --run-id $runId --output (Join-Path $releaseWorkspace 'release-validation.json')
```

## Inherited MIG-20 real-environment evidence and limits

The [MIG-20 ReviewMatter acceptance report](REVIEW_MATTER_ACCEPTANCE_2026-09-08.md)
records real-environment evidence at candidate
`806b9ecf8b5d24b980233d79a91418f8893e97c7`, not at current `main`
`b7ed1b87bc2c4c6f5db616b3134a03f6efece6ee`. The following facts are inherited
from that candidate and have **not** been rerun for this exact-main record:

- The protected browser matrix passed at `1366×768`, `1920×1080`, and
  `3840×2160` for Workbench, Formal Review, and the 17-page `CASE_DRAWING`
  flow; keyboard/focus, print, console, protected-token, decision, and detached
  lifecycle checks were also recorded there.
- The 17-page drawing source hash was verified in the inherited acceptance
  record. Its hash and filename are omitted here to avoid publishing
  user-workspace source metadata; no source bytes are reproduced.
- The Formal Review display recorded seven evidence citations and a verified
  reference page. A read-only recheck on 2026-09-12 resolved the missing
  source-to-packet identity: the repository-bound workspace returned
  `ACTIVE`. The source-batch manifest and preserved reference source, database
  revision, page-52 citation, and finalized packet were cross-checked for
  consistent identity. Source filename, workspace path, hashes, and local
  run/document/citation identifiers are intentionally omitted from this public
  record to avoid disclosing user-workspace artifact metadata; those values
  were checked locally.
  The finalized machine packet was `READY_FOR_HUMAN_REVIEW`, not a human
  approval; its `human_decision` remains null. The browser interaction itself
  remains inherited from candidate `806b9ecf...`; this source-lineage check did
  not rerun the browser at current `main`.
- The inherited wheel/runtime smoke used
  `evidence_review_system-0.2.0-py3-none-any.whl`, SHA-256
  `889363c481b7efb51cf5f19a4fd4d6759f42d20757096575fd8d16f45d81d217`.
  The inherited prepared-workspace database and Formal Review print-PDF hashes
  were verified locally but are omitted because they identify user-workspace
  artifacts.
- The inherited automated suite result was `2245 passed, 1 skipped, 1 warning
  in 598.99s`. It must not be substituted for the current exact-main full
  pytest gate.

## Release-state and repository controls

Source authority in `pyproject.toml` is the candidate version `0.2.0rc1`.
The changelog and security material agree that it is unreleased. The latest
official GitHub release remains `v0.1.0`; no `v0.2.0` tag or publication was
created or is authorized by this closure record.

For this exact base SHA, GitHub Actions is `ACTIONS_NOT_RUN`: the observed
state was 0 workflow runs, 0 check-runs, and 0 statuses. This is an observation,
not a pass.

`main` protection was verified under #162 / PR #221: pull request required,
administrators enforced, 0 required approvals, no bypass, 0 required status
checks, and force push and branch deletion disabled.

## Closure decision

`HOLD` at report preparation. The inherited real-environment evidence now has
an independently verified text-source-to-packet lineage, but none of the
inherited browser or CASE_DRAWING results is represented as rerun at current
`main`. Issue #167 must remain open until the clean committed PR-head full
pytest gate and final candidate documentation validation are recorded as
passing in the PR acceptance evidence, the documentation change receives the
required independent review, and the PR is merged under the repository policy.
The inherited MIG-20 evidence is not represented as a rerun at
`b7ed1b87bc2c4c6f5db616b3134a03f6efece6ee`.
