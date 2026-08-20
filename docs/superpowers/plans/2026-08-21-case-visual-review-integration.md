# CASE Visual Review Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route user-provided drawing/image attachments through a validated case-visual evidence path, preserve the existing formal-review pipeline, and render issue locations over the actual source image/PDF page in the final Review Workspace.

**Architecture:** Keep normative `REFERENCE_DOCUMENT` ingestion and case-specific visual evidence as separate authority tracks. Bind `CASE_DRAWING` / `SUPPORTING_IMAGE` identity into `review-request.inputs`, create a validated external visual-analysis handoff that yields source-bound `DrawingCandidate` geometry, expose candidate lineage to Track A without treating drawings as legal authority, and project validated candidates into the existing Review Workspace.

**Tech Stack:** Python 3.13, pytest, argparse CLI, immutable JSON artifacts, existing Evidence Review System drawing contracts/renderers.

**Spec:** Approved conversation design for CASE visual review integration, 2026-08-21.

## Global Constraints

- Work directly from the current repository architecture; do not create ReviewPacket v3.
- A PDF file is not automatically a `REFERENCE_DOCUMENT`; routing follows the user-declared purpose/role.
- `CASE_DRAWING` PDF must never require OpenDataLoader reference ingestion or parser reproducibility as a prerequisite for visual review.
- `REFERENCE_DOCUMENT` parsing behavior must remain unchanged.
- Question text is not visual evidence. Only validated visual-analysis output may create drawing candidates.
- Visual analysis may record observations and geometry, but must not create legal conclusions, calculation results, or rule outcomes.
- Unconfirmed drawing candidates cannot bind deterministic Math/Rule inputs.
- Existing no-attachment compound-question behavior and request shape must remain unchanged.
- All source/page/geometry lineage must be hash-bound and fail closed.

---

### Task 1: Lock routing regressions with tests

**Files:**
- Create: `tests/unit/review_question/test_case_visual_routing.py`
- Create: `tests/integration/test_case_visual_formal_review.py`

**Interfaces:**
- Consumes: existing `ImmutableAttachment`, `compute_run_id_from_request`.
- Produces: executable expectations for `bind_case_visual_context_to_review_request()`.

- [ ] Write tests proving CASE_DRAWING PDF and SUPPORTING_IMAGE bind to visual context only.
- [ ] Write rejection test for REFERENCE_DOCUMENT entering case-visual context.
- [ ] Write no-attachment compatibility test.
- [ ] Write test proving question prose cannot create visual candidates.
- [ ] Write deterministic Run ID tests for visual source hash changes.
- [ ] Run focused tests and confirm they fail before implementation.
- [ ] Commit as `test: lock case visual review routing behavior`.

### Task 2: Separate Codex skill routing

**Files:**
- Modify: `.agents/skills/ers-review/SKILL.md`
- Modify: `.agents/skills/ers-pdf/SKILL.md`
- Modify: `.agents/skills/TESTS.md`

**Interfaces:**
- Consumes: attachment roles `REFERENCE_DOCUMENT`, `CASE_DRAWING`, `SUPPORTING_IMAGE`.
- Produces: explicit skill routing contract.

- [ ] Narrow `$ERS_PDF` to REFERENCE_DOCUMENT corpus preparation.
- [ ] Add explicit CASE_DRAWING/SUPPORTING_IMAGE visual-review route to `$ERS_REVIEW`.
- [ ] Add activation examples for reference PDF versus visual PDF/image requests.
- [ ] Commit as `fix: separate case drawings from reference pdf parsing`.

### Task 3: Bind case visual attachments to formal review

**Files:**
- Create: `src/evidence_review/case_visual.py`
- Modify: `src/evidence_review/planned_review_question.py`
- Modify: `src/evidence_review/question_planner_cli.py`
- Modify: `src/evidence_review/cli_parser.py`

**Interfaces:**
- Produces: `bind_case_visual_context_to_review_request(request, attachments, drawing_candidates=...) -> dict[str, object]`.
- CLI adds repeatable `--case-drawing` and `--supporting-image` arguments.

