# PR #122 Formal Acceptance Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every product, contract, and acceptance-harness defect discovered during the PR #122 formal acceptance run, while preserving direct/related authority boundaries and fail-closed `not_comparable`/ABSTAIN behavior.

**Architecture:** Keep retrieval lineage as the hard eligibility boundary, add deterministic finding-level evidence relevance before limiting related references, align external LLM instructions with strict validators, align numeric token grammar with explicit unit notation, and make CLI/formal-acceptance prerequisites discoverable before expensive external stages. Track B receives immutable citation support sufficient for independent audit without gaining authority to rewrite Track A.

**Tech Stack:** Python 3.13, stdlib, pytest, existing ERS contracts/CLI, PowerShell 5.1 acceptance wrapper only where Windows byte-preserving stdin is required.

**Spec:** `docs/superpowers/specs/2026-08-26-pr122-formal-acceptance-hardening-design.md`

## Global Constraints

- PR #122 remains Draft until exact-HEAD automated gates, formal artifact acceptance, and browser acceptance are all observed PASS.
- No production workaround for PowerShell 5.1 native-pipe encoding behavior.
- Related evidence never becomes direct authority and never changes `not_comparable` by itself.
- Machine claims, finalizer status, and human decision remain immutable authority boundaries.
- Apply the five-related-reference limit only after semantic filtering/ranking.
- Every product behavior change follows RED → observed failure → minimal GREEN → verification.
- Python 3.13 is the verification baseline.

---

### Task 1: Make related-reference routing semantic, deterministic, and order-independent

**Files:**
- Modify: `tests/unit/review_packet/test_issue_119_related_reference_routing.py`
- Modify: `src/evidence_review/review_packet/related_reference_routing.py`

**Interfaces:**
- Consumes: `finding.title`, `finding.subject_value`, `finding.issue_ids`, QuestionPlan search requests, retrieval lineage, Track A bundle evidence.
- Produces: the existing `(findings, related_references)` shape with deterministic `related_evidence_ids` and render-only `RELATED-*` claim IDs.

- [ ] **Step 1: Add the formal-run failure shape as RED tests.** Extend the fixture with five `REF-002` distractors followed by `REF-001` p.24 §2-5-8. Put all six evidence records on the same issue and make the distractors share the same `S-SPACE` retrieval lineage as the target. Use distractor text such as `사업계획승인신청서`, `촉진지구 지정`, `교통현황`, `건설ㆍ관리ㆍ운영` and target text containing `2-5-8. 단위세대 계획` plus a visible finding term such as `냉장고`/`주방`.

```python
def test_related_routing_prefers_semantic_target_over_same_lineage_distractors(tmp_path):
    view_model, workspace = _formal_shape_fixture(tmp_path, reverse_evidence=False)
    result = build_case_visual_projection(view_model, workspace_root=workspace)
    assert result is not None
    finding = next(item for item in result["findings"] if item["title"] == "공간 구성")
    assert finding["status"] == "not_comparable"
    assert finding["direct_claim_ids"] == []
    assert "E-UNIT" in finding["related_evidence_ids"]
    assert all(
        item["citation"]["document_id"] != "REF-002"
        for item in result["related_references"]
        if item["evidence_id"] in finding["related_evidence_ids"]
    )


def test_related_routing_is_independent_of_evidence_input_order(tmp_path):
    normal_model, normal_workspace = _formal_shape_fixture(tmp_path / "normal", False)
    reversed_model, reversed_workspace = _formal_shape_fixture(tmp_path / "reversed", True)
    normal = build_case_visual_projection(normal_model, workspace_root=normal_workspace)
    reversed_ = build_case_visual_projection(reversed_model, workspace_root=reversed_workspace)
    assert normal is not None and reversed_ is not None
    assert normal["related_references"] == reversed_["related_references"]
```

- [ ] **Step 2: Run RED.**

```text
py -3.13 -m pytest -q tests/unit/review_packet/test_issue_119_related_reference_routing.py
```

Expected: the new tests fail because the first five eligible distractors consume the limit and/or order changes the projection.

- [ ] **Step 3: Implement minimal deterministic ranking.** In `related_reference_routing.py`, keep `_matching_search_request_ids()` and issue/search lineage checks as hard eligibility. Add focused helpers equivalent to:

