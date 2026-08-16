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

## 2. 핵심 설계 결정

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
| partial answer | global hard gate와 issue-scoped insufficiency 분리 |

## 3. 초기 retrieval budget

```text
max_issues = 8
max_queries_per_issue = 4
per_issue_role_limit = 5
global_candidate_cap = 80
max_selected_evidence = 40
reference_max_depth = 2
reference_max_nodes_per_issue = 12
reference_max_fanout = 6
```

## 4. 구현 Task

### Task 0 — 실제 실패 fixture 고정
- parser-shaped fixture로 7개 독립 issue를 고정한다.
- global Top-K 구조의 카디널리티 실패를 재현한다.

### Task 1 — QuestionPlan v2
- `EvidenceRole = supporting_fact | rule`
- `QuestionIssue.required_evidence_roles`
- `SearchRequest.role`
- v1은 보수적으로 `rule`로 deterministic adapter한다.

### Task 2 — clause semantic index / schema v4
- clause retrieval 전용 영속 인덱스를 추가한다.
- bbox-required citation record와 semantic clause record를 분리한다.

### Task 3 — clause retrieval + citation resolve
- clause로 relevance를 결정한다.
- source element/page/bbox로 citation을 materialize한다.

### Task 4 — fact/rule lookup 분리
- `300m`, `1,500㎡` 같은 사용자 입력은 사실로 보존한다.
- rule query는 규정의 기준명/threshold를 검색한다.

### Task 5 — issue-aware retrieval coordinator
- issue별 후보를 먼저 확보한다.
- semantic clause 기준 dedupe 후 global budget을 적용한다.

### Task 6 — deterministic adaptive fallback

```text
EXACT_CLAUSE
→ PHRASE
→ TOKEN_AND
→ TOKEN_PREFIX
→ APPROVED_ALIAS
→ LEGAL_COMPOUND_DECOMPOSITION
→ HEADING_SCOPED
```

REFERENCE_EXPANSION은 Task 7에서 별도 연결한다.

### Task 7 — bounded legal cross-reference traversal
- 기존 `visited`/depth BFS 유지
- `max_nodes`, `max_fanout` 추가
- reference path provenance 보존
- missing target 기록
- 동일 문서 stale revision 차단
- cross-document reference 허용

### Task 8 — issue coverage state machine / gap diagnosis

```text
IssueStatus = RESOLVED | CONDITIONAL | CONFLICT | SOURCE_MISSING | UNRESOLVED
GapCode = RETRIEVAL_MISS | SOURCE_NOT_INGESTED | REFERENCE_TARGET_MISSING | PARSE_GAP | AMBIGUOUS_RULE | CONFLICTING_RULES
```

retrieval → fallback → reference traversal 이후 issue별 필요한 evidence role 충족 여부를 결정론적으로 판정한다.

### Task 9 — Track A claim/citation issue relevance hard gate
- `Claim.issue_ids` 필수
- `EvidenceExcerpt.issue_ids`, `role` 유지
- `claim.issue_ids ∩ evidence.issue_ids != ∅` 강제
- `UNRELATED_CLAIM`, `CROSS_ISSUE_CITATION`, `UNKNOWN_CLAIM_ISSUE` reject

### Task 10 — end-to-end issue lineage 보존

```text
QuestionPlan issue
→ SearchRequest
→ RetrievalMatch
→ selected evidence
→ TrackABundle
→ Claim
→ Citation
```

모든 단계의 issue lineage를 추적 가능하게 유지한다.

### Task 11 — partial answer / finalizer 재설계
- global hard gate는 전체 ABSTAIN 유지
- issue-scoped insufficiency는 해당 issue만 unresolved
- `resolved_issue_count == 0`이면 ABSTAIN
- 일부 resolved가 있으면 `READY_FOR_HUMAN_REVIEW + issue_results`
- 새 `PARTIAL` global status는 도입하지 않는다.

### Task 12 — confidence를 issue coverage 기반으로 보강
- unresolved issue를 global confidence가 덮지 못하게 한다.
- 기존 weight는 근거 없이 변경하지 않는다.

### Task 13 — retrieval trace
- issue_id, role, search_request_id, fallback stage, rank/score, kept/dropped, reference path, selected evidence, coverage status, citation_ids 기록

