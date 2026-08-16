# Issue #116 Real Review Correctness Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** PR #115 이후 남아 있는 실제 ERS 회귀를 수정해, 올바른 evidence snapshot에서 올바른 issue/facet 근거만 채택하고, 필요한 수치·조건 비교를 결정론적으로 수행한 경우에만 `RESOLVED`/`CONDITIONAL`/`READY_FOR_HUMAN_REVIEW`로 진행하도록 한다.

**Architecture:** 기존 clause-first retrieval, issue-aware bundle, fail-closed finalizer는 유지한다. 새 수정은 `workspace/snapshot provenance → operational subclause/local citation → subject/section relevance → issue facet compilation/coverage → deterministic fact-rule comparison → end-to-end lineage → question-scope reference sufficiency` 순서로 correctness gate를 강화한다. correctness가 고정된 뒤에만 Track A/B retry orchestration을 최적화한다. prompt tuning만으로 correctness를 보완하지 않고, 모든 판정은 테스트 가능한 deterministic contract로 만든다.

**Tech Stack:** Python 3.13, SQLite/FTS5, immutable dataclass contracts, canonical JSON/SHA-256, pytest, Ruff, mypy, compileall.

**Issue:** #116 — Real ERS regression: clause granularity·issue retrieval·citation locality 보강

**Baseline:** PR #115 merge commit `446a432483395c4eb51000dec36d3b5680a6e1dd`

---

## 1. 현재 상태와 이번 계획의 범위

PR #115에서 다음 기반은 이미 구현됐다. 이번 작업에서 다시 만들지 않는다.

- element-only workspace의 clause/index backfill
- clause-first retrieval 및 citation-grade element materialization
- 사용자 fact 기반 numeric decontamination
- bounded fallback과 legal reference expansion
- `SOURCE_NOT_INGESTED` / `REFERENCE_TARGET_MISSING` 구분
- 기본 issue-aware retrieval/coverage
- Track A claim/citation issue lineage 검증
- coverage/human-review aware confidence
- production-shaped real-workspace E2E

#116 재검증에서 남은 핵심은 단순 `hit가 존재하는가`가 아니다. 완료 조건은 다음이다.

```text
올바른 workspace/snapshot
→ 올바른 semantic subclause
→ 올바른 issue/subject/section
→ 필요한 모든 facet 근거 확보
→ 사용자 fact와 rule threshold의 deterministic comparison
→ lineage/reference sufficiency 검증
→ 그 이후에만 READY/ABSTAIN 결정
```

대표 false positive는 반드시 회귀 테스트로 고정한다.

```text
질문: 역세권 부지의 제2종일반주거지역 → 준주거지역 변경 요건
잘못 채택된 근거: 2-3-2. 간선도로변의 용도지역 변경 기준

역세권 용도지역 변경 != 간선도로변 용도지역 변경
```

또한 #116 본문의 복합 질문 I1~I7 acceptance를 그대로 유지한다.

---

## 2. Correctness invariants

구현 중 아래 invariant를 깨는 변경은 acceptance하지 않는다.

1. **Snapshot identity:** 실행에 사용한 evidence snapshot이 명확하지 않거나 prepared/resumed run과 현재 workspace snapshot이 다르면 retrieval miss로 위장하지 않고 fail closed 한다.
2. **Subject/section relevance:** lexical overlap이 있어도 질문 subject/mechanism/section과 충돌하는 clause는 selected evidence가 될 수 없다.
3. **Match locality:** citation은 clause의 앞 N개 element가 아니라 실제 semantic match와 가장 가까운 source element/page/bbox를 우선한다.
4. **Facet completeness:** issue가 요구하는 모든 독립 rule facet을 확보하지 못하면 generic `rule` 1건만으로 `RESOLVED`가 될 수 없다.
5. **Deterministic comparison:** 사용자 fact와 rule threshold 비교 결과는 모델이 계산하거나 수정하지 않는다.
6. **Lineage:** `QuestionIssue → SearchRequest/facet → RetrievalMatch → selected evidence → comparison → Track A claim → citation → IssueResult`를 추적할 수 있어야 한다.
7. **Reference sufficiency:** 질문이 요구한 reference scope가 충족되지 않으면 unrelated/local citation이 존재하더라도 READY로 진행하지 않는다.
8. **Retry isolation:** deterministic correctness failure는 LLM retry로 해결하려 하지 않는다. retry는 typed transient failure에만 bounded하게 적용한다.
9. **No regression:** #115에서 확보한 clause backfill, source-gap typing, confidence/human-review fail-close를 유지한다.

