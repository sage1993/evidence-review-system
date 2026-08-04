# Codex Review Orchestration Tasks 5–9 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the merged review foundation, drawing confirmation lane, deterministic engines, file-based Track A/Track B handoff, browser routes, resumable execution, and operator documentation into one fail-closed offline review run.

**Architecture:** Extend the existing `ansim_review.workflow` package with a single orchestration coordinator that owns state transitions and writes create-only artifacts. Drawing confirmation remains an input gate; retrieval, Math, and Rule execute in that order, while Track A/Track B remain external file actions validated by the existing finalizer. The web runtime serves only confirmation and final-review views from immutable run artifacts and never emits a human decision.

**Tech Stack:** Python 3.11+, standard library runtime, SQLite evidence store, pytest, canonical JSON, existing Math/Rule/Retrieval/Review Packet contracts, localhost-only web runtime.

## Global Constraints

- Preserve original PDFs and raw parser artifacts; all run artifacts are create-only and hash-bound.
- Project runtime stays offline and must not call remote APIs or external search services.
- Deterministic retrieval, Math, Rule, confidence, abstention, and finalization remain machine artifacts; Track A and Track B are untrusted external file inputs.
- `human_decision` remains null; `READY_FOR_HUMAN_REVIEW` means human review is still required.
- Existing Review Packet v1 and foundation workflow contracts remain backward compatible.
- Every deterministic artifact stores the request/evidence/rule/formula version identity and SHA-256 needed for resume and byte-equivalence checks.

---

### Task 5: Drawing confirmation orchestration

**Files:**
- Create: `src/ansim_review/workflow/drawing_confirmation.py`
- Modify: `src/ansim_review/workflow/orchestrator.py`
- Modify: `src/ansim_review/workflow/run_layout.py`
- Test: `tests/unit/workflow/test_drawing_confirmation_orchestration.py`
- Test: `tests/integration/workflow/test_drawing_confirmation_resume.py`

**Interfaces:**
- Consumes: `ReviewRunLayout`, `ReviewRequest`, `CaseManifestEntry`, `project_drawing_workflow`, `bind_confirmed_inputs`.
- Produces: `DrawingConfirmationResult(state, candidate_urls, confirmation_path, confirmed_inputs_sha256)` and `resume_after_confirmation(layout)`.

- [ ] **Step 1: Write the failing test**

```python
def test_case_drawing_stops_before_engines_and_returns_confirmation_url(tmp_path):
    layout = prepared_request_with_case_drawing(tmp_path)
    result = start_drawing_lane(layout)
    assert result.workflow_state == "INPUT_CONFIRMATION_REQUIRED"
    assert result.candidate_urls == ("/runs/{}/confirmation".format(layout.run_id),)
    assert not (layout.run_dir / "calculation-result.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/workflow/test_drawing_confirmation_orchestration.py::test_case_drawing_stops_before_engines_and_returns_confirmation_url -q`

Expected: FAIL because the drawing-lane coordinator and confirmation URL result do not exist.

- [ ] **Step 3: Write the minimal implementation**

Persist the case manifest and candidate artifacts using existing create-only drawing helpers, project `INPUT_CONFIRMATION_REQUIRED` when required values are absent, and expose only a run-relative confirmation route. Refuse Math/Rule entry until `bind_confirmed_inputs` revalidates source, candidate, and confirmation hashes. When the source hash changes, invalidate the prior confirmation and project `FAILED` with `SOURCE_HASH_MISMATCH`.

- [ ] **Step 4: Run focused and integration tests**

Run: `pytest tests/unit/workflow/test_drawing_confirmation_orchestration.py tests/integration/workflow/test_drawing_confirmation_resume.py -q`

Expected: PASS, including confirmation tamper and source-hash invalidation cases.

- [ ] **Step 5: Commit**

```bash
git add src/ansim_review/workflow tests/unit/workflow tests/integration/workflow
git commit -m "feat: connect drawing confirmation to review workflow"
```

### Task 6: Deterministic engine and dual-track orchestration

**Files:**
- Create: `src/ansim_review/workflow/engine_orchestration.py`
- Create: `src/ansim_review/workflow/next_actions.py`
- Modify: `src/ansim_review/workflow/orchestrator.py`
- Modify: `src/ansim_review/review_run.py`
- Test: `tests/unit/workflow/test_engine_orchestration.py`
- Test: `tests/integration/workflow/test_engine_orchestration.py`

**Interfaces:**
- Consumes: deterministic retrieval query, `math_engine.runner`, governed `rule_engine`, `ReviewRequest`, bound drawing inputs, and existing `finalize_review_run`.
- Produces: `run_deterministic_stages(layout)`, `write_track_a_action(layout)`, `write_track_b_action(layout)`, and immutable `stage-manifest.json`.

