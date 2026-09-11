# MIG-15 implementation report

## Identity

- Issue: #185 / MIG-15
- Branch: `feat/mig-15-matter-visual-integration`
- Base SHA: `18aeab81fbfab52872a1cf63b7c8770241188bee`
- Commit SHA: `9f6cf3a9f238ba1fad1f95002f5c378867e793e0`
- Commit message: `feat(mig-15): bind visual review to ReviewMatter`

## Implementation

- Added `VisualCase` and `visual_case_from_attachments(...)` in `src/evidence_review/case_visual.py`. The constructor revalidates immutable attachment documents, requires one `case_id`, preserves direct attachment-id/source-hash identity, and never resolves by basename.
- Added `bind_visual_case_to_matter(...)` in `src/evidence_review/review_matter/visual_binding.py`. It pins an immutable visual context to the exact loaded Matter revision and validates every candidate against both visual `case_id` and source SHA. It returns no confirmed inputs and does not mutate confirmation, calibration, evidence, Formal Review, or Human Decision state.
- Preserved immutable candidate case provenance in `src/evidence_review/contracts/drawing.py` and populated it from the established drawing candidate constructors in `src/evidence_review/parsing/drawing_candidates.py`. Legacy artifacts without `case_id` remain decodable but fail closed when used for this new Matter visual binding.
- Preserved validated `ReviewScope` control context in visual-analysis handoff identity and bundle output, while retaining the existing QuestionPlan adapter. Added exact page attachment/source lineage validation before handoff creation.
- Added integration regressions for foreign source, same-source foreign case, same-basename direct attachment lineage, ReviewScope handoff context, MIME mismatch, and no candidate auto-promotion.

## Changed files

- `src/evidence_review/case_visual.py`
- `src/evidence_review/contracts/drawing.py`
- `src/evidence_review/parsing/drawing_candidates.py`
- `src/evidence_review/review_matter/visual_binding.py`
- `src/evidence_review/drawing_review/visual_handoff.py`
- `src/evidence_review/drawing_review/visual_pages.py`
- `tests/integration/review_matter/test_visual_binding.py`

## Scope rulings

- `SCOPE_EXPANSION_REQUIRED = YES` was recorded in `task-185-mig15-ledger.md` before changing the candidate contract. Reason: source SHA alone cannot distinguish candidates from two separate visual cases containing byte-identical sources. Candidate `case_id` lineage is therefore required to meet the fail-closed cross-case contract.
- The prior `VisualCase` value-object ruling was also recorded. `prepare_case_visual_sources(...)` retains its tuple return contract.

## RED / GREEN evidence

1. RED: `py -3.13 -m pytest -v tests/integration/review_matter/test_visual_binding.py`
   - Observed expected missing-contract collection failure: `ImportError: cannot import name 'visual_case_from_attachments'`.
2. GREEN after the initial boundary: focused suite passed `5 passed in 7.57s` outside the filesystem sandbox, required because sandboxed pytest could not create/clean Windows temporary directories.
3. Additional RED for identical bytes across different cases: focused suite observed `1 failed, 5 passed`; `test_visual_candidate_from_other_case_with_same_source_cannot_bind` failed because the old candidate shape had no case lineage and did not raise.
4. GREEN after candidate `case_id` provenance: focused suite passed `6 passed in 7.81s`; final focused rerun passed `6 passed in 0.85s`.

## Verification

- Focused: `py -3.13 -m pytest -v tests/integration/review_matter/test_visual_binding.py` — PASS, `6 passed in 0.85s`.
- Adjacent: `py -3.13 -m pytest -v tests/unit/parsing/test_drawing_candidates.py tests/unit/parsing/test_drawing_confirmation.py tests/unit/parsing/test_drawing_inputs.py tests/unit/drawing_review/test_visual_handoff.py tests/unit/drawing_review/test_visual_source_authority.py tests/unit/drawing_review/test_visual_submission.py tests/integration/test_case_visual_formal_review.py tests/integration/drawing/test_manual_annotation_flow.py` — PASS, `68 passed in 1.48s`.
  - One existing expected warning was emitted by Pillow for the deliberately corrupt TIFF fixture: `Corrupt EXIF data`.
