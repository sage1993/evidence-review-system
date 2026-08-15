# 실제 ERS_REVIEW 검색·관련성 실패 상세 구현 계획

> **For Codex:** 구현 시 `superpowers:executing-plans`를 사용하고, 각 Task는 **실패 테스트 작성 → 실패 확인 → 최소 구현 → 해당 테스트 PASS → 관련 회귀 테스트 PASS → 커밋** 순서로 진행한다.

## 1. 목적

실제 `$ERS_REVIEW` 검증에서 확인된 다음 두 종류의 실패를 함께 해결한다.

1. **RETRIEVAL FAILURE**: 원문과 파싱 데이터에 존재하는 핵심 근거를 검색하지 못함
2. **RELEVANCE FAILURE**: 핵심 근거를 놓친 상태에서 질문과 직접 관계없는 citation/claim이 최종 답변에 노출됨

대표 실패 질문은 다음 항목을 동시에 포함한다.

- 안심주택 일반 사업대상지 최소 면적
- 역 승강장 경계 300m, 1,500㎡ 부지의 사업대상지 적격성
- 준공업지역에서 공공지원민간임대주택과 임대형기숙사를 복합하는 경우의 주차기준
- 공동주택 부분 용적률 400% 완화
- 산업부지 확보비율
- 지구단위계획에 따른 추가 주차기준 완화

최종 목표는 단순 recall 개선이 아니라 다음 세 가지를 동시에 보장하는 것이다.

- **존재하는 근거는 찾는다.**
- **없는 근거는 왜 없는지 구분한다.**
- **질문과 관계없는 근거/claim은 최종 답변에 진입하지 못한다.**

---

## 2. 현재 구조에서 확인된 제약

### 2.1 검색 의미 단위와 citation 단위가 혼재

현재 FTS의 주 검색 단위는 parser `elements`/`tables`/`visuals`이고, `retrieval_records`는 `page_id`, `page_number`, `bbox_json`을 전제로 한다. 반면 법규 의미 단위는 이미 `clauses`에 존재한다.

따라서 역할을 다음과 같이 분리한다.

```text
clause/subclause = 의미 검색 단위
element/page/bbox = citation 위치 단위
table row/cell = 구조화된 표 근거 단위
```

### 2.2 복합질문의 issue가 global Top-K에서 경쟁

현재 여러 search request가 fusion 후 하나의 global `limit`을 공유한다. broad topic hit가 상위 후보를 점유하면 다른 issue의 exact hit가 탈락할 수 있다.

### 2.3 사용자 사실과 규칙 threshold가 분리되지 않음

예:

```text
Fact: station_distance = 300m
Rule lookup: 역 승강장 경계 기준
Retrieved thresholds: 250m / 350m
Deterministic comparison: 250 < 300 <= 350
```

`300m`와 `1,500㎡`는 사용자 사실이며, 찾아야 할 규정값이 아니다. 사용자 입력 숫자는 fail-closed로 보존하되 모든 lexical query의 must-token으로 강제하지 않는다.

### 2.4 Track A claim에 issue relevance 불변조건이 없음

현재 claim이 citation을 갖고 있더라도 그 citation이 사용자가 질문한 issue와 직접 연결되는지는 강제되지 않는다. 따라서 well-cited but unrelated claim이 살아남을 수 있다.

### 2.5 현재 finalizer는 일부 missing input도 전체 ABSTAIN 처리

부분답변을 구현하려면 retrieval만 고치는 것으로 부족하다. issue별 coverage를 finalizer까지 전달하고, global hard gate와 issue-scoped insufficiency를 분리해야 한다.

---

## 3. 핵심 설계 결정

| 항목 | 결정 |
| --- | --- |
| 검색 의미 단위 | clause/subclause |
| 최종 citation 단위 | element/page/bbox |
| 기존 element FTS | 삭제하지 않고 fallback/context용 유지 |
| QuestionPlan | v1 호환 유지 + 신규 v2 계약 |
| Evidence DB | clause retrieval 영속 구조 추가 시 schema v4 |
| 사용자 입력 숫자 | `QuestionFact`로 보존, rule query must-token에서 분리 |
| 검색 실행 | issue + evidence role별 실행 |
| 후보 선택 | per-issue reserve 후 global dedupe/budget |
| cross-reference | deterministic bounded BFS |
| relevance | Track A 이전 + claim validation에서 이중 강제 |
| partial answer | issue별 상태 판정 후 resolved issue만 답변 |
| global ABSTAIN | 전체 issue 실패 또는 global hard gate일 때 |
| LLM 권한 | issue 분해/query 제안까지만, evidence authority 확대 금지 |

