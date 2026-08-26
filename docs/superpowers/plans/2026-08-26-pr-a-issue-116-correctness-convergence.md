# PR-A Issue #116 Correctness Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-integrate Issue #116 correctness, active-workspace binding, retrieval relevance/facets, deterministic comparisons, final lineage, and Track retry ownership onto current `main` without regressing merged PR #122.

**Architecture:** Start from `main@3eb45de3d6d12265d6fa75f713b42a570955e949` in a fresh worktree and selectively port behavior from PR #117 HEAD `e8e17271888b6f4833776c4200a24fe40c5d7772`; never merge or cherry-pick PR #117 wholesale. The trust path is active workspace → snapshot provenance → issue/facet-aware retrieval → deterministic comparison → Track A/B validation → final packet. If old #117 workflow code conflicts with current #122 behavior, current `main` wins and only the missing correctness contract is added.

**Tech Stack:** Python 3.13, pytest, SQLite/FTS, dataclasses, Decimal, canonical JSON/SHA-256, existing CLI/skills, PowerShell verification.

**Spec:** `docs/superpowers/specs/2026-08-26-integrated-correctness-reference-viewer-design.md`

## Global Constraints

- If `origin/main` advances beyond `3eb45de3d6d12265d6fa75f713b42a570955e949` before execution, re-run Task 1 against the new main and update only baseline SHA-dependent commands before editing code.
- Do not merge or cherry-pick PR #117 wholesale.
- Preserve `AGENTS.md` authority order; QuestionPlan remains control input, not evidence authority.
- Preserve PR #122 Visual Review and workflow event contracts.
- Runtime remains offline except existing loopback protected-server traffic.
- Python 3.13 is the acceptance runtime.
- All natural-language questions retain Question Planner → retrieval → Track A → Track B → finalizer flow.
- Workspace/snapshot mismatch fails closed.
- Numeric comparisons are deterministic runtime artifacts, never prose calculations.
- External Track generation writes attempt files; canonical Track outputs are runtime-owned.
- Real-corpus S1–S3 and I1–I7 acceptance is a merge gate.

---

### Task 1: Freeze Current Main and Inventory the Selective Port

**Files:**
- Read: `AGENTS.md`
- Read: `docs/superpowers/specs/2026-08-26-integrated-correctness-reference-viewer-design.md`
- Create: `docs/plans/2026-08-26-issue-116-port-inventory.md`

**Interfaces:**
- Consumes: current main and PR #117 HEAD.
- Produces: isolated branch `agent/issue-116-correctness-convergence` and a `PORT / ALREADY_IN_MAIN / DO_NOT_PORT_PR122_CONFLICT` inventory.

- [ ] **Step 1: Create the isolated worktree**

```powershell
git fetch origin main docs/issue-116-correctness-hardening
git worktree add F:\2026-PJ\evidence-review-system-issue116-convergence -b agent/issue-116-correctness-convergence 3eb45de3d6d12265d6fa75f713b42a570955e949
Set-Location F:\2026-PJ\evidence-review-system-issue116-convergence
git status --short
git rev-parse HEAD
```

Expected: clean worktree and exact baseline SHA.

- [ ] **Step 2: Run the unmodified main baseline**

```powershell
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
```

Expected: current-main gate passes or any environment-only deviation is recorded before edits.

- [ ] **Step 3: Generate the port inventory**

```powershell
git diff --name-status 3eb45de3d6d12265d6fa75f713b42a570955e949 e8e17271888b6f4833776c4200a24fe40c5d7772 -- `
  src/evidence_review tests .agents/skills skills AGENTS.md
```

Inventory rules:

```text
PORT
- src/evidence_review/workspace_binding.py
- evidence snapshot provenance additions
- relevance/facet/coverage/comparison behavior
- IssueResult lineage additions
- retry-ownership behavior missing from current main
- active-workspace skill/CLI guidance

ALREADY_IN_MAIN
- any behavior already present after PR #122