### Task 14 — 실제 실패 E2E acceptance
- 1,000㎡ 최소면적
- 250m/350m 역세권 기준
- 1,500㎡ deterministic comparison
- 준공업지역 400%
- 산업부지 확보비율
- 주택유형별 주차기준
- 지구단위계획 추가 주차완화
- unrelated evidence 제거
- issue-scoped partial answer
- parser-shaped fixture에서 retrieval → Track A → Track B → finalizer까지 검증

### Task 15 — 전체 검증

```bash
python -m pytest -q
python -m ruff check src tests
python -m mypy src/evidence_review
python -m compileall -q src
```

추가:
- schema v3 → v4 migration
- retrieval rebuild/freshness
- exact-head E2E
- Python 3.13 wheel/runtime smoke

## 5. 구현 진행 현황

- [x] Task 0 — 실제 parser-shaped regression fixture
- [x] Task 1 — QuestionPlan v2
- [x] Task 2 — schema v4 + clause semantic index
- [x] Task 3 — clause retrieval + citation resolver
- [x] Task 4 — fact/rule lookup 분리
- [x] Task 5 — issue-aware fair retrieval budgets
- [x] Task 6 — deterministic adaptive fallback
- [x] Task 7 — bounded legal cross-reference traversal
- [x] Task 8 — issue coverage state machine / gap diagnosis
- [x] Task 9 — Track A claim/citation issue relevance hard gate
- [x] Task 10 — end-to-end issue lineage 보존
- [x] Task 11 — partial answer / finalizer gate 재설계
- [x] Task 12 — confidence coverage 보강
- [x] Task 13 — retrieval trace
- [x] Task 14 — 실제 실패 E2E acceptance 구현
- [ ] Task 15 — 현재 HEAD 전체 재검증

현재 진행: **Task 15 — merge-preflight 수정 후 exact-head 재검증**

## 6. Merge-preflight 후속 수정

PR 전체 diff 리뷰에서 발견된 다음 병합 차단 항목을 수정했다.

- [x] planned review의 자유형 `user_expansions`가 legacy global retrieval로 우회하지 않도록 fail-closed 처리. 사용자 확장은 QuestionPlan `search_requests`에서 issue/role binding을 가진 경우에만 계획 검색으로 표현한다.
- [x] `I1`~`I8` 하드코딩 issue whitelist 제거. Track A claim issue는 실제 `inputs.question_plan.issues`를 권위 목록으로 검증한다.
- [x] partial issue coverage가 deterministic `RuleResult.missing_inputs`의 전역 `MISSING_REQUIRED_INPUT` hard gate를 약화하지 않도록 분리한다.
- [x] 실제 parser-shaped 회귀 fixture에서 retrieval → Track A validation → Track B audit → finalizer까지 통과하는 full-pipeline acceptance test를 추가한다.
- [x] partial fixture에서 해결된 issue의 claim을 유지하고 unresolved issue claim을 생성하지 않는 finalizer E2E를 추가한다.
- [x] `1,500㎡ >= 1,000㎡`, `300m > 250m`, `300m <= 350m` 비교를 production deterministic rule operator로 검증하는 acceptance assertion을 추가한다.
- [ ] 위 후속 수정이 포함된 최종 HEAD에서 full pytest/Ruff/mypy/compileall/documentation/migration/exact-head E2E를 다시 실행한다.

이전 exact-head 검증 `d614706788024374783249d4ae9cbe75f6b8df4f`의 `1539 passed, 7 skipped` 결과는 merge-preflight 수정 이전 증거이며 현재 HEAD 검증으로 재사용하지 않는다.

## 7. 검증 정책

- 테스트 코드를 production 변경보다 먼저 추가한다.
- 가능한 경우 GitHub Actions 결과를 확인한다.
- Actions가 없으면 실행하지 않은 항목을 PASS로 표시하지 않는다.
- full pytest/Ruff/mypy/compileall 및 exact-head acceptance는 Task 15의 별도 완료 조건으로 유지한다.
- 최종 HEAD가 변경되면 이전 HEAD의 검증 결과를 최종 검증으로 재사용하지 않는다.