---

# 4. 구현 Tasks

## Task 0 — 실제 실패 사례를 regression fixture로 고정

**Files**

```text
Create:
tests/fixtures/real_review_retrieval_relevance/
    question-plan.json
    expected-issues.json
    expected-evidence.json

tests/integration/retrieval/test_real_review_retrieval_relevance.py
```

### 구현

다음 issue를 독립적으로 고정한다.

| ID | Issue | 기대 핵심 근거 |
| --- | --- | --- |
| I1 | 일반 사업대상지 최소면적 | 1,000㎡ |
| I2 | 역 승강장 경계 300m 부지 | 250m 원칙 / 350m 조건 |
| I3 | 1,500㎡ 면적 적격성 | 최소면적 규칙과 비교 |
| I4 | 임대형기숙사/기타 주택 주차기준 | 조례 제13조 |
| I5 | 준공업지역 공동주택 400% | 기본용적률 400% 이하 |
| I6 | 산업부지 확보비율 | 관련 완화 기준 |
| I7 | 지구단위계획 추가 주차 완화 | 제13조제4항 및 참조규정 |

다음 항목은 forbidden evidence/claim으로 fixture에 고정한다.

```text
공장비율 10% 미만/이상 공공기여율
비주거 용도 위치 기준
364호 이상 관련 산식
```

### 검증

```bash
python -m pytest -q tests/integration/retrieval/test_real_review_retrieval_relevance.py
```

구현 전 현재 실패를 재현해야 한다.

---

## Task 1 — QuestionPlan v2 계약 고정

**Files**

```text
Modify:
src/evidence_review/contracts/question_plan.py
src/evidence_review/llm_layer/question_planner.py
src/evidence_review/llm_layer/templates/question-planner.md

tests/unit/llm_layer/test_question_planner.py
tests/unit/llm_layer/test_question_plan_numeric_units.py

Create:
tests/unit/contracts/test_question_plan_v2.py
```

### 계약

```python
EvidenceRole = Literal["supporting_fact", "rule"]

@dataclass(frozen=True, slots=True)
class QuestionIssue:
    id: str
    question: str
    depends_on: tuple[str, ...]
    required_evidence_roles: tuple[EvidenceRole, ...]

@dataclass(frozen=True, slots=True)
class SearchRequest:
    id: str
    issue_ids: tuple[str, ...]
    text: str
    kind: SearchKind
    source: AnchorSource
    role: EvidenceRole
```

`QuestionFact`는 사용자가 제공한 사실을 의미하고, `supporting_fact` retrieval은 외부 문서에서 확인해야 하는 사실을 의미한다. 두 개념을 혼동하지 않는다.

### Version 정책

- 신규 planner output: v2
- 기존 v1 decoder: 유지
- v1 artifact: internal v2 adapter를 통해 호환
- unknown field/version/role: fail-closed

### 필수 테스트

- v2 issue에 `required_evidence_roles` 필수
- v2 search request에 `role` 필수
- unknown role 실패
- unknown issue 참조 실패
- 사용자 숫자 `300m`, `1,500㎡`는 facts에 보존
- rule query에 사용자 숫자가 없어도 valid
- 사용자가 직접 명시한 법 조항 보존

---

## Task 2 — Evidence DB schema v4와 clause 검색 레코드 추가

**Files**

```text
Modify:
src/evidence_review/evidence/schema.sql
src/evidence_review/evidence/schema_version.py
src/evidence_review/retrieval/models.py
src/evidence_review/retrieval/index.py

Create:
src/evidence_review/evidence/migrations/v3_to_v4.py
tests/unit/retrieval/test_clause_index.py
tests/integration/migration/test_v3_to_v4.py

Modify:
tests/unit/evidence/test_schema_version.py
tests/integration/retrieval/test_index.py
```

### 권장 구조