```python
def _finding_tokens(finding: Mapping[str, object]) -> frozenset[str]:
    return _tokens(
        " ".join(
            value
            for value in (
                str(finding.get("title", "")),
                str(finding.get("subject_value", "")),
            )
            if value
        )
    )


def _rank_related_evidence(
    finding: Mapping[str, object],
    evidence: Mapping[str, object],
    matched_request_texts: Sequence[str],
) -> tuple[int, int, str] | None:
    finding_tokens = _finding_tokens(finding)
    evidence_tokens = _tokens(evidence.get("text"))
    evidence_overlap = len(finding_tokens & evidence_tokens)
    if evidence_overlap == 0:
        return None
    request_overlap = max(
        (len(finding_tokens & _tokens(text)) for text in matched_request_texts),
        default=0,
    )
    evidence_id = str(_mapping(evidence.get("citation"), "citation")["evidence_id"])
    return (-evidence_overlap, -request_overlap, evidence_id)
```

Collect all eligible candidates first, discard rank `None`, sort by the key, and only then slice `[:_RELATED_REFERENCE_LIMIT]`. Do not filter by retrieval role.

- [ ] **Step 4: Run GREEN and renderer regression.**

```text
py -3.13 -m pytest -q tests/unit/review_packet/test_issue_119_related_reference_routing.py tests/unit/review_packet/test_related_reference_render_fallback.py
```

Expected: PASS; direct remains empty, target is related, unrelated REF-002 is absent, status remains `not_comparable`.

- [ ] **Step 5: Commit.**

```text
git add src/evidence_review/review_packet/related_reference_routing.py tests/unit/review_packet/test_issue_119_related_reference_routing.py
git commit -m "fix: rank related visual references by relevance"
```

---

### Task 2: Align external LLM instruction templates with strict contracts

**Files:**
- Create: `tests/unit/llm_layer/test_handoff_template_contracts.py`
- Modify: `src/evidence_review/llm_layer/templates/visual-analysis.md`
- Modify: `src/evidence_review/llm_layer/templates/question-planner.md`
- Modify: `src/evidence_review/llm_layer/templates/track-b.md`

**Interfaces:**
- Produces: self-sufficient handoff instructions that describe the schemas already enforced by decoders/validators.

- [ ] **Step 1: Add RED template-contract tests.** Resolve templates from `Path(evidence_review.llm_layer.__file__).parent / "templates"` and assert the authoritative constraints are present.

```python
def test_visual_analysis_template_declares_strict_scalar_and_geometry_contracts():
    text = _template("visual-analysis.md")
    assert "`normalized_candidate` must be a JSON string or null" in text
    assert "must never be an object, array, number, or boolean" in text
    assert "final point must exactly equal the first point" in text
    assert "`asset_path` is relative to the review workspace" in text


def test_question_planner_template_declares_v2_schema():
    text = _template("question-planner.md")
    for field in ("format", "version", "original_question", "facts", "assumptions", "issues", "legal_anchors", "search_requests"):
        assert f'"{field}"' in text
    assert "legal anchors are retrieval hypotheses" in text.lower()


def test_track_b_template_declares_exact_audit_and_overall_contract():
    text = _template("track-b.md")
    for field in ("run_id", "claim_audits", "overall_disposition", "claim_id", "disposition", "finding_codes", "notes"):
        assert field in text
    assert "any `REJECT`" in text
    assert "any `INCOMPLETE`" in text
```

- [ ] **Step 2: Run RED.**

```text
py -3.13 -m pytest -q tests/unit/llm_layer/test_handoff_template_contracts.py
```

Expected: FAIL because the current templates omit these constraints.

- [ ] **Step 3: Update templates, without changing validators.** Visual Analysis explicitly declares `raw_value`/`normalized_candidate` as `string|null`, forbids structured normalized values, requires closed POLYGON rings, in-bounds geometry, and workspace-relative `asset_path`. Question Planner includes the exact v2 top-level JSON shape, exact fact/issue/anchor/search-request object shapes and enum values. Track B includes exact top-level/audit shapes, allowed dispositions/codes, ACCEPT-with-empty-findings rule, exactly-once coverage, and deterministic overall derivation.

- [ ] **Step 4: Run GREEN plus existing handoff tests.**

```text
py -3.13 -m pytest -q tests/unit/llm_layer/test_handoff_template_contracts.py tests/unit/llm_layer/test_question_planner_handoff_files.py
```

- [ ] **Step 5: Commit.**

```text
git add src/evidence_review/llm_layer/templates tests/unit/llm_layer/test_handoff_template_contracts.py
git commit -m "fix: align llm handoff instructions with validators"
```

---

### Task 3: Support attached measurement units in Track A numeric grammar