- Static checks: `py -3.13 -m ruff check src/evidence_review/case_visual.py src/evidence_review/contracts/drawing.py src/evidence_review/parsing/drawing_candidates.py src/evidence_review/review_matter/visual_binding.py src/evidence_review/drawing_review/visual_handoff.py src/evidence_review/drawing_review/visual_pages.py tests/integration/review_matter/test_visual_binding.py` — PASS.
- Type check: `py -3.13 -m mypy src` — PASS, `Success: no issues found in 266 source files`.
- Final repository checks after commit: `git rev-parse HEAD` returned `9f6cf3a9f238ba1fad1f95002f5c378867e793e0`; `git status --short`, `git diff --check`, and `git diff --cached --check` were clean.
- The documented 17-page CASE_DRAWING-specific regression was searched for but is not present as a dedicated existing test in this checkout: `NOT_PRESENT`.

## NOT_RUN

- Full Python 3.13 pytest suite.
- Full repository Ruff, documentation validation, compileall, and Windows-platform mypy.
- Browser viewport/manual QA, protected/archival decision paths, server lifecycle acceptance, wheel/runtime smoke, and GitHub Actions.
- Push, remote SHA verification, and PR creation.

## Concerns

- The exact new binding intentionally fails closed for legacy candidate artifacts that lack `case_id`; these remain readable and retain existing confirmation behavior, but cannot establish the new Matter visual lineage until regenerated or explicitly migrated through an approved path.
- Sandboxed pytest creates inaccessible Windows temporary reparse artifacts in this environment. Verification was rerun outside the filesystem sandbox; the nine resulting test-only directories were removed before final Git status verification.

## Fix round 1 — review remediation

### Commit

- Fix commit SHA: `12f8543a4d64d9974497c667c28a9867b82d1d39`
- Fix commit message: `fix(mig-15): enforce Matter visual source lineage`

### Findings addressed

- P1 Matter/source lineage: `bind_visual_case_to_matter(...)` now requires a complete attachment-id → existing Matter source-binding-id map. It validates every requested binding ID against the loaded Matter's exact `source_hash` and records the selected Matter binding ID in each returned `VisualAttachmentBinding`. A visual case cannot bind to a Matter whose selected source binding has a different source hash.
- P1 candidate lineage: visual-analysis submission and deterministic drawing extraction now set `DrawingCandidate.case_id`. The active request binder rejects missing candidate case IDs, foreign candidate case IDs, and page/attachment case mismatch before request construction.
- P2 coverage: added regressions for wrong Matter source binding, same-source foreign case in active request binding, producer-preserved `case_id`, and end-to-end visual submission through active request binding with identical basenames in separate visual cases.

### Round-1 RED / GREEN evidence

1. RED: `py -3.13 -m pytest -v tests/integration/review_matter/test_visual_binding.py tests/unit/drawing_review/test_visual_submission.py tests/unit/parsing/test_drawing_extractors.py`
   - Result: `4 failed, 10 passed in 1.21s`.
   - Failures were the missing `expected_source_binding_ids` contract, active request binder accepting a foreign same-source case, and both production candidate producers returning `case_id=None`.
2. GREEN focused: the same command passed `15 passed in 1.03s` after the remediation and end-to-end regression.
3. GREEN adjacent: `py -3.13 -m pytest -v tests/unit/parsing/test_drawing_candidates.py tests/unit/parsing/test_drawing_extractors.py tests/unit/parsing/test_drawing_confirmation.py tests/unit/parsing/test_drawing_inputs.py tests/unit/drawing_review tests/unit/review_question/test_case_visual_intake.py tests/unit/review_question/test_case_visual_routing.py tests/integration/test_case_visual_formal_review.py tests/integration/drawing/test_manual_annotation_flow.py` passed `109 passed in 2.36s`.
   - The existing deliberately corrupt TIFF fixture emitted one Pillow `Corrupt EXIF data` warning.