```sql
CREATE TABLE clause_retrieval_records (
    clause_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    title TEXT NOT NULL,
    chapter TEXT,
    section TEXT,
    clause_number TEXT,
    normalized_text TEXT NOT NULL,
    source_element_ids_json TEXT NOT NULL
) STRICT;

CREATE VIRTUAL TABLE clause_fts USING fts5(
    clause_id UNINDEXED,
    title,
    chapter,
    section,
    clause_number,
    normalized_text,
    tokenize = 'unicode61'
);
```

### 원칙

- 기존 `clauses`는 canonical/parser evidence 역할 유지
- clause 의미 검색과 bbox citation record를 분리
- `source_element_ids`를 결정할 수 없는 clause에 임의 bbox를 붙이지 않음
- semantic retrieval은 성공했지만 exact citation으로 resolve할 수 없으면 `PARSE_GAP` 후보로 분류
- schema v3 DB는 명시적 migration 없이 current schema로 열지 않음

### 필수 테스트

- fresh v4 DB 생성
- v3 → v4 migration
- migration 재실행 안전성
- clause FTS rebuild 결정론
- snapshot hash 변경 시 stale index 거부

---

## Task 3 — Clause 검색 primitive와 citation resolver 구현

**Files**

```text
Modify:
src/evidence_review/retrieval/models.py
src/evidence_review/retrieval/index.py

Create:
src/evidence_review/retrieval/clause_resolution.py
tests/unit/retrieval/test_clause_resolution.py

Modify:
tests/integration/retrieval/test_fts_lexical_channels.py
```

### 모델

```python
@dataclass(frozen=True, slots=True)
class ClauseRetrievalHit:
    clause_id: str
    document_id: str
    revision_id: str
    title: str
    text: str
    source_element_ids: tuple[str, ...]
    channel_scores: tuple[ChannelScore, ...]
    matches: tuple[RetrievalMatch, ...]
    final_score: Decimal
```

### deterministic search primitive

```text
1. clause number / exact
2. phrase
3. token AND
4. token prefix AND
5. approved alias / compound decomposition
6. heading/section-scoped
```

한 단계에서 issue coverage가 충족되면 이후 fallback은 실행하지 않는다.

### citation materialization

```python
resolve_clause_to_evidence(
    clause_hit,
    *,
    max_source_elements: int,
) -> tuple[RetrievalHit, ...]
```

검색 relevance는 clause에서 결정하고, citation 위치는 source element에서 결정한다. element 자체의 FTS 점수가 낮다는 이유로 관련 clause를 제거하지 않는다.

---

## Task 4 — Planner에서 사용자 fact와 rule lookup 분리

**Files**

```text
Modify:
src/evidence_review/llm_layer/templates/question-planner.md
src/evidence_review/llm_layer/question_planner.py

Create:
tests/unit/llm_layer/test_question_planner_evidence_roles.py
```

### 기대 구조 예

```json
{
  "facts": [
    {"id": "F1", "text": "station_distance = 300m"},
    {"id": "F2", "text": "site_area = 1500㎡"}
  ],
  "issues": [
    {
      "id": "I1",
      "question": "역세권 거리 요건 충족 여부",
      "required_evidence_roles": ["rule"]
    }
  ],
  "search_requests": [
    {
      "id": "S1",
      "issue_ids": ["I1"],
      "role": "rule",
      "text": "역 승강장 경계 역세권 기준"
    }
  ]
}
```

다음과 같이 사용자 숫자를 규정값으로 가정하는 query는 regression 실패로 처리한다.

```text
역세권 300m 기준
사업 최소면적 1500㎡
```

---

## Task 5 — Issue-aware retrieval coordinator 및 global budget

**Files**

```text
Create:
src/evidence_review/retrieval/issue_bundle.py
src/evidence_review/retrieval/policy.py
tests/unit/retrieval/test_issue_bundle.py
tests/unit/retrieval/test_retrieval_budget.py

Modify:
src/evidence_review/retrieval/bundle.py
```

### 초기 policy

```python
@dataclass(frozen=True, slots=True)
class RetrievalPolicy:
    max_issues: int = 8
    max_queries_per_issue: int = 4
    per_issue_role_limit: int = 5
    global_candidate_cap: int = 80
    max_selected_evidence: int = 40
    reference_max_depth: int = 2
    reference_max_nodes_per_issue: int = 12
    reference_max_fanout: int = 6
```