- [ ] **Step 1: Write failing tests**

```python
def test_stages_are_retrieval_math_rule_in_order(tmp_path):
    layout = ready_review_fixture(tmp_path)
    run_deterministic_stages(layout)
    assert read_stage_names(layout) == ["RETRIEVING_EVIDENCE", "RUNNING_MATH", "RUNNING_RULES"]

def test_track_b_failure_cannot_finalize_packet(tmp_path):
    layout = ready_review_fixture(tmp_path)
    run_deterministic_stages(layout)
    write_invalid_track_b(layout)
    with pytest.raises(ValueError, match="Track B"):
        finalize_orchestration(layout)
    assert not (layout.run_dir / "final-review-packet.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/workflow/test_engine_orchestration.py tests/integration/workflow/test_engine_orchestration.py -q`

Expected: FAIL because no coordinator owns the ordered stage journal or Track B gate.

- [ ] **Step 3: Write the minimal implementation**

Execute retrieval, then Math, then governed Rule selection/evaluation. Write each output as canonical JSON with its input hash and version identity. Emit `next-action.json` only at `WAITING_TRACK_A` and after validated Track A at `WAITING_TRACK_B`; reject any Track B action without deterministic Track A validation. Delegate final confidence/citation/abstention checks to the existing finalizer and never synthesize results in prose.

- [ ] **Step 4: Run focused, then full workflow tests**

Run: `pytest tests/unit/workflow tests/integration/workflow -q`

Expected: PASS with no packet when Track A/Track B or finalizer gates fail, and a packet only after both validated tracks.

- [ ] **Step 5: Commit**

```bash
git add src/ansim_review/workflow src/ansim_review/review_run.py tests/unit/workflow tests/integration/workflow
git commit -m "feat: orchestrate deterministic engines and dual-track review"
```

### Task 7: HTML browser routes and CLI handoff

**Files:**
- Create: `web_runtime/review_server.py`
- Modify: `web_runtime/bootstrap.py`
- Modify: `src/ansim_review/cli_parser.py`
- Modify: `src/ansim_review/entrypoint.py`
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `docs/REVIEWER_WORKFLOW.md`
- Test: `tests/integration/web_runtime/test_review_routes.py`
- Test: `tests/integration/test_cli_help.py`

**Interfaces:**
- Consumes: run layout and immutable `confirmation/*` / `final-review-packet.json` / `review.html` artifacts.
- Produces: `/runs/<run-id>/confirmation`, `/runs/<run-id>/review`, and `review-run ... --open` with stdout limited to status, run ID, and URL.

- [ ] **Step 1: Write failing route and CLI tests**

```python
def test_confirmation_and_review_routes_are_distinct(client, run_id):
    assert client.get(f"/runs/{run_id}/confirmation").status_code == 200
    assert client.get(f"/runs/{run_id}/review").status_code == 404
    publish_final_review_fixture(run_id)
    assert client.get(f"/runs/{run_id}/review").status_code == 200

def test_open_flag_is_documented_and_does_not_print_artifact_payload():
    result = run_cli_help("review-run", "open")
    assert "--open" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/web_runtime/test_review_routes.py tests/integration/test_cli_help.py -q`

Expected: FAIL because the server has no separate routes and the CLI has no `--open` handoff.

- [ ] **Step 3: Write the minimal implementation**

Serve only localhost, reject path traversal and missing/unfinished artifacts, route confirmation separately from final review, and use `webbrowser.open` only when `--open` is present. Print a compact JSON status line containing `status`, `run_id`, and `url`; never print evidence, model output, or packet contents.

- [ ] **Step 4: Run focused web and CLI tests**

Run: `pytest tests/integration/web_runtime tests/integration/test_cli_help.py -q`

Expected: PASS, including final packet visibility only after finalization and offline/network-guard checks.

- [ ] **Step 5: Commit**

```bash
git add web_runtime src/ansim_review/cli_parser.py src/ansim_review/entrypoint.py docs/CODEX_WORKFLOW.md docs/REVIEWER_WORKFLOW.md tests/integration/web_runtime tests/integration/test_cli_help.py
git commit -m "feat: expose separate confirmation and review browser routes"
```

### Task 8: Recovery and reproducibility

**Files:**
- Create: `src/ansim_review/workflow/resume.py`
- Modify: `src/ansim_review/workflow/events.py`
- Modify: `src/ansim_review/workflow/run_layout.py`
- Test: `tests/unit/workflow/test_resume.py`
- Test: `tests/integration/workflow/test_resume_reproducibility.py`