---

## 3. 구현 순서

### Task 0 — #116 실제 회귀 baseline과 snapshot provenance를 고정한다

**Files:**
- Modify: `src/evidence_review/review_question.py`
- Modify: `src/evidence_review/evidence/snapshot.py`
- Modify: `src/evidence_review/retrieval/trace.py`
- Modify: `tests/integration/review_question/test_real_review_full_e2e.py`
- Create: `tests/integration/review_question/test_issue_116_correctness_e2e.py`
- Create: `tests/unit/review_question/test_evidence_snapshot_binding.py`

**Step 1: failing tests를 먼저 작성한다.**

다음 경우를 fixture로 고정한다.

- prepared run snapshot과 active workspace snapshot이 동일함
- prepared/resumed run snapshot과 active workspace snapshot이 다름
- mismatch가 `RETRIEVAL_MISS`/일반 `ABSTAIN`으로 내려가지 않고 typed failure가 됨
- issue #116의 실제 parser-shaped corpus에서 I1~I7 질문과 false-positive zoning 질문을 재현함

권장 reason code:

```text
EVIDENCE_SNAPSHOT_MISMATCH
WORKSPACE_EVIDENCE_MISMATCH
STALE_REVIEW_RUN
```

**Step 2: RED를 확인한다.**

```bash
python -m pytest -q tests/unit/review_question/test_evidence_snapshot_binding.py tests/integration/review_question/test_issue_116_correctness_e2e.py
```

현재 main에서 새 invariant가 아직 구현되지 않은 케이스가 실패해야 한다.

**Step 3: 최소 구현한다.**

retrieval 시작 직전에 실제 열린 DB에서 최소 다음 provenance를 canonical artifact에 기록한다.

```json
{
  "evidence_snapshot_hash": "...",
  "evidence_db_sha256": "...",
  "schema_version": 4,
  "retrieval_record_count": 1614,
  "clause_record_count": 197
}
```

절대경로는 immutable artifact에 넣지 않는다. prepared/resumed run은 snapshot identity가 다르면 조용히 재사용하지 않는다.

**Step 4: GREEN을 확인한다.**

```bash
python -m pytest -q tests/unit/review_question/test_evidence_snapshot_binding.py tests/integration/review_question/test_issue_116_correctness_e2e.py
```

**Step 5: commit checkpoint.**

```bash
git add src/evidence_review/review_question.py src/evidence_review/evidence/snapshot.py src/evidence_review/retrieval/trace.py tests/unit/review_question/test_evidence_snapshot_binding.py tests/integration/review_question/test_issue_116_correctness_e2e.py tests/integration/review_question/test_real_review_full_e2e.py
git commit -m "fix: bind review runs to evidence snapshots"
```

---

### Task 1 — operational subclause granularity와 match-local citation을 강화한다

**Files:**
- Modify: `src/evidence_review/evidence/clause_materialization.py`
- Modify: `src/evidence_review/retrieval/clause_resolution.py`
- Modify: `src/evidence_review/retrieval/index.py`
- Modify: `tests/unit/evidence/test_clause_materialization.py`
- Modify: `tests/integration/retrieval/test_clause_resolution.py`
- Modify: `tests/integration/retrieval/test_real_parser_workspace_regression.py`

**Step 1: structural RED tests를 작성한다.**

운영기준 계층을 최소 다음 수준까지 독립 derived clause로 materialize해야 한다.