- [ ] Implement canonical visual context binding under `inputs.case_visual_context`.
- [ ] Preserve exact request when attachments are empty.
- [ ] Ingest visual files through existing immutable drawing intake, never reference source-batch ingestion.
- [ ] Bind attachment hashes before Run ID computation.
- [ ] Run Task 1 tests and planned-review regression tests.
- [ ] Commit as `feat: bind case visual attachments to planned reviews`.

### Task 4: Add validated external visual-analysis handoff

**Files:**
- Create: `src/evidence_review/contracts/visual_review.py`
- Create: `src/evidence_review/drawing_review/visual_handoff.py`
- Create: `src/evidence_review/drawing_review/visual_submission.py`
- Create: `src/evidence_review/llm_layer/templates/visual-analysis.md`
- Create: focused contract/handoff/submission tests.

**Interfaces:**
- Produces immutable `visual-analysis-bundle.json`, instructions, expected output path, and validated `DrawingCandidate` records.

- [ ] Define strict visual observation/output contract.
- [ ] Bind each observation to attachment hash, page, coordinate system and geometry.
- [ ] Reject nonexistent pages, source mismatches and out-of-bounds geometry.
- [ ] Keep legal conclusions/rule outcomes out of visual output.
- [ ] Commit as `feat: add validated visual analysis handoff`.

### Task 5: Bind visual lineage to Track A

**Files:**
- Modify: `src/evidence_review/llm_layer/track_a.py`
- Modify: `src/evidence_review/llm_layer/templates/track-a.md`
- Modify: `src/evidence_review/llm_layer/validators.py`
- Create: `tests/unit/llm_layer/test_track_a_visual_lineage.py`

**Interfaces:**
- Track A may reference validated `drawing_candidate_ids` as case facts; normative citations remain independently required for legal authority.

- [ ] Allow known candidate references.
- [ ] Reject unknown/cross-source candidates.
- [ ] Prevent visual candidates from replacing normative citation authority.
- [ ] Preserve old Track A behavior with no visual context.
- [ ] Commit as `feat: bind visual evidence lineage to track a claims`.

### Task 6: Render actual visual findings in Review Workspace

**Files:**
- Modify: `src/evidence_review/review_packet/builder.py`
- Modify: `src/evidence_review/review_packet/drawing_evidence.py`
- Modify: `src/evidence_review/review_packet/html_renderer.py`
- Create: `tests/unit/review_packet/test_case_visual_workspace.py`

**Interfaces:**
- Reuse existing page-image + SVG geometry renderer as a main-workspace fragment.

- [ ] Render actual source page/image with candidate overlay only when visual evidence exists.
- [ ] Link finding selection to page/geometry and related normative evidence.
- [ ] Keep non-spatial findings in text-only review sections.
- [ ] Derive overlay tone only from validated rule/coverage states; do not invent visual verdicts.
- [ ] Keep no-visual workspace layout unchanged.
- [ ] Commit as `feat: render case visual findings in review workspace`.

### Task 7: Isolate visual blockers from normative parser blockers

**Files:**
- Modify: `src/evidence_review/abstention/finalizer.py`
- Modify: `src/evidence_review/review_run.py` as required by run-local visual artifacts.
- Add focused finalizer tests.

**Interfaces:**
- Visual failures use `VISUAL_SOURCE_RENDER_FAILED`, `VISUAL_ANALYSIS_REQUIRED`, or `INPUT_CONFIRMATION_REQUIRED`; reference retrieval failures remain separate.

- [ ] Ensure CASE_DRAWING does not produce `PARSER_SOURCE_PDF_INVALID` as a visual blocker.
- [ ] Scope visual failure to dependent issues where possible.
- [ ] Preserve existing REFERENCE_DOCUMENT parser failures.
- [ ] Commit as `fix: isolate visual evidence failures from reference parsing`.

### Task 8: Full acceptance validation

**Files:**
- Add/update integration fixtures and tests only as needed.

- [ ] Re-run three existing compound-question scenarios.
- [ ] Run one PNG visual question.
- [ ] Run one CASE_DRAWING PDF visual question.
- [ ] Run one REFERENCE_DOCUMENT PDF regression.
- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m ruff check src tests`.
- [ ] Run `python -m mypy src/evidence_review`.
- [ ] Run `python -m compileall -q src`.
- [ ] Record any environment limitations without converting unexecuted validation to PASS.