**Interfaces:**
- Consumes: append-only event journal, stage manifest, request hash, evidence snapshot hash, rule manifest hash, and formula manifest hash.
- Produces: `resume_review_run(layout)` and a deterministic machine-artifact comparison report.

- [ ] **Step 1: Write failing tests**

```python
def test_resume_reuses_completed_stage_when_hashes_match(tmp_path):
    layout = completed_retrieval_fixture(tmp_path)
    first = resume_review_run(layout)
    second = resume_review_run(layout)
    assert first.stage_hashes == second.stage_hashes
    assert first.reexecuted_stages == ()

def test_request_or_version_change_creates_new_run(tmp_path):
    original = request_fixture(tmp_path, question="old")
    changed = request_fixture(tmp_path, question="new")
    assert prepare_or_resume(original).run_id != prepare_or_resume(changed).run_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/workflow/test_resume.py tests/integration/workflow/test_resume_reproducibility.py -q`

Expected: FAIL because stage completion hashes and version-bound resume behavior are not implemented.

- [ ] **Step 3: Write the minimal implementation**

Scan events from the last valid sequence, validate all referenced artifact hashes, skip only completed deterministic stages with identical request/evidence/rule/formula identities, and create a new run ID when any identity changes. Compare canonical machine JSON bytes from two runs and report differing paths plus hashes; never compare timestamps, browser ports, or filenames.

- [ ] **Step 4: Run focused reproducibility tests**

Run: `pytest tests/unit/workflow/test_resume.py tests/integration/workflow/test_resume_reproducibility.py -q`

Expected: PASS, including truncated journal recovery, tampered artifact failure, and byte-equivalence.

- [ ] **Step 5: Commit**

```bash
git add src/ansim_review/workflow tests/unit/workflow tests/integration/workflow
git commit -m "feat: resume review runs from verified deterministic stages"
```

### Task 9: Operations documentation and five E2E acceptance scenarios

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `docs/REVIEWER_WORKFLOW.md`
- Create: `docs/acceptance/issue-56/README.md`
- Create: `docs/acceptance/issue-56/e2e-report.json`
- Create: `tests/integration/workflow/test_issue_56_e2e.py`

**Interfaces:**
- Consumes: all Task 5–8 command paths and artifacts.
- Produces: executable operator scenarios for existing DB, new reference PDF, A3 600dpi drawing, 200dpi JPEG quality-gate abstention, and interrupted confirmation resume.

- [ ] **Step 1: Write the failing E2E acceptance tests**

```python
@pytest.mark.parametrize("scenario", [
    "existing_db_question", "new_reference_pdf_question", "a3_drawing",
    "jpeg_200dpi_abstention", "confirmation_interrupt_resume",
])
def test_issue_56_scenario_reaches_expected_gate(scenario, tmp_path):
    result = run_issue_56_scenario(scenario, tmp_path)
    assert result.status == expected_status(scenario)
    assert result.human_decision is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/workflow/test_issue_56_e2e.py -q`

Expected: FAIL because the integrated command path and acceptance fixtures are not wired together.

- [ ] **Step 3: Write the minimal implementation and docs**

Document source preparation, confirmation, deterministic execution, Track A/B handoff, resume, browser QA, and the distinction between automated PASS and human review. Record exact commands, Python version, commit, artifact hashes, and any unavailable Ubuntu/Actions evidence without labeling it PASS.

- [ ] **Step 4: Run repository acceptance gates**

Run:

```powershell
evidence-review documentation validate --repository-root . --config documentation-integrity.json --output build/issue-56-documentation-integrity.json
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

Expected: all local gates PASS; any unavailable external runner or human browser QA remains explicitly pending.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md docs/CODEX_WORKFLOW.md docs/REVIEWER_WORKFLOW.md docs/acceptance/issue-56 tests/integration/workflow/test_issue_56_e2e.py
git commit -m "docs: record issue 56 orchestration acceptance"
```

## Final Review Checklist

- [ ] Task 5–9 tests pass independently and together.
- [ ] No deterministic engine runs before drawing confirmation is hash-verified.
- [ ] Retrieval → Math → Rule order is visible in the append-only journal.
- [ ] Track B failure prevents packet finalization.
- [ ] Browser confirmation and final review routes are separate.
- [ ] Resume skips only hash-identical completed stages.
- [ ] `human_decision` remains null in every automated artifact.
- [ ] Documentation integrity report has zero errors.
- [ ] Human browser QA and GitHub Actions status are reported separately from local PASS.