```text
4-4-2.
  나. 준공업지역의 경우
    1) 기본용적률 및 공공기여율
      가) 기본용적률 : 400% 이하
    2) 용도별 비율 등
      나) 공장비율 10% 이상인 경우 산업부지 확보비율 ...
```

권장 structural key 예:

```text
4-4-2/나/1/가
4-4-2/나/2/나
```

테스트는 다음을 확인한다.

- parser element는 source truth로 그대로 유지
- derived subclause가 bounded source elements만 포함
- subclause가 source element/page/bbox provenance를 잃지 않음
- 400%와 산업부지 비율 근거가 서로 다른 semantic subclause로 검색 가능

**Step 2: citation locality RED test를 작성한다.**

`resolve_clause_to_evidence()`가 `ORDER BY ... LIMIT N`으로 clause 앞부분만 반환하는 상황을 재현하고, 실제 query match가 뒤쪽 source element에 있을 때 해당 element가 첫 citation으로 선택되어야 한다.

**Step 3: RED를 확인한다.**

```bash
python -m pytest -q tests/unit/evidence/test_clause_materialization.py tests/integration/retrieval/test_clause_resolution.py tests/integration/retrieval/test_real_parser_workspace_regression.py
```

**Step 4: 최소 구현한다.**

- heading hierarchy를 deterministic stack으로 분해한다.
- clause/subclause → source element 연결은 source ordering과 revision identity를 유지한다.
- resolver는 matched span/token overlap/source-element distance를 deterministic tuple로 정렬한다.
- tie-break는 `evidence_id` 등 stable key를 사용한다.
- max citation budget은 유지한다.

권장 정렬 우선순위:

```text
exact matched source element
→ same structural leaf + highest token overlap
→ nearest source order distance
→ stable evidence_id
```

**Step 5: GREEN + 기존 migration/backfill 회귀를 확인한다.**

```bash
python -m pytest -q tests/unit/evidence/test_clause_materialization.py tests/integration/retrieval/test_clause_resolution.py tests/integration/retrieval/test_real_parser_workspace_regression.py tests/integration/review_question/test_real_workspace_clause_repair_e2e.py
```

**Step 6: commit checkpoint.**

```bash
git commit -am "fix: materialize local operational subclauses"
```

---

### Task 2 — subject/section-aware evidence relevance gate를 추가한다

**Files:**
- Create: `src/evidence_review/retrieval/relevance.py`
- Modify: `src/evidence_review/retrieval/issue_bundle.py`
- Modify: `src/evidence_review/retrieval/fallback.py`
- Modify: `src/evidence_review/retrieval/trace.py`
- Modify: `tests/unit/retrieval/test_claim_issue_relevance.py`
- Modify: `tests/integration/retrieval/test_real_review_retrieval_relevance.py`
- Create: `tests/unit/retrieval/test_subject_section_relevance.py`

**Step 1: 핵심 false-positive RED test를 작성한다.**

```text
question subject = 역세권 용도지역 변경
candidate section = 간선도로변 용도지역 변경 기준
expected = reject
```

generic token인 `용도지역`, `변경`, `기준`이 겹쳐도 subject/mechanism anchor가 충돌하면 candidate를 coverage 대상에서 제외한다.

**Step 2: 정상 positive control도 작성한다.**

- 역세권 질문 ↔ 역세권 변경 기준: accept
- 간선도로변 질문 ↔ 간선도로변 변경 기준: accept
- 실제로 양쪽 subject를 함께 규정하는 clause: multi-subject evidence로 accept 가능

**Step 3: first-non-empty fallback 회귀를 같이 고정한다.**

약한 variant가 irrelevant hit를 반환해도 fallback이 즉시 종료되지 않고 stronger semantic anchor variant를 bounded하게 평가해야 한다.

```text
hit exists != relevance success
```

**Step 4: RED를 확인한다.**