**Files:**
- Modify: `tests/unit/llm_layer/test_numeric_grammar.py`
- Modify: `src/evidence_review/llm_layer/numeric_grammar.py`

**Interfaces:**
- Consumes: claim text.
- Produces: existing `NumericToken` tuples; `token.text` remains the numeric token representation expected by Track A integrity checks.

- [ ] **Step 1: Add RED cases to the existing supported-token parametrization.**

```python
("천장높이는 2.4m 이상이다.", ("2.4",)),
("폭은 1500mm이다.", ("1500",)),
("길이는 300cm이다.", ("300",)),
```

Also add `3F` to identifier/non-token coverage.

- [ ] **Step 2: Run RED.**

```text
py -3.13 -m pytest -q tests/unit/llm_layer/test_numeric_grammar.py
```

Expected: attached ASCII measurement-unit cases fail under the current ASCII identifier boundary.

- [ ] **Step 3: Implement an explicit unit suffix whitelist.** Preserve the existing identifier guards, but permit the scanner to end the numeric span immediately before an approved suffix (`m`, `m2`, `m²`, `km`, `mm`, `cm`, `%`, `㎡`, and already-supported Korean measurement/count units). Do not permit arbitrary ASCII suffixes; `3F`, `A12B`, `R1` remain excluded.

- [ ] **Step 4: Verify Track A integration.** Add/extend `tests/unit/review_question/test_track_a_submission.py` with a request excerpt/claim containing `2.4m` and declared `numeric_tokens=["2.4"]`, then assert `submit_track_a()` creates the Track B handoff instead of raising `NUMERIC_TOKEN_MISMATCH`.

```text
py -3.13 -m pytest -q tests/unit/llm_layer/test_numeric_grammar.py tests/unit/review_question/test_track_a_submission.py
```

- [ ] **Step 5: Commit.**

```text
git add src/evidence_review/llm_layer/numeric_grammar.py tests/unit/llm_layer/test_numeric_grammar.py tests/unit/review_question/test_track_a_submission.py
git commit -m "fix: parse attached measurement units in track a"
```

---

### Task 4: Give Track B immutable evidence support for independent audit

**Files:**
- Create: `tests/unit/review_question/test_track_b_handoff_support.py`
- Modify: `src/evidence_review/llm_layer/track_b.py`
- Modify: `src/evidence_review/review_run.py`
- Update tests that snapshot/compare Track B bundle JSON if they fail because of the intentional additive input contract.

**Interfaces:**
- Extends Track B **input only** with citation-bound immutable excerpts.
- Track B output remains exactly `run_id`, `claim_audits`, `overall_disposition`.

- [ ] **Step 1: Reproduce the formal gap as RED.** Prepare a review request with one evidence excerpt, submit a valid cited Track A claim, read `track-b-bundle.json`, and assert it contains support for the cited ID including `citation_id`, `evidence_id`, `source_hash`, and `text`.

```python
def test_track_b_handoff_contains_immutable_support_for_cited_claims(tmp_path):
    prepared = _prepared_with_evidence(tmp_path, text="기준은 40%이다.")
    submit_track_a(...)
    bundle = json.loads((prepared.run_directory / "track-b-bundle.json").read_text("utf-8"))
    support = bundle["evidence_support"]
    assert support == [{
        "citation_id": "CIT-E1",
        "evidence_id": "E1",
        "source_hash": "a" * 64,
        "text": "기준은 40%이다.",
    }]
```

- [ ] **Step 2: Run RED.**

```text
py -3.13 -m pytest -q tests/unit/review_question/test_track_b_handoff_support.py
```

Expected: FAIL because the current Track B bundle contains claims only.

- [ ] **Step 3: Add a narrow immutable support type.** In `track_b.py`, add a frozen `TrackBEvidenceSupport` containing `citation_id`, `evidence_id`, `source_hash`, `text`; add `evidence_support: tuple[TrackBEvidenceSupport, ...]` to `TrackBBundle`; serialize deterministically by citation ID. No support record may exist unless its citation is used by a Track A claim. Duplicate/conflicting citation identity must fail closed.

- [ ] **Step 4: Populate support from the validated Track A input bundle in `submit_track_a()`.** Reuse the already trusted `TrackABundle.evidence`; select only citations referenced by validated Track A claims; do not requery the database and do not add uncited evidence.

- [ ] **Step 5: Run GREEN and Track B validator regression.**

```text
py -3.13 -m pytest -q tests/unit/review_question/test_track_b_handoff_support.py tests/unit/review_question/test_track_a_submission.py tests/unit/llm_layer
```

