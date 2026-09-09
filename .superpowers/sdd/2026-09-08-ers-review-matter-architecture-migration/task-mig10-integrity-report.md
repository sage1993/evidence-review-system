# MIG-10 prepared-artifact integrity — post-merge follow-up report

## Scope and root cause

Implemented only in
`F:/2026-PJ/evidence-review-system-test/.worktrees/mig-10-artifact-integrity`
on branch `fix/mig-10-prepared-artifact-integrity`.

The resumed `formalize_snapshot` path previously verified only these prepared
artifacts beyond the persisted request: `track-a-bundle.json` and
`confidence-input.json`. It therefore returned a resumed `WAITING_TRACK_A`
state even after `next-action-track-a.json` was replaced by
`{"tampered":true}`. The existing request, Track A bundle, and confidence
validation did not cover the rest of the deterministic preparation contract.

The fix now requires verified regular files and canonical expected contents for
all preparation-contract artifacts before the resume call reaches
`prepare_review_question_from_request`:

- `review-request.json` (existing strict request decoder);
- `track-a-bundle.json` (existing deterministic Track A builder);
- `confidence-input.json` (existing strict confidence decoder);
- `next-action-track-a.json` (existing strict next-action decoder and
  canonical next-action builder);
- `TRACK_A_INSTRUCTIONS.md` and `TRACK_B_INSTRUCTIONS.md` (exact bytes from
  their authoritative bundled templates);
- `prepare-status.json` (the same canonical status-document builder used when
  preparing a run).

The canonical instruction and preparation-status helpers were extracted into
`review_run.py` and used for both creation and resume validation. No authority
inputs, scope semantics, Track A/B behavior, finalizer behavior, packets,
human decisions, Matter history, or evidence were changed.

## TDD evidence

The regression test was added before production changes. It names the break it
catches: a resume implementation that verifies only Track A input artifacts.
It calls the public `formalize_snapshot` path and uses real prepared artifacts.

RED command:

```powershell
py -3.13 -m pytest -v --basetemp 'F:\2026-PJ\evidence-review-system-test\.worktrees\mig-10-artifact-integrity\pytest-mig10-red' tests/integration/review_matter/test_existing_formal_core_adapter.py
```

Exact result:

```text
4 failed, 15 passed in 12.45s
```

Each new parametrized case failed with the expected pre-fix condition:

```text
Failed: DID NOT RAISE ValueError
```

The four mutations were:

```text
next-action-track-a.json = {"tampered":true}
TRACK_A_INSTRUCTIONS.md = tampered
TRACK_B_INSTRUCTIONS.md = tampered
prepare-status.json = {"tampered":true}
```

GREEN command:

```powershell
py -3.13 -m pytest -v --basetemp 'F:\2026-PJ\evidence-review-system-test\.worktrees\mig-10-artifact-integrity\pytest-mig10-green' tests/integration/review_matter/test_existing_formal_core_adapter.py
```

Exact result:

```text
19 passed in 10.70s
```

This includes the existing deterministic same-snapshot resume test, which
remained green.

## Focused and adjacent verification

Command:

```powershell
py -3.13 -m pytest -v --basetemp 'F:\2026-PJ\evidence-review-system-test\.worktrees\mig-10-artifact-integrity\pytest-mig10-adjacent' tests/integration/review_matter/test_existing_formal_core_adapter.py tests/integration/review_matter/test_formalization_race.py tests/unit/review_matter/test_formalization_adapter.py tests/unit/review_question/test_track_a_submission.py tests/unit/review_question/test_track_b_handoff_support.py tests/integration/review_question/test_planned_question_flow.py tests/integration/review_run/test_review_run.py tests/integration/review_run/test_filesystem_trust_boundary.py tests/integration/review_run/test_review_run_cli.py
```

Exact result:

```text
72 passed in 25.40s
```

Static commands and exact outputs:

```powershell
py -3.13 -m ruff check src tests web_runtime
```

```text
All checks passed!
```

```powershell
py -3.13 -m mypy src
```

```text
Success: no issues found in 256 source files
```

```powershell
py -3.13 -m mypy --platform win32 src
```

```text
Success: no issues found in 256 source files
```

```powershell
py -3.13 -m compileall -q src scripts web_runtime tests
```

```text
(no output; exit code 0)
```

Documentation validation first exposed an environment selection issue, rather
than a source failure:

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output 'F:\2026-PJ\evidence-review-system-test\.worktrees\mig-10-artifact-integrity\documentation-integrity-mig10.json'
```

Exact result:

```text
status: SOURCE_MISMATCH
package_root: F:\2026-PJ\evidence-review-system\src\evidence_review
repository_root: F:\2026-PJ\evidence-review-system-test\.worktrees\mig-10-artifact-integrity
```

The authoritative source-worktree invocation then passed:

```powershell
$env:PYTHONPATH = 'src'; py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output 'F:\2026-PJ\evidence-review-system-test\.worktrees\mig-10-artifact-integrity\documentation-integrity-mig10-source.json'
```

Exact result:

```text
Documentation integrity: PASS
Documents: 50 current=22 historical=26 generated=2
Findings: errors=0 warnings=139
Report: documentation-integrity-mig10-source.json
```

## Exact-HEAD full acceptance

The first verbose full-suite invocation and an accidental duplicate quiet
invocation produced streaming output but not a retained final exit result; the
duplicate was stopped, and neither invocation is counted as acceptance. The
following single retained quiet invocation is the authoritative exact-HEAD
result:

```powershell
py -3.13 -m pytest -q --basetemp 'F:\2026-PJ\evidence-review-system-test\.worktrees\mig-10-artifact-integrity\pytest-mig10-full-final'
```

Exact final output and exit code:

```text
2033 passed, 1 skipped in 294.33s (0:04:54)
exit_code: 0
```

All generated pytest bases and generated documentation reports used above were
removed before commit.

## Diff self-review

Reviewed with:

```powershell
git diff --check
git diff -- src/evidence_review/review_matter/formalization.py src/evidence_review/review_run.py tests/integration/review_matter/test_existing_formal_core_adapter.py
```

`git diff --check` produced no whitespace errors. The review confirmed that:

- malformed, non-canonical, missing, and mismatched contract artifacts fail
  before a resumed `WAITING_TRACK_A` result is returned;
- valid deterministic resume is still covered and passes;
- the new next-action validation uses the existing decoder/document builder;
- the shared status and instruction builders prevent creation and validation
  from drifting;
- the change does not introduce a caller-controlled authority input or modify
  Matter/evidence/finalizer/Human Decision authority boundaries.

## Concerns / non-automated gates

- `ACTIONS_NOT_RUN`: no GitHub Actions were requested or run.
- Browser viewport/keyboard/print QA and protected/archival human-decision
  manual paths were not rerun; this narrow artifact-integrity change does not
  alter their code paths.
- The base interpreter initially resolved an unrelated installed source checkout
  for documentation validation. The source-worktree `PYTHONPATH=src` gate above
  is the recorded passing result.
- No push, PR operation, merge, or change outside the specified worktree was
  performed.