DO_NOT_PORT_PR122_CONFLICT
- old #117 workflow/UI hunks that replace current #122 event, Visual Review, Track B handoff, or renderer behavior
```

- [ ] **Step 4: Commit the inventory**

```powershell
git add docs/plans/2026-08-26-issue-116-port-inventory.md
git commit -m "docs: inventory issue 116 convergence port"
```

---

### Task 2: Add Snapshot Provenance and Active Workspace Binding

**Files:**
- Create: `src/evidence_review/workspace_binding.py`
- Modify: `src/evidence_review/evidence/snapshot.py`
- Create/port: `tests/unit/test_active_workspace_binding.py`
- Create/port: `tests/unit/review_question/test_evidence_snapshot_binding.py`

**Interfaces:**
- `ActiveWorkspaceBinding(workspace: Path, evidence_snapshot_hash: str, evidence_db_sha256: str, schema_version: int, retrieval_record_count: int, clause_record_count: int)`.
- `bind_active_workspace(repository_root: Path, workspace: Path) -> ActiveWorkspaceBinding`.
- `resolve_active_workspace(repository_root: Path) -> ActiveWorkspaceBinding`.
- `evidence_snapshot_provenance(connection: sqlite3.Connection) -> dict[str, object]`.

- [ ] **Step 1: Port active-workspace tests before production code**

Required assertions:

```python
binding = bind_active_workspace(repository_root, workspace)
assert binding.workspace == workspace.resolve()
assert len(binding.evidence_snapshot_hash) == 64
assert len(binding.evidence_db_sha256) == 64
assert resolve_active_workspace(repository_root) == binding
```

Also assert missing binding includes `ACTIVE_WORKSPACE_NOT_BOUND`, mutated evidence after binding includes `ACTIVE_WORKSPACE_STALE`, and symlinked state/workspace/database paths are rejected.

- [ ] **Step 2: Run tests to verify RED**

```powershell
py -3.13 -m pytest -q tests/unit/test_active_workspace_binding.py tests/unit/review_question/test_evidence_snapshot_binding.py
```

Expected: current main lacks `workspace_binding.py` and run provenance binding.

- [ ] **Step 3: Add exact evidence provenance**

```python
def evidence_snapshot_provenance(connection: sqlite3.Connection) -> dict[str, object]:
    evidence_hash = _metadata_hash(connection, "snapshot_meta")
    retrieval_hash = _metadata_hash(connection, "retrieval_meta")
    if retrieval_hash != evidence_hash:
        raise RuntimeError("retrieval index snapshot hash mismatch")
    serialized = connection.serialize()
    return {
        "evidence_snapshot_hash": evidence_hash,
        "evidence_db_sha256": hashlib.sha256(serialized).hexdigest(),
        "schema_version": detect_schema_version(connection),
        "retrieval_record_count": int(connection.execute("SELECT COUNT(*) FROM retrieval_records").fetchone()[0]),
        "clause_record_count": int(connection.execute("SELECT COUNT(*) FROM clause_retrieval_records").fetchone()[0]),
    }
```

- [ ] **Step 4: Port atomic binding implementation**

State path is `.ers/active-workspace.json`. Write through `NamedTemporaryFile` + `os.fsync` + `os.replace`. Store exact absolute workspace and all provenance fields. Preserve literal failure codes:

```python
raise FileNotFoundError(f"ACTIVE_WORKSPACE_NOT_BOUND: {binding_path}")
raise ValueError("ACTIVE_WORKSPACE_STALE: evidence snapshot or workspace identity changed")
```

- [ ] **Step 5: Bind provenance into prepared review artifacts**

`review-question prepare` must record the same provenance into Track A inputs and retrieval trace. Prepared/resumed runs comparing against a different current snapshot fail with `EVIDENCE_SNAPSHOT_MISMATCH` rather than `RETRIEVAL_MISS`.

- [ ] **Step 6: Run focused tests to verify GREEN**

```powershell
py -3.13 -m pytest -q tests/unit/test_active_workspace_binding.py tests/unit/review_question/test_evidence_snapshot_binding.py
```

- [ ] **Step 7: Commit**

```powershell
git add src/evidence_review/workspace_binding.py src/evidence_review/evidence/snapshot.py tests/unit/test_active_workspace_binding.py tests/unit/review_question/test_evidence_snapshot_binding.py
git commit -m "feat: bind reviews to exact evidence workspace"
```

---

### Task 3: Wire Active Workspace into CLI and ERS Skills

**Files:**
- Modify: `src/evidence_review/cli_parser.py`
- Modify: `src/evidence_review/command_dispatch.py`
- Modify: `.agents/skills/ers-pdf/SKILL.md`
- Modify: `.agents/skills/ers-review/SKILL.md`
- Modify: `.agents/skills/TESTS.md`
- Modify: `skills/ers-pdf/SKILL.md`
- Modify: `skills/ers-review/SKILL.md`
- Modify/port: `tests/integration/skills/test_ers_pdf_skill.py`
- Modify/port: `tests/integration/packaging/test_user_facing_skills_bundle.py`

**Interfaces:**
- `evidence-review workspace bind --repository-root <path> --workspace <path>`.
- `evidence-review workspace active --repository-root <path>`.
- Successful active query emits `format=evidence-review/active-workspace-status`, `stage=active`, `status=ACTIVE` plus provenance.

- [ ] **Step 1: Add failing parser/dispatch tests**

Assert the two workspace subcommands parse and that missing/stale binding exits non-zero with the literal failure code on stderr.

- [ ] **Step 2: Run focused tests to verify RED**

```powershell
py -3.13 -m pytest -q tests/unit/test_active_workspace_binding.py tests/integration/skills/test_ers_pdf_skill.py tests/integration/packaging/test_user_facing_skills_bundle.py
```

- [ ] **Step 3: Port the exact dispatch contract**

```python
def _workspace_status_document(binding: ActiveWorkspaceBinding, *, stage: str, status: str) -> dict[str, object]:
    return {
        "format": "evidence-review/active-workspace-status",
        "version": 1,
        "stage": stage,
        "status": status,
        "workspace": str(binding.workspace),
        "evidence_snapshot_hash": binding.evidence_snapshot_hash,
        "evidence_db_sha256": binding.evidence_db_sha256,
        "schema_version": binding.schema_version,
        "retrieval_record_count": binding.retrieval_record_count,
        "clause_record_count": binding.clause_record_count,
    }