```bash
python -m pytest -q tests/unit/retrieval/test_subject_section_relevance.py tests/unit/retrieval/test_claim_issue_relevance.py tests/integration/retrieval/test_real_review_retrieval_relevance.py
```

**Step 5: deterministic relevance score/gate를 구현한다.**

모델 호출 없이 최소 다음 신호를 조합한다.

- issue/search-request subject anchors
- clause heading/section anchors
- explicit legal mechanism anchors
- hard numeric/legal anchors
- conflicting sibling-section anchors
- exact structural path/heading match

relevance 결과는 단순 float만 남기지 말고 traceable reason을 보존한다.

```text
ACCEPT_SUBJECT_MATCH
ACCEPT_SECTION_MATCH
REJECT_SUBJECT_CONFLICT
REJECT_MECHANISM_CONFLICT
REJECT_REQUIRED_ANCHOR_MISSING
```

**Step 6: rejected candidate가 coverage/Track A로 전달되지 않는지 확인한다.**

**Step 7: commit checkpoint.**

```bash
git add src/evidence_review/retrieval/relevance.py src/evidence_review/retrieval/issue_bundle.py src/evidence_review/retrieval/fallback.py src/evidence_review/retrieval/trace.py tests/unit/retrieval/test_subject_section_relevance.py tests/unit/retrieval/test_claim_issue_relevance.py tests/integration/retrieval/test_real_review_retrieval_relevance.py
git commit -m "fix: reject subject-mismatched legal evidence"
```

---

### Task 3 — compound issue를 deterministic facet plan으로 컴파일한다

**Files:**
- Create: `src/evidence_review/retrieval/facets.py`
- Modify: `src/evidence_review/review_question.py`
- Modify: `src/evidence_review/retrieval/issue_bundle.py`
- Modify: `src/evidence_review/retrieval/coverage.py`
- Modify: `src/evidence_review/retrieval/models.py`
- Modify: `tests/unit/retrieval/test_coverage.py`
- Modify: `tests/unit/review_question/test_fact_rule_query_adapter.py`
- Create: `tests/unit/retrieval/test_issue_facet_compiler.py`

**Design decision:** QuestionPlan v2의 공개 직렬화 계약을 이번 이슈에서 즉시 깨지 않는다. 기존 `QuestionIssue`, `SearchRequest`, preserved `QuestionFact`를 입력으로 받아 deterministic `CompiledIssuePlan`을 만들고, run input/trace에 facet lineage를 저장한다. 실제 구현 중 planner가 명시적 facet field 없이는 재현 불가능하다는 RED test가 확인되는 경우에만 별도 QuestionPlan version bump를 한다.

**Step 1: I2 facet RED test를 작성한다.**

I2는 하나의 `rule` role이 아니라 최소 다음 세 facet을 요구한다.

```text
I2/distance-normal-threshold
I2/distance-conditional-threshold
I2/minimum-area-threshold
```

테스트는 generic rule evidence 하나만 있어서는 `RESOLVED`가 되지 않음을 확인한다.

**Step 2: I3/I4 lineage facet을 고정한다.**

```text
I3/public-supported-private-rental-parking
I4/dormitory-parking
I4/mixed-use-separate-standards
```

제13조③ 복합 적용 근거는 I4의 `mixed-use-separate-standards`를 충족해야 한다. query-origin이 I3였다는 이유만으로 I3에만 귀속되면 실패해야 한다.

**Step 3: RED를 확인한다.**

```bash
python -m pytest -q tests/unit/retrieval/test_issue_facet_compiler.py tests/unit/retrieval/test_coverage.py tests/unit/review_question/test_fact_rule_query_adapter.py
```

**Step 4: 최소 compiler를 구현한다.**

`CompiledIssuePlan`은 최소 다음을 가진다.

```text
issue_id
facet_id
role
query_terms / legal anchors
fact_operand_ids
required = true|false
```

compiler는 사용자 fact 숫자를 rule search must-token으로 넣지 않고 comparison operand로 분리한다. facet ID와 ordering은 동일 입력에 대해 항상 동일해야 한다.

