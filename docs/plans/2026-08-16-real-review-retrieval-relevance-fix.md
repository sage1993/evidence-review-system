# 실제 ERS_REVIEW 검색·관련성 실패 수정 계획

## 배경

실제 안심주택 검토 질문에서 근거 문서와 파싱 데이터에 기준이 존재함에도 retrieval이 핵심 근거를 누락하고, 질문과 직접 관계없는 근거가 최종 답변에 포함되는 실패가 확인되었다.

대표 실패 질문은 다음 세 항목을 동시에 포함한다.

1. 안심주택 일반 사업대상지 최소 면적
2. 역 승강장 경계 300m, 1,500㎡ 부지의 사업대상지 적격성
3. 준공업지역에서 공공지원민간임대주택과 임대형기숙사를 복합하는 경우의 주차기준, 공동주택 용적률 400% 완화, 산업부지 확보비율, 지구단위계획 주차기준 추가 완화

## 확인된 문제

- 최소면적, 역세권 250m/350m, 준공업지역 400%, 산업부지 확보비율 등은 원문 및 파싱 산출물에 존재하지만 최종 review packet에서는 missing input으로 처리되었다.
- 현재 retrieval은 parser element 중심의 lexical FTS에 의존하고 있어 법규의 clause 단위 의미 구조를 충분히 활용하지 못한다.
- planner가 생성한 여러 issue/search request가 global Top-K에서 경쟁하여 일부 issue의 정답 근거가 탈락할 수 있다.
- 숫자 사실(예: 300m, 1,500㎡)과 법규 threshold(250m, 350m, 1,000㎡)의 역할이 분리되지 않아 규칙 검색이 취약하다.
- 법규 표현 변형(예: 용적률 ↔ 기본용적률, 완화 ↔ 400% 이하)에 대한 deterministic fallback이 부족하다.
- 법규 간 참조(예: 안심주택 조례 제13조 → 주택건설기준 규정 제27조 / 서울시 주차장 조례 별표 2)를 issue별로 추적하는 retrieval이 부족하다.
- Track A claim과 QuestionPlan issue 사이의 기계적 관련성 검증이 없어, citation은 맞지만 질문과 무관한 claim이 최종 답변에 포함될 수 있다.
- RETRIEVAL_MISS와 SOURCE_NOT_INGESTED가 동일한 missing input으로 뭉개져 원인 진단이 어렵다.

## 수정 방향

1. Clause-first retrieval
   - clause를 1차 법규 검색 단위로 사용한다.
   - element/page/bbox는 citation anchor로 유지한다.
2. Fact와 rule lookup 분리
   - 사용자 숫자 사실은 facts에 보존하되 규칙 검색어에 불필요하게 강제하지 않는다.
3. Issue-aware retrieval
   - global Top-K 전에 issue별 최소 Top-K를 보장한다.
4. Adaptive fallback
   - exact/phrase → token AND → relaxed deterministic aliases/compound handling → heading/section scope → legal reference traversal 순으로 부족한 issue만 재검색한다.
5. Evidence coverage loop
   - 각 issue의 근거 충족 여부를 확인하고 부족한 issue만 fallback/retry한다.
6. Cross-reference traversal 강화
   - 법규명·조항·별표 참조를 구조화하고 제한된 depth로 후속 근거를 탐색한다.
7. Claim relevance validation
   - Track A claim에 issue_ids를 필수화하고 evidence retrieval lineage와 교차 검증한다.
   - issue와 연결되지 않는 claim은 UNRELATED_CLAIM으로 거부한다.
8. Source coverage 상태 분리
   - RETRIEVAL_MISS, SOURCE_NOT_INGESTED, REFERENCE_TARGET_MISSING, PARSE_GAP, AMBIGUOUS_RULE, CONFLICTING_RULES를 구분한다.
9. Partial answer 정책
   - 일부 issue만 미해결이면 해결된 issue까지 전체 ABSTAIN하지 않는다.
10. 실제 parser output 기반 회귀 테스트
   - synthetic evidence만으로 검증하지 않고 실제 source_elements/clauses 구조를 fixture로 고정한다.

## 완료 기준

수정 후 동일한 실패 질문을 재실행했을 때 다음을 만족해야 한다.

- 일반 사업대상지 최소면적 1,000㎡ 근거를 검색한다.
- 300m 부지는 250m 일반 기준 밖이지만 350m 예외 심의 가능 범위임을 근거와 함께 구분한다.
- 1,500㎡가 일반 최소면적 1,000㎡를 충족함을 판정한다.
- 준공업지역 공동주택 용적률 400% 완화 근거를 검색한다.
- 산업부지 확보비율 관련 통합심의/운영기준 근거를 검색한다.
- 공공지원민간임대주택과 임대형기숙사의 주차기준을 용도별로 각각 적용하는 근거를 검색한다.
- 지구단위계획에 따른 추가 주차기준 완화 근거를 검색한다.
- 참조 법규 세부 산정 기준이 snapshot에 없을 경우 해당 issue만 SOURCE_NOT_INGESTED 또는 REFERENCE_TARGET_MISSING으로 표시한다.
- 질문과 무관한 공공기여율, 비주거 위치, 364호 산식 등의 claim은 최종 답변에서 제외한다.

## 예상 리스크

- relaxed retrieval로 recall을 높이면 무관한 근거가 증가할 수 있다.
- clause가 길 경우 검색 단위가 지나치게 커질 수 있다.
- cross-reference traversal이 후보 폭발을 일으킬 수 있다.
- 동일 법규의 여러 revision이 동시에 존재하면 적용 시점 충돌이 발생할 수 있다.
- 표 기반 기준은 행/열 의미 보존 없이는 여전히 오판 가능성이 있다.
- issue별 retrieval/fallback으로 latency가 증가할 수 있다.
- partial answer 허용 시 근거 부족 issue를 과도하게 확정하는 위험이 있다.

따라서 모든 확장은 deterministic bound, revision filtering, issue coverage, citation/lineage validation, fail-closed 정책 안에서 구현한다.