```

`_workspace_dispatch()` writes `dump_bytes(document)` to `sys.stdout.buffer` and returns `2` for missing/invalid/stale binding.

- [ ] **Step 4: Update both installed and packaged skill copies**

Required `$ERS_REVIEW` prefix:

```text
workspace active
→ review-question prepare-plan
→ external QuestionPlan
→ review-question prepare
```

Explicitly prohibit recursive `evidence.sqlite` search, newest-workspace guessing, first-result selection, and old-run-path inference.

- [ ] **Step 5: Run focused tests to verify GREEN**

```powershell
py -3.13 -m pytest -q tests/unit/test_active_workspace_binding.py tests/integration/skills/test_ers_pdf_skill.py tests/integration/packaging/test_user_facing_skills_bundle.py
```

- [ ] **Step 6: Commit**

```powershell
git add src/evidence_review/cli_parser.py src/evidence_review/command_dispatch.py .agents/skills skills tests/integration/skills/test_ers_pdf_skill.py tests/integration/packaging/test_user_facing_skills_bundle.py
git commit -m "feat: enforce active workspace handoff"
```

---

### Task 4: Port Operational Subclauses and Match-Local Citation Resolution

**Files:**
- Modify: `src/evidence_review/evidence/clause_materialization.py`
- Modify: `src/evidence_review/retrieval/clause_resolution.py`
- Modify/port: `tests/unit/evidence/test_clause_materialization.py`
- Modify/port: `tests/integration/retrieval/test_clause_resolution.py`

**Interfaces:**
- `derive_legal_clauses(elements: Sequence[Mapping[str, object]]) -> ClauseMaterialization`.
- Operational leaves include `4-4-2/나/1/가` and `4-4-2/나/2/나`.
- Citation materialization prioritizes matching source elements before bounded neighbors.

- [ ] **Step 1: Add hierarchy RED tests**

Fixture text:

```text
4-4-2. 준공업지역
나. 준공업지역의 경우
1) 기본용적률 및 공공기여율
가) 기본용적률 : 400% 이하
2) 용도별 비율 등
나) 공장비율 10% 이상인 경우 산업부지 확보비율은 관련 위원회 심의를 통해 2분의 1까지 완화할 수 있다.
```

Assert leaf keys and exact source element IDs.

- [ ] **Step 2: Add citation locality RED test**

Build a broad clause with the matching phrase in the final linked source element. Assert the matching element is selected even when the citation budget is smaller than the linked-element count.

- [ ] **Step 3: Run RED tests**

```powershell
py -3.13 -m pytest -q tests/unit/evidence/test_clause_materialization.py tests/integration/retrieval/test_clause_resolution.py
```

- [ ] **Step 4: Port only recognized operational hierarchy state**

```python
_OPERATION_RE = re.compile(r"^\s*(\d+(?:-\d+){1,3})\.\s*(.*)$", re.DOTALL)
_OPERATION_ALPHA_DOT_RE = re.compile(r"^\s*([가-힣])\.\s*(.*)$", re.DOTALL)
_OPERATION_NUMBER_PAREN_RE = re.compile(r"^\s*(\d+)\)\s*(.*)$", re.DOTALL)
_OPERATION_ALPHA_PAREN_RE = re.compile(r"^\s*([가-힣])\)\s*(.*)$", re.DOTALL)
```

Parser elements remain source truth; derived clauses preserve source/page/bbox lineage.

- [ ] **Step 5: Implement match-local source-element ordering**

Rank direct matched source elements first, then deterministic nearest linked elements, then stop at the existing citation budget. Do not revert to simple first-N parser order.

- [ ] **Step 6: Run GREEN tests and commit**

```powershell
py -3.13 -m pytest -q tests/unit/evidence/test_clause_materialization.py tests/integration/retrieval/test_clause_resolution.py
git add src/evidence_review/evidence/clause_materialization.py src/evidence_review/retrieval/clause_resolution.py tests/unit/evidence/test_clause_materialization.py tests/integration/retrieval/test_clause_resolution.py
git commit -m "fix: materialize precise operational clauses"
```

---

### Task 5: Add Issue Relevance, Required Anchors, and Fallback Continuation

**Files:**
- Create: `src/evidence_review/retrieval/relevance.py`
- Modify: `src/evidence_review/retrieval/fallback.py`
- Modify: `src/evidence_review/retrieval/issue_bundle.py`
- Modify: `src/evidence_review/retrieval/trace.py`
- Create/port: `tests/unit/retrieval/test_subject_section_relevance.py`
- Create/port: `tests/unit/retrieval/test_relevance_specificity_edges.py`
- Create/port: `tests/unit/retrieval/test_relevance_trace.py`

**Interfaces:**
- `evaluate_issue_clause_relevance(*, issue_id: str, issue_question: str, search_request_id: str, query_text: str, clause: ClauseRetrievalHit) -> RelevanceDecision`.
- Rejection codes include `REJECT_SUBJECT_CONFLICT` and `REJECT_REQUIRED_ANCHOR_MISSING`.
- `search_clause_with_fallback(..., hit_filter=...)` continues after a stage whose hits are all rejected.

- [ ] **Step 1: Add the exact station/arterial conflict test**

```python
decision = evaluate_issue_clause_relevance(
    issue_id="I-ZONE",
    issue_question="역세권 부지의 제2종일반주거지역을 준주거지역으로 변경하는 요건은?",
    search_request_id="S-ZONE",
    query_text="역세권 용도지역 변경 기준",
    clause=_clause(
        "2-3-2. 간선도로변의 용도지역 변경 기준",
        "간선도로변에서 용도지역을 변경하는 경우 적용하는 기준이다.",
    ),
)
assert decision.accepted is False
assert "REJECT_SUBJECT_CONFLICT" in decision.reason_codes
```

- [ ] **Step 2: Add the exact minimum-area anchor test**

```python
decision = evaluate_issue_clause_relevance(
    issue_id="I1",
    issue_question="안심주택의 일반적인 사업대상지 최소 면적은 얼마인가?",
    search_request_id="S1",
    query_text="안심주택 일반 사업대상지 최소 면적",
    clause=_clause(
        "2-3-1. 용도지역 변경 기준",
        "안심주택 사업대상지의 용도지역 변경과 도로 조건을 정한다.",
    ),
)
assert decision.accepted is False
assert "REJECT_REQUIRED_ANCHOR_MISSING" in decision.reason_codes
```

- [ ] **Step 3: Add fallback continuation test**

Use `search_clause_with_fallback()` with a `hit_filter` that rejects the exact-clause stage and assert `result.success_stage == FallbackStage.PHRASE` and later hits are returned.

- [ ] **Step 4: Run RED tests**

```powershell
py -3.13 -m pytest -q tests/unit/retrieval/test_subject_section_relevance.py tests/unit/retrieval/test_relevance_specificity_edges.py tests/unit/retrieval/test_relevance_trace.py
```

- [ ] **Step 5: Port relevance logic and trace binding**

Selection path:

```text
query hit
→ request-required anchor check
→ issue subject conflict check
→ accepted candidate OR trace rejection
→ if stage has zero accepted candidates, continue bounded fallback
```

- [ ] **Step 6: Run GREEN tests and commit**

```powershell
py -3.13 -m pytest -q tests/unit/retrieval/test_subject_section_relevance.py tests/unit/retrieval/test_relevance_specificity_edges.py tests/unit/retrieval/test_relevance_trace.py
git add src/evidence_review/retrieval/relevance.py src/evidence_review/retrieval/fallback.py src/evidence_review/retrieval/issue_bundle.py src/evidence_review/retrieval/trace.py tests/unit/retrieval/test_subject_section_relevance.py tests/unit/retrieval/test_relevance_specificity_edges.py tests/unit/retrieval/test_relevance_trace.py
git commit -m "fix: reject issue-subject retrieval conflicts"
```

---

### Task 6: Add Compound Facet Compilation and Facet-Aware Coverage

**Files:**
- Create: `src/evidence_review/retrieval/facets.py`
- Modify: `src/evidence_review/retrieval/coverage.py`
- Modify: `src/evidence_review/planned_review_question.py`
- Create/port: `tests/unit/retrieval/test_compound_issue_facet_decomposition.py`
- Create/port: `tests/unit/retrieval/test_issue_facets.py`
- Create/port: `tests/unit/retrieval/test_industrial_facet_specificity.py`
- Create/port: `tests/unit/retrieval/test_facet_gap_precedence.py`
- Modify/port: `tests/unit/retrieval/test_coverage.py`

**Interfaces:**
- `compile_required_facets(plan: QuestionPlan) -> FacetPlan`.
- `augment_plan_with_facet_search_requests(plan: QuestionPlan) -> QuestionPlan`.
- `FacetCoverageReport.by_issue_id(issue_id)`.
- I2 requires `minimum-area-threshold`, `distance-normal-threshold`, `distance-conditional-threshold`.

- [ ] **Step 1: Add I2 facet RED test**

```python
facet_ids = [
    item.facet_id
    for item in compile_required_facets(plan).by_issue_id("I2").required_facets
]
assert facet_ids == [
    "minimum-area-threshold",
    "distance-normal-threshold",
    "distance-conditional-threshold",
]
```

Assert `issue_context_text()` recovers `1,500㎡` only from the original sentence sharing the I2 `300m` measure.

- [ ] **Step 2: Add dormitory and industrial specificity tests**

`임대형기숙사를 제외한` must not satisfy `dormitory-parking-standard`. `industrial-site-ratio` must bind the ratio nearest `산업부지 확보비율`, not an unrelated percentage.

- [ ] **Step 3: Run RED tests**

```powershell
py -3.13 -m pytest -q tests/unit/retrieval/test_compound_issue_facet_decomposition.py tests/unit/retrieval/test_issue_facets.py tests/unit/retrieval/test_industrial_facet_specificity.py tests/unit/retrieval/test_facet_gap_precedence.py tests/unit/retrieval/test_coverage.py
```

- [ ] **Step 4: Port the facet compiler and generated request contract**

Generated IDs are exact:

```python
id=f"FACET-{issue.issue_id}-{requirement.facet_id}"
```

Generated search requests remain bounded by `MAX_SEARCH_REQUESTS`.

- [ ] **Step 5: Make coverage facet-aware**

Coverage documents gain `covered_facet_ids` and `missing_facet_ids`. Generic role=`rule` evidence cannot produce `RESOLVED` if a required facet is missing.

- [ ] **Step 6: Run GREEN tests and commit**

```powershell
py -3.13 -m pytest -q tests/unit/retrieval/test_compound_issue_facet_decomposition.py tests/unit/retrieval/test_issue_facets.py tests/unit/retrieval/test_industrial_facet_specificity.py tests/unit/retrieval/test_facet_gap_precedence.py tests/unit/retrieval/test_coverage.py
git add src/evidence_review/retrieval/facets.py src/evidence_review/retrieval/coverage.py src/evidence_review/planned_review_question.py tests/unit/retrieval
git commit -m "feat: enforce required issue facets"
```

---

### Task 7: Add Deterministic Fact-Rule Comparison and Final Lineage

**Files:**
- Create: `src/evidence_review/rule_engine/fact_rule_comparison.py`
- Modify: `src/evidence_review/contracts/review.py`
- Modify: `src/evidence_review/contracts/codecs.py`
- Modify: `src/evidence_review/planned_review_question.py`
- Modify: `src/evidence_review/abstention/finalizer.py`
- Modify: `src/evidence_review/llm_layer/validators.py`
- Create/port: `tests/unit/rule_engine/test_fact_rule_comparison.py`
- Create/port: `tests/unit/rule_engine/test_issue_bound_fact_rule_comparison.py`
- Modify/port: `tests/unit/contracts/test_review_issue_results.py`
- Create/port: `tests/unit/llm_layer/test_track_a_comparison_integrity.py`

**Interfaces:**
- `FactRuleComparison(comparison_id, issue_id, facet_id, operator, fact_value, threshold_value, unit, satisfied, evidence_ids, result_hash)`.
- `compare_fact_to_threshold(...) -> FactRuleComparison`.
- `evaluate_fact_rule_comparisons(plan, bundle, facet_report) -> tuple[FactRuleComparison, ...]`.
- `bind_comparisons_to_review_request(...) -> dict[str, object]`.
- `IssueResult` optional fields: `covered_facet_ids`, `missing_facet_ids`, `comparison_ids`.

- [ ] **Step 1: Add deterministic comparison RED tests**

```python
assert minimum_area.fact_value == "1500"
assert minimum_area.threshold_value == "1000"
assert minimum_area.satisfied is True
assert normal_distance.fact_value == "300"
assert normal_distance.threshold_value == "250"
assert normal_distance.satisfied is False
assert conditional_distance.threshold_value == "350"
assert conditional_distance.satisfied is True
assert far.fact_value == "400" and far.threshold_value == "400" and far.satisfied is True
```

- [ ] **Step 2: Run RED tests**

```powershell
py -3.13 -m pytest -q tests/unit/rule_engine/test_fact_rule_comparison.py tests/unit/rule_engine/test_issue_bound_fact_rule_comparison.py
```

- [ ] **Step 3: Implement Decimal-owned comparison**

```python
_COMPARISON_CONFIG = {
    "minimum-area-threshold": ("area_m2", ">=", None),
    "distance-normal-threshold": ("length_m", "<=", False),
    "distance-conditional-threshold": ("length_m", "<=", True),
    "semi-industrial-far-threshold": ("percent", "<=", None),
}
```

Hash canonical comparison content and derive `CMP-...` from the result hash.

- [ ] **Step 4: Bind comparison/facet lineage through Track A and final packet**

Track A numeric integrity may treat `1500` and `1,500` as grouping-equivalent only when deterministic comparison lineage proves the same value. `%` remains preserved. Old packets without the three optional lineage fields continue to decode.

- [ ] **Step 5: Run GREEN tests and commit**

```powershell
py -3.13 -m pytest -q tests/unit/rule_engine/test_fact_rule_comparison.py tests/unit/rule_engine/test_issue_bound_fact_rule_comparison.py tests/unit/contracts/test_review_issue_results.py tests/unit/llm_layer/test_track_a_comparison_integrity.py
git add src/evidence_review/rule_engine/fact_rule_comparison.py src/evidence_review/contracts/review.py src/evidence_review/contracts/codecs.py src/evidence_review/planned_review_question.py src/evidence_review/abstention/finalizer.py src/evidence_review/llm_layer/validators.py tests/unit/rule_engine tests/unit/contracts/test_review_issue_results.py tests/unit/llm_layer/test_track_a_comparison_integrity.py
git commit -m "feat: bind deterministic comparisons to issue results"
```

---

### Task 8: Add Only Missing Track A/B Retry Ownership on Top of #122

**Files:**
- Inspect/modify only missing behavior: `src/evidence_review/review_question.py`
- Inspect/modify only missing behavior: `src/evidence_review/review_run.py`
- Inspect/modify only missing behavior: `src/evidence_review/contracts/workflow.py`
- Inspect/modify only missing behavior: `src/evidence_review/workflow/events.py`
- Modify: `.agents/skills/ers-review/SKILL.md`
- Modify: `skills/ers-review/SKILL.md`
- Create/port: `tests/unit/skills/test_ers_review_retry_contract.py`
- Modify/port: `tests/integration/review_question/test_review_metrics.py`
- Regression: `tests/unit/review_question/test_track_b_handoff_support.py`
- Regression: `tests/integration/review_run/test_review_run_cli.py`
- Regression: `tests/integration/workflow/test_event_journal.py`

**Interfaces:**
- External attempts use `track-a-attempt-<N>.json` and `track-b-attempt-<N>.json`.
- Validated stage cannot receive later external-wait events for that stage.
- Track B finalization recovery reuses canonical validated Track B.
- Different recovery retry identity fails `TRACK_B_RETRY_MISMATCH`.

- [ ] **Step 1: Diff the four workflow files before editing**

```powershell
git diff 3eb45de3d6d12265d6fa75f713b42a570955e949 e8e17271888b6f4833776c4200a24fe40c5d7772 -- `
  src/evidence_review/review_question.py `
  src/evidence_review/review_run.py `
  src/evidence_review/contracts/workflow.py `
  src/evidence_review/workflow/events.py