**Step 5: coverage를 facet-aware로 확장한다.**

기존 `required_evidence_roles`는 상위 role gate로 유지하고, 그 아래에서 required facet subset을 검사한다.

```text
role coverage PASS
AND required facet coverage PASS
→ RESOLVED/CONDITIONAL candidate
```

누락된 facet은 typed gap으로 trace에 남긴다. 예:

```text
MISSING_REQUIRED_FACET
```

**Step 6: commit checkpoint.**

```bash
git add src/evidence_review/retrieval/facets.py src/evidence_review/review_question.py src/evidence_review/retrieval/issue_bundle.py src/evidence_review/retrieval/coverage.py src/evidence_review/retrieval/models.py tests/unit/retrieval/test_issue_facet_compiler.py tests/unit/retrieval/test_coverage.py tests/unit/review_question/test_fact_rule_query_adapter.py
git commit -m "fix: require deterministic issue facet coverage"
```

---

### Task 4 — 사용자 fact와 rule threshold 비교를 deterministic engine으로 이동한다

**Files:**
- Create: `src/evidence_review/rule_engine/fact_rule_comparison.py`
- Modify: `src/evidence_review/review_question.py`
- Modify: `src/evidence_review/llm_layer/track_a.py`
- Modify: `src/evidence_review/contracts/engines.py`
- Modify: `tests/unit/llm_layer/test_numeric_grammar.py`
- Modify: `tests/unit/llm_layer/test_track_a_validator.py`
- Create: `tests/unit/rule_engine/test_fact_rule_comparison.py`
- Modify: `tests/integration/review_question/test_issue_116_correctness_e2e.py`

**Step 1: I2 exact comparisons를 RED로 고정한다.**

```text
1,500㎡ >= 1,000㎡  → true
300m > 250m         → true
300m <= 350m        → true
```

그 결과 substantive issue status는 `CONDITIONAL`이어야 한다.

**Step 2: unit normalization을 함께 테스트한다.**

```text
1,500㎡ == 1500m2
300 m == 300미터
400% == 400퍼센트
```

단위가 호환되지 않거나 threshold parser가 불확실하면 임의 변환하지 않고 fail closed 한다.

**Step 3: RED를 확인한다.**

```bash
python -m pytest -q tests/unit/rule_engine/test_fact_rule_comparison.py tests/unit/llm_layer/test_numeric_grammar.py tests/integration/review_question/test_issue_116_correctness_e2e.py
```

**Step 4: canonical comparison result를 구현한다.**

결과에는 최소 다음을 포함한다.

```text
comparison_id
issue_id
facet_id
left_operand
operator
right_operand
normalized_unit
outcome
source_evidence_ids
result_hash
```

`result_hash`는 canonical JSON 기반 SHA-256으로 계산한다.

**Step 5: Track A authority boundary를 강화한다.**

Track A는 comparison을 설명할 수만 있고 계산 결과를 새로 만들거나 변경할 수 없다. claim이 deterministic comparison과 충돌하면 validation failure가 되어야 한다.

**Step 6: GREEN을 확인한다.**

```bash
python -m pytest -q tests/unit/rule_engine/test_fact_rule_comparison.py tests/unit/llm_layer/test_track_a_validator.py tests/integration/review_question/test_issue_116_correctness_e2e.py
```

**Step 7: commit checkpoint.**

```bash
git commit -am "fix: evaluate fact rule thresholds deterministically"
```

---

### Task 5 — retrieval부터 final issue result까지 lineage를 완결한다

**Files:**
- Modify: `src/evidence_review/evidence/lineage_contract.py`
- Modify: `src/evidence_review/evidence/lineage_graph.py`
- Modify: `src/evidence_review/retrieval/trace.py`
- Modify: `src/evidence_review/llm_layer/track_a.py`
- Modify: `src/evidence_review/abstention/finalizer.py`
- Modify: `tests/unit/evidence/test_lineage_contract.py`
- Modify: `tests/unit/evidence/test_lineage_graph.py`
- Modify: `tests/unit/llm_layer/test_track_a_lineage_enrichment.py`
- Create: `tests/unit/evidence/test_issue_facet_comparison_lineage.py`