- [ ] **Step 6: Commit.**

```text
git add src/evidence_review/llm_layer/track_b.py src/evidence_review/review_run.py tests/unit/review_question/test_track_b_handoff_support.py
git commit -m "fix: provide citation support to track b audit"
```

---

### Task 5: Harden CLI discoverability and retrieval preflight

**Files:**
- Create: `tests/unit/test_cli_contract.py`
- Modify: `src/evidence_review/cli.py`
- Modify: `src/evidence_review/cli_parser.py`
- Modify: the review-question preparation path that first guarantees retrieval is required (`src/evidence_review/question_planner_cli.py` and/or `src/evidence_review/review_question.py`, chosen after tracing the current call path).

**Interfaces:**
- `python -m evidence_review.cli ...` must behave like the canonical package CLI.
- `review-question --help` must list supported external submission stages.
- Missing `workspace/evidence/evidence.sqlite` must be rejected before an external visual-analysis handoff is returned once a planned review requires retrieval.

- [ ] **Step 1: Add RED module-entry/help tests.** Use `subprocess.run([sys.executable, "-m", "evidence_review.cli", "--help"], ...)` and parser help capture. Assert exit 0, non-empty help, and presence of `submit-visual-analysis`, `submit-track-a`, `submit-track-b` in `review-question --help`.

- [ ] **Step 2: Add RED missing-DB preflight test.** Build a valid QuestionPlan + case drawing in an otherwise empty workspace and call the same function/CLI stage that previously returned `WAITING_VISUAL_ANALYSIS`; assert deterministic failure mentioning `evidence/evidence.sqlite` and assert no visual-analysis handoff directory was created.

- [ ] **Step 3: Run RED.**

```text
py -3.13 -m pytest -q tests/unit/test_cli_contract.py tests/unit/llm_layer/test_question_planner_cli.py
```

- [ ] **Step 4: Implement minimal fixes.** Add `if __name__ == "__main__": raise SystemExit(main())` to `cli.py`. Add parser-visible submission subcommands that are consistent with `command_dispatch` and do not duplicate runtime handling. Add a helper such as `_require_evidence_database(workspace: Path) -> Path` at the earliest planned-review stage that guarantees retrieval, before visual handoff creation.

- [ ] **Step 5: Run GREEN and nearby CLI suites.**

```text
py -3.13 -m pytest -q tests/unit/test_cli_contract.py tests/unit/llm_layer/test_question_planner_cli.py tests/unit/llm_layer/test_question_planner_dispatch.py tests/unit/review_question
```

- [ ] **Step 6: Commit.**

```text
git add src/evidence_review/cli.py src/evidence_review/cli_parser.py src/evidence_review/question_planner_cli.py src/evidence_review/review_question.py tests/unit/test_cli_contract.py
git commit -m "fix: preflight formal review cli prerequisites"
```

---

### Task 6: Replace fragile manual acceptance checks with deterministic helpers

**Files:**
- Create: `scripts/acceptance/run_codex_json_stage.ps1`
- Create: `scripts/acceptance/verify_formal_review.py`
- Create: `tests/unit/release/test_formal_acceptance_helpers.py`
- Modify: `docs/superpowers/specs/2026-08-26-pr122-formal-acceptance-hardening-design.md` only if execution reveals a contract detail that must be clarified; otherwise leave the approved spec untouched.

**Interfaces:**
- PowerShell wrapper receives prompt file, output file, optional image, trace/stderr paths; sends file bytes through `cmd.exe type` to resolved `codex.cmd` on Windows.
- Python verifier receives workspace, run ID, expected status and optional expected Git HEAD; stops at first failed predicate and emits PASS lines only after successful predicates.

- [ ] **Step 1: Add RED tests for verifier behavior.** Import the Python helper functions directly. Assert workspace-relative `asset_path` resolution, SHA mismatch rejection, missing evidence DB/page-image prerequisite rejection, and that success markers are returned only after all checks pass.

- [ ] **Step 2: Implement `verify_formal_review.py`.** Use exception-driven checks rather than printable unconditional markers. Include functions with explicit signatures:

```python
def resolve_workspace_asset(workspace: Path, asset_path: str) -> Path: ...
def verify_sha256(path: Path, expected: str) -> None: ...
def require_formal_prerequisites(workspace: Path) -> None: ...
def verify_review_artifacts(workspace: Path, run_id: str) -> dict[str, object]: ...
```

The CLI prints `PASS` only after the returned verification document is complete.