```

Classify each #117 hunk as `MISSING_CORRECTNESS` or `ALREADY_REPLACED_BY_122`. Only the first category may be ported.

- [ ] **Step 2: Port retry tests first**

Required cases:

```text
Track A validation fail → attempt 2 allowed
Track A success → no later Track A external wait
Track B success → finalization recovery does not call Track B again
mismatched Track B recovery identity → TRACK_B_RETRY_MISMATCH
FILEEXISTSERROR → orchestration defect, not normal retry
```

- [ ] **Step 3: Run focused tests**

```powershell
py -3.13 -m pytest -q tests/unit/skills/test_ers_review_retry_contract.py tests/integration/review_question/test_review_metrics.py tests/unit/review_question/test_track_b_handoff_support.py tests/integration/review_run/test_review_run_cli.py tests/integration/workflow/test_event_journal.py
```

Tests already GREEN on main indicate no production port is required for that behavior.

- [ ] **Step 4: Implement only RED behaviors**

Track A submission requires current state `WAITING_TRACK_A`. Validated Track B recovery verifies original retry identity, reuses canonical Track B, and resumes only finalization. Do not overwrite #122 event allowlists or immutable `evidence_support` handoff behavior.

- [ ] **Step 5: Re-run focused tests and commit only changed files**

```powershell
py -3.13 -m pytest -q tests/unit/skills/test_ers_review_retry_contract.py tests/integration/review_question/test_review_metrics.py tests/unit/review_question/test_track_b_handoff_support.py tests/integration/review_run/test_review_run_cli.py tests/integration/workflow/test_event_journal.py
git add src/evidence_review/review_question.py src/evidence_review/review_run.py src/evidence_review/contracts/workflow.py src/evidence_review/workflow/events.py .agents/skills/ers-review/SKILL.md skills/ers-review/SKILL.md tests/unit/skills/test_ers_review_retry_contract.py tests/integration/review_question/test_review_metrics.py tests/unit/review_question/test_track_b_handoff_support.py tests/integration/review_run/test_review_run_cli.py tests/integration/workflow/test_event_journal.py
git commit -m "fix: preserve validated track retry ownership"
```

If no production file changed because #122 already contains all runtime behavior, commit only the missing skill/tests with a test-focused commit message.

---

### Task 9: Port Production-Shaped Issue #116 Acceptance

**Files:**
- Modify/port: `tests/fixtures/real_review_retrieval_relevance/expected-evidence.json`
- Modify/port: `tests/fixtures/real_review_retrieval_relevance/question-plan.json`
- Create/port: `tests/integration/review_question/test_issue_116_acceptance_artifacts.py`
- Modify/port: `tests/integration/review_question/test_real_review_full_e2e.py`

**Interfaces:**
- Synthetic acceptance proves I1–I7 before real corpus.
- I2=`CONDITIONAL` with exactly three facets/comparisons.
- I6 evidence contains `공장비율 10% 이상`, `관련 위원회 심의`, `2분의 1까지 완화`.

- [ ] **Step 1: Port exact acceptance assertions**

```python
assert coverage["I2"]["status"] == "CONDITIONAL"
assert facets["I2"]["covered_facet_ids"] == [
    "minimum-area-threshold",
    "distance-normal-threshold",
    "distance-conditional-threshold",
]
assert set(coverage["I2"]["comparison_ids"]) == {
    minimum_area["comparison_id"],
    normal_distance["comparison_id"],
    conditional_distance["comparison_id"],
}
assert "2분의 1까지" in evidence_by_id["E-INDUSTRIAL-SITE"]["text"]
```

- [ ] **Step 2: Run integration acceptance**

```powershell
py -3.13 -m pytest -q tests/integration/review_question/test_issue_116_acceptance_artifacts.py tests/integration/review_question/test_real_review_full_e2e.py
```

Expected: PASS after Tasks 2–8.

- [ ] **Step 3: Run complete Issue #116 targeted suite**

```powershell
py -3.13 -m pytest -q `
  tests/unit/review_question/test_evidence_snapshot_binding.py `
  tests/unit/evidence/test_clause_materialization.py `
  tests/integration/retrieval/test_clause_resolution.py `
  tests/unit/retrieval/test_subject_section_relevance.py `
  tests/unit/retrieval/test_relevance_specificity_edges.py `
  tests/unit/retrieval/test_relevance_trace.py `
  tests/unit/retrieval/test_compound_issue_facet_decomposition.py `
  tests/unit/retrieval/test_issue_facets.py `
  tests/unit/retrieval/test_industrial_facet_specificity.py `
  tests/unit/retrieval/test_facet_gap_precedence.py `
  tests/unit/rule_engine/test_fact_rule_comparison.py `
  tests/unit/rule_engine/test_issue_bound_fact_rule_comparison.py `
  tests/unit/llm_layer/test_track_a_comparison_integrity.py `
  tests/unit/retrieval/test_coverage.py `
  tests/unit/contracts/test_review_issue_results.py `
  tests/unit/skills/test_ers_review_retry_contract.py `
  tests/integration/review_question/test_issue_116_acceptance_artifacts.py `
  tests/integration/review_question/test_real_review_full_e2e.py