**Step 1: broken-lineage RED tests를 작성한다.**

다음 중 하나라도 끊기면 finalization이 성공하면 안 된다.

```text
QuestionIssue
→ facet/search request
→ RetrievalMatch
→ selected evidence
→ ComparisonResult (해당 시)
→ Claim
→ Citation
→ IssueResult
```

특히 `selected evidence의 issue_ids가 query-origin과 같으니 신뢰한다`는 동작을 금지한다. Task 2 relevance 결과와 Task 3 facet assignment가 authoritative lineage source가 되어야 한다.

**Step 2: multi-issue evidence 규칙을 테스트한다.**

한 evidence가 복수 issue에 연결되려면 각각에 대해 relevance/facet eligibility가 독립적으로 PASS해야 한다.

**Step 3: RED를 확인한다.**

```bash
python -m pytest -q tests/unit/evidence/test_issue_facet_comparison_lineage.py tests/unit/evidence/test_lineage_contract.py tests/unit/evidence/test_lineage_graph.py tests/unit/llm_layer/test_track_a_lineage_enrichment.py
```

**Step 4: lineage nodes/edges를 확장하고 stable serialization을 구현한다.**

**Step 5: trace와 final artifact에서 issue별 provenance를 확인한다.**

**Step 6: commit checkpoint.**

```bash
git commit -am "fix: preserve issue facet lineage through finalization"
```

---

### Task 6 — question-scope-aware reference sufficiency를 finalizer hard gate로 만든다

**Files:**
- Modify: `src/evidence_review/retrieval/reference_projection.py`
- Modify: `src/evidence_review/retrieval/coverage.py`
- Modify: `src/evidence_review/abstention/finalizer.py`
- Modify: `tests/integration/abstention/test_finalizer.py`
- Modify: `tests/unit/review_question/test_reference_lineage_projection.py`
- Create: `tests/unit/abstention/test_question_scope_reference_sufficiency.py`

**Step 1: RED cases를 작성한다.**

- I7 local 제13조④는 존재하지만 외부 시행령 원문이 미수집인 경우: local rule은 보존하되 reference gap을 유지
- unrelated 주차 조항이 존재해도 I7을 `RESOLVED` 처리하지 않음
- I6에서 `2분의 1까지 완화` 직접 근거 없이 generic 산업부지 clause만 있으면 resolved 불가
- primary question scope에 필수 reference가 빠졌는데 다른 citation 수가 충분하다는 이유로 READY 불가

**Step 2: RED를 확인한다.**

```bash
python -m pytest -q tests/unit/abstention/test_question_scope_reference_sufficiency.py tests/unit/review_question/test_reference_lineage_projection.py tests/integration/abstention/test_finalizer.py
```

**Step 3: sufficiency contract를 구현한다.**

reference sufficiency는 citation count가 아니라 issue/facet/reference requirement 단위로 판단한다.

```text
LOCAL_RULE_PRESENT
EXTERNAL_REFERENCE_REQUIRED
EXTERNAL_REFERENCE_MISSING
REFERENCE_SCOPE_SATISFIED
```

외부 원문 미수집은 `SOURCE_NOT_INGESTED`와 연결하고, 실제 corpus에 없는 내용을 생성하지 않는다.

**Step 4: finalizer에서 fail closed 한다.**

`READY_FOR_HUMAN_REVIEW`는 모든 resolved/conditional issue의 required facet/reference가 충분하고 Track A/B validation이 통과한 경우에만 가능해야 한다.

**Step 5: commit checkpoint.**

```bash
git commit -am "fix: gate readiness on reference sufficiency"
```

---

### Task 7 — Track A/B retry와 stale-output atomicity를 correctness 이후에 정리한다