이 값은 회귀/성능 테스트의 초기 baseline이며 필요 시 조정한다.

### 실행 순서

```text
for issue:
    for required role:
        execute issue queries
        reserve up to K candidates

merge issue pools
→ dedupe by semantic clause_id
→ preserve all retrieval matches / issue_ids
→ global_candidate_cap
→ max_selected_evidence
```

### 불변조건

한 issue의 broad hit가 다른 issue의 reserved exact candidate를 제거하면 안 된다.

### 필수 테스트

- I1 broad hit 30개 + I2 exact hit 1개 → I2 exact hit 유지
- 동일 clause가 search request 3개에 적중 → candidate 1개, lineage 3개 보존
- candidate cap 결정론
- 동일 입력 반복 시 ordering 결정론

---

## Task 6 — Issue별 adaptive fallback

**Files**

```text
Create:
src/evidence_review/retrieval/fallback.py
tests/unit/retrieval/test_adaptive_fallback.py

Modify:
src/evidence_review/retrieval/korean_variants.py
src/evidence_review/retrieval/issue_bundle.py
```

### fallback 순서

```text
EXACT_CLAUSE
→ PHRASE
→ TOKEN_AND
→ TOKEN_PREFIX
→ APPROVED_ALIAS
→ LEGAL_COMPOUND_DECOMPOSITION
→ HEADING_SCOPED
→ REFERENCE_EXPANSION
```

모든 fallback에는 provenance를 남긴다.

```python
FallbackTrace(
    issue_id="I5",
    search_request_id="S8",
    stage="APPROVED_ALIAS",
    input_query="준공업지역 용적률 완화",
    derived_query="준공업지역 기본용적률",
)
```

LLM이 자유롭게 동의어나 evidence authority를 확대하지 않는다.

### 필수 regression

```text
용적률 ↔ 기본용적률
주차기준 ↔ 주차장 설치기준
400% 완화 ↔ 기본용적률 400% 이하
```

---

## Task 7 — Bounded legal cross-reference traversal 강화

**Files**

```text
Modify:
src/evidence_review/retrieval/graph.py
src/evidence_review/retrieval/models.py

Create:
tests/unit/retrieval/test_reference_traversal_policy.py

Modify:
tests/integration/retrieval/test_structured_graph_retrieval.py
```

### 제한

```text
max_depth = 2
max_total_nodes_per_issue = 12
max_fanout_per_node = 6
visited_set
cycle_detection
authoritative_revision_filter
duplicate_suppression
missing_target_capture
```

### provenance

```python
ReferencePath(
    issue_id="I4",
    seed_clause_id="CLAUSE-13",
    target_clause_id="...",
    relation_types=("cited_clause", "rule_source"),
    depth=2,
)
```

reference-expanded clause는 원 질문과 lexical similarity가 낮더라도 검증된 explicit reference path가 있으면 단순 similarity 부족으로 제거하지 않는다.

### 필수 테스트

- A → B → A cycle
- A → A self reference
- fanout cap
- missing target
- outdated revision target
- depth limit

---

## Task 8 — Issue coverage state machine

**Files**

```text
Create:
src/evidence_review/retrieval/coverage.py
tests/unit/retrieval/test_issue_coverage.py

Modify:
src/evidence_review/retrieval/issue_bundle.py
```

### 상태 계약

```python
IssueStatus = Literal[
    "RESOLVED",
    "CONDITIONAL",
    "CONFLICT",
    "SOURCE_MISSING",
    "UNRESOLVED",
]

GapCode = Literal[
    "RETRIEVAL_MISS",
    "SOURCE_NOT_INGESTED",
    "REFERENCE_TARGET_MISSING",
    "PARSE_GAP",
    "AMBIGUOUS_RULE",
    "CONFLICTING_RULES",
]
```

```python
@dataclass(frozen=True, slots=True)
class IssueSupport:
    issue_id: str
    status: IssueStatus
    evidence_ids: tuple[str, ...]
    missing_roles: tuple[EvidenceRole, ...]
    gap_codes: tuple[GapCode, ...]
```

### coverage loop

```text
initial retrieval
→ required role coverage
→ 부족 issue만 fallback
→ reference expansion
→ coverage 재평가
→ specific gap status
```