```

- [ ] **Step 4: Commit**

```powershell
git add tests/fixtures/real_review_retrieval_relevance tests/integration/review_question/test_issue_116_acceptance_artifacts.py tests/integration/review_question/test_real_review_full_e2e.py
git commit -m "test: lock issue 116 acceptance artifacts"
```

---

### Task 10: Run Exact-HEAD Repository and PR #122 Regression Gates

**Files:**
- No planned production edits.

**Interfaces:**
- Produces automated exact-HEAD acceptance evidence.

- [ ] **Step 1: Run PR #122 focused regression**

```powershell
py -3.13 -m pytest -q `
  tests/unit/review_packet/test_issue_119_related_reference_formal_shape.py `
  tests/unit/review_packet/test_issue_119_related_reference_routing.py `
  tests/unit/review_packet/test_issue_119_visual_hardening.py `
  tests/unit/review_packet/test_issue_119_visual_performance.py `
  tests/unit/review_packet/test_pr122_acceptance_regressions.py `
  tests/unit/review_packet/test_related_reference_render_fallback.py `
  tests/unit/review_question/test_track_b_handoff_support.py
```

- [ ] **Step 2: Run the repository-wide gate from `AGENTS.md`**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output .tmp-doc-validation
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
```

Expected: all PASS; documentation errors=0.

- [ ] **Step 3: Record exact HEAD and clean state**

```powershell
git rev-parse HEAD
git status --short
```

Expected: clean worktree.

---

### Task 11: Execute Real-Corpus S1–S3 and I1–I7 Acceptance

**Files:**
- Runtime artifacts only in the selected user workspace.
- Do not commit source PDFs, parser outputs, evidence DBs, page caches, run ZIPs, or absolute private workspace paths.

**Interfaces:**
- S1 → direct `1,000㎡` evidence.
- S2 → direct `250m` + conditional `350m` evidence.
- S3 → paragraph ② dormitory parking lineage.
- I2 → `CONDITIONAL` with `1500>=1000`, `300<=250`, `300<=350`.

- [ ] **Step 1: Select the real acceptance workspace outside git and expose it only through the process environment**

```powershell
$acceptanceWorkspace = [System.IO.Path]::GetFullPath($env:ERS_ACCEPTANCE_WORKSPACE)
if (-not (Test-Path $acceptanceWorkspace)) { throw "ERS_ACCEPTANCE_WORKSPACE does not exist" }
py -3.13 -m evidence_review workspace bind --repository-root . --workspace $acceptanceWorkspace
py -3.13 -m evidence_review workspace active --repository-root .
```

Expected: `status=ACTIVE` and the returned snapshot/hash match the chosen workspace. The absolute path is not copied into committed files or PR comments.

- [ ] **Step 2: Run S1, S2, S3 through full formal review**

For each case execute `workspace active` → `review-question prepare-plan` → external planner output → `review-question prepare` → Track A attempt/submit → Track B attempt/submit/finalize. Verify all three run artifacts contain the same `evidence_snapshot_hash`.

Required evidence:

```text
S1 사업대상지 최소면적 → 1,000㎡
S2 승강장 경계 → 250m + 심의 조건부 350m
S3 임대형기숙사 주차 → 제13조② lineage
```

- [ ] **Step 3: Run the approved compound I1–I7 question on the same binding**

Inspect `retrieval-trace.json`, `track-a-bundle.json`, `run-metrics.json`, and `final-review-packet.json`.

Required outcomes:

```text
I1 RESOLVED with direct minimum-area evidence
I2 CONDITIONAL with 3 facets and 3 comparisons
I3 correct source-gap state; no paragraph ① dormitory false lineage
I4 mixed-use/dormitory evidence assigned to the correct issue
I5 direct 400% evidence
I6 direct 2분의 1 + committee/procedure evidence
I7 local rule retained; external authority gap explicit when not ingested
```

- [ ] **Step 4: Verify retry metrics**

No external-wait event may occur after successful validation of the same Track stage. Track B finalization recovery must reuse validated output and must not add Track B attempt 2.

- [ ] **Step 5: Post sanitized acceptance evidence to PR-A**

Include exact HEAD, automated test counts, S1–S3 `3/3`, I1–I7 status table, snapshot hash prefix, Track A/B attempt counts, and explicit source gaps. Do not post the absolute workspace path or proprietary source material.

---

### Task 12: Merge PR-A, Close #116, and Supersede #117

**Files:**
- PR/Issue metadata only.

**Interfaces:**
- PR-A is the only replacement allowed to close #116.

- [ ] **Step 1: Update PR-A body after every gate passes**

Change `Refs #116` to `Fixes #116` only after real-corpus PASS. State that PR #117 was selectively replaced on current main and was not merged wholesale.

- [ ] **Step 2: Mark ready and merge with expected HEAD protection**

Verify the PR HEAD has not moved since acceptance; merge using the repository's normal merge method.

- [ ] **Step 3: Verify #116 closure**

If auto-close did not occur, close Issue #116 as `completed` and link the merged PR plus acceptance comment.

- [ ] **Step 4: Supersede PR #117**

Add a final comment that PR-A replaced its valid behavior on current main, then close #117 without merging.

- [ ] **Step 5: Record post-merge main for PR-B**

```powershell
git fetch origin main
git rev-parse origin/main
```

The resulting SHA is the mandatory PR-B base.