**Files:**
- Modify: `src/evidence_review/review_question.py`
- Modify: `src/evidence_review/review_run.py`
- Modify: `src/evidence_review/workflow/events.py`
- Modify: `tests/integration/review_question/test_review_question_cli.py`
- Modify: `tests/integration/review_run/test_review_run.py`
- Create: `tests/unit/review_question/test_llm_retry_policy.py`

**Step 1: 현재 회귀를 RED로 고정한다.**

#116 run의 observed pattern을 재현한다.

```text
Track A: VALUEERROR → FILEEXISTSERROR → success
Track B: success → 불필요한 second external attempt
```

**Step 2: retry reason을 typed contract로 만든다.**

retry 가능:

```text
TRANSIENT_EXTERNAL_FAILURE
MALFORMED_UNTRUSTED_OUTPUT
```

retry 금지:

```text
UNRELATED_EVIDENCE
MISSING_REQUIRED_FACET
REFERENCE_INSUFFICIENT
EVIDENCE_SNAPSHOT_MISMATCH
TRACK_B_INPUT_MISMATCH
```

**Step 3: output publication atomicity를 테스트한다.**

validated output은 temp file → fsync/close → atomic replace 또는 repository가 이미 사용하는 동등한 안전 패턴으로 게시한다. stale invalid output 때문에 정상 retry가 `FILEEXISTSERROR`에 빠지면 안 된다.

**Step 4: success short-circuit를 구현한다.**

Track A 또는 Track B가 validate 성공한 순간 추가 external attempt를 호출하지 않는다.

**Step 5: metrics acceptance를 추가한다.**

```text
validated_success_after_attempt_n → no attempt_n+1
retry_count == 실제 재시도 횟수
external_wait_total_ms == 실제 external calls 합계
```

**Step 6: targeted GREEN을 확인한다.**

```bash
python -m pytest -q tests/unit/review_question/test_llm_retry_policy.py tests/integration/review_question/test_review_question_cli.py tests/integration/review_run/test_review_run.py
```

**Step 7: commit checkpoint.**

```bash
git commit -am "fix: bound review model retries after validation"
```

---

### Task 8 — #116 I1~I7 production-shaped acceptance를 완성한다

**Files:**
- Modify: `tests/integration/review_question/test_issue_116_correctness_e2e.py`
- Modify: `tests/integration/review_question/test_real_review_full_e2e.py`
- Modify: `tests/integration/retrieval/test_real_review_retrieval_relevance.py`
- Modify: `tests/integration/retrieval/test_real_parser_workspace_regression.py`
- Create: `docs/acceptance/issue-116/README.md`

**Step 1: acceptance matrix를 자동화한다.**

| Issue | 필수 acceptance |
| --- | --- |
| I1 | `1,000㎡` 직접 근거; 필요한 경우 `5,000㎡` 예외; broad zoning clause가 핵심 근거를 대체하지 않음 |
| I2 | 250m + 조건부 350m + 1,000㎡; `1500>=1000`, `300>250`, `300<=350`; `CONDITIONAL` |
| I3 | 제13조① 등 공공지원민간임대주택 기준의 올바른 lineage |
| I4 | 제13조②/③, 복합 시 각 유형 기준 각각 적용; 제13조③이 I4 facet을 충족 |
| I5 | 준공업지역 400% 직접 근거와 관련 요건/심의 근거 |
| I6 | 산업부지 확보비율 `2분의 1까지 완화` 직접 citation |
| I7 | 제13조④ local rule 유지 + 외부 reference gap 정확히 표시 |
| zoning false positive | 역세권 질문에 간선도로변 기준만으로 READY 금지 |

**Step 2: three-simple-query smoke를 별도 유지한다.**

동일 evidence snapshot에서 최소 다음 3개는 3/3 retrieval success여야 한다.

```text
사업대상지 최소면적 → 1,000㎡
역세권 승강장 거리 → 250m + 조건부 350m
임대형기숙사 주차기준 → 제13조② / 별표2 인용 관계
```

**Step 3: issue-level artifact를 assertion한다.**