모든 실패를 `MISSING_REQUIRED_INPUT` 하나로 처리하지 않는다.

---

## Task 9 — Track A claim/citation에 issue lineage 강제

**Files**

```text
Modify:
src/evidence_review/contracts/review.py
src/evidence_review/contracts/codecs.py
src/evidence_review/contracts/review_v2.py
src/evidence_review/llm_layer/track_a.py
src/evidence_review/llm_layer/templates/track-a.md
src/evidence_review/retrieval/claims.py

tests/unit/llm_layer/test_track_a_validator.py
tests/unit/retrieval/test_claim_citations.py

Create:
tests/unit/retrieval/test_claim_issue_relevance.py
```

### Claim 계약

```python
@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    issue_ids: tuple[str, ...]
    text: str
    citation_ids: tuple[str, ...]
    numeric_tokens: tuple[str, ...] = ()
```

### EvidenceExcerpt 계약

```python
@dataclass(frozen=True, slots=True)
class EvidenceExcerpt:
    citation: Citation
    text: str
    issue_ids: tuple[str, ...]
    role: EvidenceRole
```

### hard invariant

모든 claim의 모든 citation에 대해 적어도 하나의 issue overlap이 있어야 한다.

```python
set(claim.issue_ids) & set(cited_evidence.issue_ids)
```

비어 있으면 reject한다.

권장 오류코드:

```text
UNRELATED_CLAIM
CROSS_ISSUE_CITATION
UNKNOWN_CLAIM_ISSUE
```

### 핵심 regression

```text
Claim(issue=I5) + Citation(evidence issue=I4)
→ CROSS_ISSUE_CITATION
```

---

## Task 10 — review-question 파이프라인 전체에서 issue lineage 보존

**Files**

```text
Modify:
src/evidence_review/review_question.py
src/evidence_review/question_planning.py
src/evidence_review/planned_review_question.py
src/evidence_review/review_run.py

tests/unit/review_question/test_question_plan_adapter.py
tests/unit/review_question/test_retrieval_lineage_binding.py
tests/unit/review_question/test_track_a_submission.py
```

### evidence handoff

```json
{
  "citation": {},
  "text": "...",
  "issue_ids": ["I5"],
  "role": "rule",
  "retrieval_lineage": {
    "search_request_ids": ["S8"],
    "fallback_stage": "TOKEN_PREFIX",
    "reference_path": []
  }
}
```

중간 artifact가 issue 정보를 삭제하면 fail-closed 한다.

### 검증 lineage

```text
QuestionPlan issue
→ SearchRequest
→ RetrievalMatch
→ selected evidence
→ TrackABundle EvidenceExcerpt
→ Claim
→ Citation
```

동일 `issue_id`가 끝까지 재구성 가능해야 한다.

---

## Task 11 — Partial answer와 finalizer gate 재설계

**Files**

```text
Modify:
src/evidence_review/contracts/review.py
src/evidence_review/contracts/review_v2.py
src/evidence_review/abstention/gates.py
src/evidence_review/abstention/finalizer.py

Create:
tests/unit/abstention/test_issue_scoped_partial_answer.py

Modify:
tests/unit/abstention/test_gates.py
tests/integration/abstention/*
```

### global hard gate

다음은 하나라도 발생하면 전체 ABSTAIN한다.

```text
source hash mismatch
Track B rejection
integrity failure
unapproved authority
machine-set human decision
global engine corruption
```

### issue-scoped insufficiency

예:

```text
I1 RESOLVED
I2 UNRESOLVED
I3 RESOLVED
```

이면 I1/I3의 검증된 claim은 유지하고 I2만 근거 부족으로 표시한다.

### finalizer 정책

```text
resolved_issue_count == 0
→ ABSTAIN

resolved_issue_count > 0
AND no global hard gate
→ READY_FOR_HUMAN_REVIEW
```

packet에는 반드시 issue coverage를 직렬화한다.

```json
"issue_results": [
  {"issue_id": "I1", "status": "RESOLVED"},
  {"issue_id": "I2", "status": "UNRESOLVED"}
]
```

이번 변경에서 `FinalizerStatus`에 새로운 `PARTIAL` 값을 추가하지 않는다. 기존 downstream 호환성을 유지하고 `READY_FOR_HUMAN_REVIEW + issue_results`로 부분답변 여부를 표현한다.