- [ ] **Step 3: Implement the Windows transport wrapper.** Resolve `codex.cmd` with `where.exe`, require existing UTF-8 prompt/image paths, construct one `cmd.exe /d /s /c` pipeline using `type`, propagate the native exit code, and never convert the prompt to a PowerShell string before stdin.

- [ ] **Step 4: Run helper tests and PowerShell syntax validation where available.**

```text
py -3.13 -m pytest -q tests/unit/release/test_formal_acceptance_helpers.py
powershell -NoProfile -Command "$null=[scriptblock]::Create((Get-Content -Raw scripts/acceptance/run_codex_json_stage.ps1)); 'POWERSHELL_PARSE_PASS'"
```

Record the PowerShell command `NOT_RUN` rather than PASS when not running on Windows.

- [ ] **Step 5: Commit.**

```text
git add scripts/acceptance tests/unit/release/test_formal_acceptance_helpers.py
git commit -m "test: harden formal acceptance orchestration"
```

---

### Task 7: Exact-HEAD verification and formal/browser acceptance handoff

**Files:**
- No production changes unless a verification failure exposes a new root cause; any such failure returns to RED-first TDD.
- Update PR #122 description/comment with exact observed evidence after verification.

- [ ] **Step 1: Run the focused suite covering all discovered defects.**

```text
py -3.13 -m pytest -q tests/unit/review_packet/test_issue_119_related_reference_routing.py tests/unit/review_packet/test_related_reference_render_fallback.py tests/unit/llm_layer/test_handoff_template_contracts.py tests/unit/llm_layer/test_numeric_grammar.py tests/unit/review_question/test_track_a_submission.py tests/unit/review_question/test_track_b_handoff_support.py tests/unit/test_cli_contract.py tests/unit/release/test_formal_acceptance_helpers.py
```

- [ ] **Step 2: Run quality gates on the same exact HEAD.**

```text
py -3.13 -m ruff check src tests scripts
py -3.13 -m mypy src/evidence_review
py -3.13 -m compileall -q src
```

- [ ] **Step 3: Run full pytest.**

```text
py -3.13 -m pytest -q
```

- [ ] **Step 4: Pin and record the exact HEAD and tracked-tree status.**

```text
git rev-parse HEAD
git status --short --untracked-files=no
```

Do not reuse any PASS evidence from `ab26f830...` or the design-only commit.

- [ ] **Step 5: Run a fresh formal pipeline workspace on the exact HEAD.** Reuse only the immutable evidence corpus/page-image fixture with recorded SHA equality. Generate a new QuestionPlan output, Visual ID, Run ID, Track A/B outputs, final packet and review HTML. Do not reuse prior run artifacts.

- [ ] **Step 6: Artifact-level acceptance.** Require:
  - final status `ABSTAIN` when deterministic direct comparison remains unavailable;
  - `공간 구성.status == not_comparable`;
  - `direct_claim_ids == []` for the target finding;
  - related evidence includes `REF-001` p.24 §2-5-8;
  - related evidence for that finding excludes unrelated `REF-002` business-plan excerpts;
  - machine claim set is unchanged by render-only related projection;
  - lazy case raster URLs are present and case raster base64 is absent from `review.html`.

- [ ] **Step 7: Browser acceptance.** Verify the Issue #119 P0/UX set at 1920×1080, 1366×768 and ≤720px: related §2-5-8 visible, direct empty state retained, Finding click focuses both panes, no opaque/black overlay, wheel zoom/drag pan/Fit/+/- work, selected-only works, drawer opens only on click and closes via backdrop/Escape, pagination/lazy loading works, repeated question text absent.

- [ ] **Step 8: Update PR state only from observed evidence.** Keep Draft if any P0 is FAIL/NOT_RUN. Only after all P0s and exact-head gates are observed PASS, mark the acceptance section complete and then consider Ready for review. Issue #119 stays open until that point.

## Self-review checklist

- Spec coverage: all five discovered defect groups plus exact-head formal/browser revalidation are mapped to Tasks 1–7.
- Authority consistency: no task promotes related evidence to direct or weakens Track A/B/finalizer/human-decision boundaries.
- Type consistency: Track B support is input-only; Track B output schema remains unchanged.
- Order determinism: related-reference sorting uses semantic scores plus evidence ID tie-breaker before the limit.
- Environment separation: PowerShell UTF-8 handling stays in acceptance tooling, not product logic.
- No placeholders: each task names exact files, RED/GREEN commands, implementation boundary, and commit scope.