4. Static: focused Ruff passed; `py -3.13 -m mypy src` passed with `Success: no issues found in 266 source files`.

### Round-1 concerns / NOT_RUN

- Legacy candidate artifacts without `case_id` remain readable but fail closed for new Matter and active-request visual lineage, as required.
- Callers of `bind_visual_case_to_matter(...)` must supply the complete expected attachment-to-Matter-source-binding map; omitting it fails closed.
- Full pytest, full Ruff/documentation/compileall/Windows-platform mypy, browser/manual, lifecycle, packaging, Actions, push, and PR gates remain `NOT_RUN`.

## Final broad-review fix wave

- Fix commit message: `fix(mig-15): preserve exact visual attachment lineage`

### Findings addressed

- P1 exact attachment lineage: `DrawingCandidate` now carries optional, validated `attachment_id` provenance. New visual-analysis, raw-element, and staged-extractor producers propagate it when available; `validate_visual_analysis_output(...)` always emits the exact observation attachment. New Matter and active-request visual binding reject candidates without an exact attachment ID or whose attachment/case/source/page tuple is not bound. Candidate documents serialize `attachment_id`, and the packet projection resolves pages by `(attachment_id, page)` rather than `(source_sha256, page)`.
- P1 same-SHA regression: one visual case may now contain differently named/role attachments with byte-identical sources and distinct Matter source-binding IDs. The regression verifies exact Matter mapping, active-request serialization, and distinct projection pages/candidates without source-hash ambiguity.
- P2 canonical identity: `visual_case_from_attachments(...)` reconstructs each deterministic attachment descriptor and rejects forged attachment IDs or case IDs. The Matter binder also rejects a `VisualCase.case_id` equal to its target `matter_id` before accepting the context.

### RED / GREEN evidence

1. RED: `py -3.13 -m pytest -q tests/integration/review_matter/test_visual_binding.py tests/unit/drawing_review/test_visual_submission.py tests/unit/parsing/test_drawing_extractors.py tests/unit/parsing/test_drawing_candidates.py tests/unit/review_packet/test_case_visual_projection.py`
   - Result: `11 failed, 24 passed in 1.71s`.
   - Failures demonstrated absent `attachment_id` production/serialization, binders accepting only case/source identity, and `VisualCase` accepting forged deterministic IDs.
2. Minimal GREEN: the same focused command passed `36 passed in 1.45s` after exact attachment and canonical identity implementation.
3. Focused affected-path rerun: `py -3.13 -m pytest -q tests/unit/review_packet/test_case_visual_projection.py tests/unit/review_packet/test_issue_119_related_reference_formal_shape.py tests/unit/review_packet/test_issue_119_related_reference_routing.py tests/unit/review_packet/test_issue_119_visual_hardening.py tests/integration/review_matter/test_visual_binding.py tests/unit/drawing_review/test_visual_submission.py tests/unit/parsing/test_drawing_extractors.py tests/unit/parsing/test_drawing_candidates.py` — PASS, `49 passed in 2.06s`.
4. Adjacent: `py -3.13 -m pytest -q tests/unit/parsing tests/unit/drawing_review tests/integration/drawing tests/integration/review_matter tests/unit/review_packet` — PASS, `493 passed, 1 warning in 55.00s`.
   - The sole warning is the pre-existing deliberately malformed TIFF fixture: Pillow `Corrupt EXIF data`.
5. Static: targeted `py -3.13 -m ruff check` over all changed production and regression files — PASS, `All checks passed!`; `py -3.13 -m mypy src` — PASS, `Success: no issues found in 266 source files`; `git diff --check` — PASS.

### Final-wave concerns / NOT_RUN

- Legacy `DrawingCandidate` documents without `attachment_id` remain decodable, including legacy confirmation paths. They fail closed for new Matter binding, active visual request binding, and validated visual projection because no exact attachment can be proven.
- Full repository pytest, full Ruff/documentation/compileall, browser/manual, lifecycle, packaging, Actions, push, and PR gates remain `NOT_RUN` for this fix wave.