---

## Task 12 — Confidence를 issue coverage 기반으로 보강

**Files**

```text
Modify:
src/evidence_review/confidence/policy.py
src/evidence_review/confidence/scorer.py
src/evidence_review/review_question.py

tests/unit/confidence/test_scorer.py
```

### 입력 예

```text
total_issues = 7
resolved_issues = 5
conditional_issues = 1
unresolved_issues = 1
```

기존 confidence weight를 임의로 재설계하지 않고 source/input completeness 입력을 issue coverage에 맞게 개선한다.

Global confidence가 높더라도 unresolved issue를 resolved처럼 표현하지 않는다.

---

## Task 13 — Retrieval trace / observability 추가

**Files**

```text
Create:
src/evidence_review/retrieval/trace.py
tests/unit/retrieval/test_retrieval_trace.py

Modify:
src/evidence_review/retrieval/issue_bundle.py
src/evidence_review/observability/run_metrics.py
src/evidence_review/review_question.py
```

### 최소 trace 필드

```text
issue_id
evidence_role
search_request_id
query_text
fallback_stage
raw_rank
raw_score
kept / dropped
drop_reason
clause_id
reference_path
selected_evidence_ids
coverage_status
citation_ids
```

이 trace는 일반 사용자 화면에 모두 노출하는 기능이 아니라 내부 진단 artifact다.

다음 질문에 deterministic하게 답할 수 있어야 한다.

- 왜 이 조항을 못 찾았는가?
- 왜 이 조항이 살아남았는가?
- 어떤 fallback에서 찾았는가?
- 어떤 budget 때문에 탈락했는가?
- 왜 이 citation이 이 claim에 연결됐는가?

---

## Task 14 — 실제 실패 사례 E2E를 acceptance gate로 전환

**Files**

```text
Modify:
tests/integration/retrieval/test_real_review_retrieval_relevance.py

Create/Modify as needed:
tests/integration/review_question/test_real_review_partial_answer.py
tests/golden/*
```

### Acceptance matrix

| 검증 | 통과 기준 |
| --- | --- |
| 최소면적 | 1,000㎡ 근거 검색 |
| 300m | 사용자 fact로 유지 |
| 역세권 rule | 250m / 350m 기준 확보 |
| 1,500㎡ | 최소면적 기준과 deterministic 비교 가능 |
| 주차기준 | 관련 제13조 확보 |
| 400% | 준공업지역 관련 clause 확보 |
| 산업부지 | 독립 issue에서 확보 |
| 추가 주차완화 | 제13조제4항 및 필요한 참조 확보 |
| cross-reference | bounded path 기록 |
| unrelated evidence | final selected evidence/claim에서 제외 |
| unsupported issue | issue-scoped unresolved |
| resolved issue | 다른 issue 실패에도 출력 |
| citation | claim issue와 overlap |
| duplicate | semantic clause 기준 dedupe |
| trace | 최종 evidence lineage 재구성 가능 |

### 최종 불변조건

```python
for claim in packet.claims:
    assert claim.issue_ids
    for citation_id in claim.citation_ids:
        evidence = evidence_by_citation[citation_id]
        assert set(claim.issue_ids) & set(evidence.issue_ids)
```

그리고 forbidden unrelated claim이 최종 packet에 없어야 한다.

---

## Task 15 — 전체 검증

### 집중 검증

```bash
python -m pytest -q \
  tests/unit/llm_layer \
  tests/unit/retrieval \
  tests/unit/review_question \
  tests/unit/abstention \
  tests/unit/confidence \
  tests/unit/evidence \
  tests/integration/retrieval \
  tests/integration/abstention
```

### 실제 PR #115 regression

```bash
python -m pytest -q \
  tests/integration/retrieval/test_real_review_retrieval_relevance.py \
  tests/integration/review_question/test_real_review_partial_answer.py
```

### 전체 테스트

```bash
python -m pytest -q
python -m ruff check src tests
python -m mypy src/evidence_review
python -m compileall -q src
```

### migration 검증

- fresh v4 DB 생성
- v3 → v4 migration
- migration 후 retrieval rebuild
- snapshot freshness 확인
- 기존 v3 DB를 migration 없이 열면 fail-closed