테스트는 final text만 보지 않고 다음을 함께 검증한다.

- selected evidence IDs
- issue/facet lineage
- comparison results/hash
- coverage status/gap codes
- reference sufficiency
- confidence hard gates
- retry metrics
- final status

**Step 4: targeted suite를 실행한다.**

```bash
python -m pytest -q \
  tests/integration/retrieval/test_real_parser_workspace_regression.py \
  tests/integration/retrieval/test_real_review_retrieval_relevance.py \
  tests/integration/review_question/test_issue_116_correctness_e2e.py \
  tests/integration/review_question/test_real_review_full_e2e.py
```

**Step 5: acceptance 문서에 exact HEAD와 before/after matrix를 기록한다.**

**Step 6: commit checkpoint.**

```bash
git add tests/integration docs/acceptance/issue-116/README.md
git commit -m "test: lock issue 116 real review acceptance"
```

---

### Task 9 — 전체 회귀 및 release-grade 검증

**Files:**
- Verify only unless failures require scoped fixes

**Step 1: targeted correctness suites.**

```bash
python -m pytest -q tests/unit/retrieval tests/unit/review_question tests/unit/evidence tests/unit/llm_layer tests/unit/rule_engine tests/integration/retrieval tests/integration/review_question tests/integration/abstention tests/integration/review_run
```

**Step 2: full pytest.**

```bash
python -m pytest -q
```

**Step 3: static validation.**

```bash
python -m ruff check src tests
python -m mypy src/evidence_review
python -m compileall -q src
```

**Step 4: Python 3.13 runtime/package smoke.**

저장소의 현재 Python 지원 정책에 맞춰 3.13만 검증하고, 과거 3.11 matrix를 다시 추가하지 않는다.

**Step 5: exact HEAD 검증 기록.**

최종 acceptance에는 최소 다음을 기록한다.

```text
HEAD
full pytest count
Ruff PASS
mypy PASS
compileall PASS
issue #116 targeted E2E PASS
I1~I7 coverage matrix
snapshot provenance
retry metrics
```

**Step 6: implementation PR 설명에 `Fixes #116`을 넣는 것은 이 acceptance가 모두 PASS한 뒤에만 허용한다.**

이번 계획 문서 PR은 구현이 아니므로 `Refs #116`만 사용한다.

---

## 4. 권장 PR 분할

구현을 한 PR에 모두 넣을 수 있지만 리뷰 위험을 줄이려면 아래 순서가 더 안전하다.

1. **PR A — correctness foundation**: Task 0~2
2. **PR B — facet/comparison/lineage**: Task 3~6
3. **PR C — orchestration + final acceptance**: Task 7~9

단, 각 PR은 직전 PR의 exact HEAD를 base로 검증해야 하며, 병렬 구현으로 동일 contract를 중복 수정하지 않는다.

---

## 5. 완료 정의

#116은 단순히 검색 hit가 늘었다고 닫지 않는다. 아래가 모두 성립해야 완료다.

- active evidence snapshot provenance가 run artifact에서 검증 가능
- operational subclause가 과도하게 큰 parent clause에 묻히지 않음
- match-local citation이 source element/page/bbox provenance를 유지
- 역세권/간선도로변 같은 sibling subject 오탐 차단
- I2처럼 복합 판단이 독립 facet으로 분해됨
- required facet 미충족 issue가 generic rule 하나로 `RESOLVED`되지 않음
- 사용자 fact ↔ rule threshold 비교가 deterministic result로 고정됨
- I1~I7 selected evidence와 issue lineage가 acceptance matrix와 일치
- external reference 미수집은 정확한 source/reference gap으로 남음
- 잘못된 READY보다 보수적 unresolved/ABSTAIN을 선택
- Track A/B validation 성공 이후 추가 external retry가 없음
- full pytest/Ruff/mypy/compileall 및 Python 3.13 smoke PASS

이 조건이 충족된 exact HEAD만 #116 implementation 완료 후보로 본다.