모든 검증은 Python 3.13 기준으로 수행한다.

---

# 5. 구현 의존관계

```text
Task 0   실제 실패 fixture
   ↓
Task 1   QuestionPlan v2 계약
   ↓
Task 2   DB schema v4 / clause index
   ↓
Task 3   clause retrieval + citation resolve
   ↓
Task 4   planner fact/rule 분리
   ↓
Task 5   issue별 Top-K + global budget
   ↓
Task 6   adaptive fallback
   ↓
Task 7   bounded cross-reference
   ↓
Task 8   issue coverage
   ↓
Task 9   claim/citation issue relevance
   ↓
Task 10  end-to-end lineage
   ↓
Task 11  partial answer / finalizer
   ↓
Task 12  confidence coverage
   ↓
Task 13  retrieval trace
   ↓
Task 14  실제 E2E acceptance
   ↓
Task 15  전체 검증
```

Task 1, 2, 9, 11은 contract/schema 변경 구간이므로 다른 작업과 한 커밋에 섞지 않는다.

---

# 6. 완료 기준

수정 후 PR #115의 동일 질문을 exact-head에서 재실행했을 때 다음을 모두 만족해야 한다.

- [ ] 일반 사업대상지 최소면적 1,000㎡ 근거를 검색한다.
- [ ] 사용자 fact 300m를 규정 threshold로 오인하지 않는다.
- [ ] 역세권 250m 원칙과 350m 조건부 범위를 검색한다.
- [ ] 1,500㎡와 1,000㎡ 규칙을 deterministic하게 비교할 수 있다.
- [ ] 준공업지역 공동주택 400% 기준 근거를 검색한다.
- [ ] 산업부지 확보비율 근거를 독립 issue에 연결한다.
- [ ] 임대형기숙사/기타 주택 주차기준을 해당 issue에 연결한다.
- [ ] 지구단위계획 추가 주차완화와 필요한 참조를 연결한다.
- [ ] `RETRIEVAL_MISS`와 `SOURCE_NOT_INGESTED`를 구분한다.
- [ ] reference target 부재는 `REFERENCE_TARGET_MISSING`으로 구분한다.
- [ ] 질문과 무관한 공공기여율/비주거 위치/364호 산식 claim을 최종 답변에서 제거한다.
- [ ] 모든 최종 claim은 issue lineage와 citation lineage가 교차 검증된다.
- [ ] 일부 issue만 부족하면 해결된 issue는 유지하고 부족 issue만 보류한다.
- [ ] 실제 parser-shaped fixture가 통과한다.
- [ ] Python 3.13 전체 pytest/Ruff/mypy/compileall 검증이 통과한다.
- [ ] exact-head E2E 재실행 결과를 PR에 기록한다.

---

# 7. 주요 리스크와 대응

## Recall 증가로 무관 근거 증가

대응:

- issue-scoped candidate pool
- deterministic fallback provenance
- Track A 이전 evidence eligibility
- claim/citation issue intersection hard gate

## Candidate explosion

대응:

- max issues
- max queries per issue
- per-issue role limit
- global candidate cap
- max selected evidence
- semantic clause dedupe

## Reference traversal 폭발/순환

대응:

- max depth
- max nodes per issue
- max fanout
- visited set
- cycle detection
- authoritative revision filter

## Clause와 bbox 연결 실패

대응:

- clause semantic record와 citation record 분리
- source element materialization
- 실패 시 `PARSE_GAP`
- 임의 bbox 생성 금지

## Partial answer가 과도한 확정으로 이어질 위험

대응:

- issue별 deterministic support state
- unresolved issue에 claim 생성 금지
- global hard gate는 기존 fail-closed 유지
- packet에 issue_results 직렬화

## Schema migration 위험

대응:

- v3 → v4 explicit migration
- exact schema shape 검증
- migration 없이 구버전 DB 자동 변형 금지
- index rebuild/freshness 검증

---

# 8. 현재 상태

- 상세 구현 계획: **완료**
- 코드 구현: **NOT_STARTED**
- 신규 regression fixture: **NOT_STARTED**
- 테스트: **NOT_RUN**
- 병합: **금지 — 구현 및 exact-head 검증 완료 전까지 merge하지 않음**
