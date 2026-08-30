---
name: ers-review
description: Use when a user invokes $ERS_REVIEW or asks Codex Desktop to answer a question through the Evidence Review System formal-review workflow, including questions that use case-specific drawings or supporting images.
---

# ERS Review

## 목적

`$ERS_REVIEW <질문>`은 **모든 질문을 정식 검토(formal review)** 로 처리한다. 빠른 조회 모드는 없다. 사용자는 QuestionPlan, query JSON, review-run request, Track A/B 중간 JSON을 직접 작성하지 않는다.

프로젝트 Python runtime은 모델을 호출하지 않는다. Codex가 외부 AI 역할로 **QuestionPlan → 필요한 경우 Visual Analysis → Track A → Track B** handoff를 작성하고, runtime은 각 결과를 검증·고정한다. Question Planner와 Visual Analysis는 결론을 만들지 않는다.

## 입력 역할을 먼저 구분한다

파일 확장자로 역할을 결정하지 않는다. 특히 **PDF라는 이유만으로 `$ERS_PDF`를 호출하지 않는다.** 사용 목적을 기준으로 다음 세 역할을 구분한다.

| 사용 목적 | Attachment role | 처리 경로 |
|---|---|---|
| 법령·조례·지침·보고서 등 검색 가능한 근거 corpus | `REFERENCE_DOCUMENT` | `$ERS_PDF` → evidence DB |
| 사용자가 그 도면 자체를 보고 판단해 달라고 제공한 PDF/이미지 | `CASE_DRAWING` | drawing intake → visual analysis |
| 사진·캡처·보조 이미지처럼 질문의 사실관계를 시각적으로 확인하기 위한 자료 | `SUPPORTING_IMAGE` | drawing intake → visual analysis |

예를 들어 `이 PDF 도면을 보고 출입구 위치가 적절한지 검토해`는 `CASE_DRAWING`이다. 이 파일을 OpenDataLoader reference parser에 넣어 검색 corpus로 만드는 것은 금지한다.

반대로 `이 법령 PDF를 근거자료로 등록하고 질문에 답해`는 `REFERENCE_DOCUMENT`이며 `$ERS_PDF` 선행 대상이다.

## 사전 조건

1. 법령·기준 등 **normative/reference evidence가 필요한 질문**은 `$ERS_PDF`로 준비되고 active workspace로 bind된 corpus를 사용한다.
2. active workspace의 `<workspace>/evidence/evidence.sqlite`와 인용 가능한 revision page-image cache가 준비되어 있어야 한다.
3. `CASE_DRAWING` / `SUPPORTING_IMAGE`가 있는 질문은 해당 원본을 immutable drawing intake로 보존하고 source hash를 고정해야 한다. CASE visual 자료 자체에 `$ERS_PDF` 완료를 요구하지 않는다.
4. 계산이 필요한 질문은 승인된 `CalculationResult`, 규칙이 필요한 질문은 승인된 `RuleResult`를 사용한다. prose나 visual observation에서 새 계산값·규칙 결과를 만들지 않는다.
5. 필요한 권위 근거가 없거나 시각자료 분석이 완료되지 않은 경우 해당 blocking state를 그대로 보존한다.

## 권위 분리

정식 검토에는 서로 다른 권위 트랙이 있다.

```text
REFERENCE_DOCUMENT → retrieval citation → normative authority
CASE_DRAWING / SUPPORTING_IMAGE → DrawingCandidate → case-specific fact evidence
CalculationResult / RuleResult → deterministic engine authority
```

`DrawingCandidate`는 법령 근거를 대신하지 않는다. 질문 본문에 사용자가 적은 사실도 visual observation으로 자동 승격하지 않는다. 실제 source/page/geometry에 바인딩되어 runtime 검증을 통과한 visual output만 drawing evidence가 된다.

## 0. Active workspace 재검증

`$ERS_REVIEW` 시작 시 filesystem에서 workspace 후보를 추측하지 않는다. 먼저 `$ERS_PDF`가 저장한 repository-local binding을 runtime으로 재검증한다.

```powershell
evidence-review workspace active `
  --repository-root .
```

정상 상태는 `ACTIVE`다. stdout의 `workspace`, `evidence_snapshot_hash`, `evidence_db_sha256`을 이번 review의 고정 입력으로 사용하고 이후 모든 `--workspace`에는 반환된 **동일한 workspace path**만 전달한다.

`ACTIVE_WORKSPACE_NOT_BOUND`이면 임의의 workspace를 선택하지 말고 `$ERS_PDF` 준비·bind를 먼저 완료한다. `ACTIVE_WORKSPACE_STALE`이면 bind 시점 이후 evidence snapshot 또는 workspace identity가 바뀐 것이므로 review를 시작하지 말고 해당 workspace를 다시 검증·bind한다.

저장소나 상위 디렉터리에서 `evidence.sqlite`를 재귀 검색하지 않는다. 수정시간이 가장 최신인 workspace, 첫 번째 검색 결과, 최근 run 경로를 active workspace 대신 선택하지 않는다.

## 1. Question Planner handoff

모든 자연어 질문은 retrieval 전에 Question Planner를 거친다.

```powershell
evidence-review review-question prepare-plan `
  --workspace <workspace> `
  --question "<질문>"
```

정상 상태는 `WAITING_QUESTION_PLAN`이다. Codex는 `question-planner-bundle.json`과 `QUESTION_PLANNER_INSTRUCTIONS.md`를 읽은 뒤 `question-plan-output.json`을 작성한다.

QuestionPlan 원칙:

- 원래 질문과 사용자가 명시한 사실·가정·숫자·부정 조건·예외·고유명사·인용 조문을 보존한다.
- 독립 근거가 필요한 경우에만 issue를 분리한다.
- 최소한의 bounded search request만 만든다.
- 사용자 명시 법령·조문은 `source=user`, planner 추정은 `source=planner`로 구분한다.
- answer/conclusion/decision/confidence/rule status를 만들지 않는다.
- SIMPLE/COMPOUND/COMPLEX 같은 별도 질문 등급을 만들지 않는다.
- CASE visual 자료에 적힌 것으로 추정되는 내용을 Planner가 사실로 새로 만들지 않는다.

Planner가 만든 법령명·조문·검색어는 검색 가설일 뿐 authority가 아니다.

## 2. QuestionPlan 검증 후 retrieval 및 Run 준비

```powershell
evidence-review review-question prepare `
  --workspace <workspace> `
  --question "<질문>" `
  --question-plan-output <question-plan-output.json>
```

사용자가 직접 제공한 CASE visual 자료가 있으면 역할에 따라 다음 옵션을 사용한다.

```text
--case-drawing <path>
--supporting-image <path>
```

필요한 경우에만 다음 옵션을 추가한다.

```text
--expansion <explicit-user-search-term>
--calculation-result <path>
--rule-result <path>
--approved-rule-result-id <id>
```

`--case-drawing` 또는 `--supporting-image`에 지정된 PDF는 **reference source-batch ingest 대상이 아니다.** runtime은 원본을 drawing source로 immutable ingest하고 그 source identity를 review request에 바인딩한다.

QuestionPlan 검증 실패는 `PLANNER_FAILED`이며 retrieval 실패나 `ABSTAIN`으로 바꾸지 않는다. 검색 결과 0건은 `RETRIEVAL_NO_EVIDENCE`로 보존한다.

## 3. Visual Analysis handoff

CASE visual attachment가 있으면 Track A보다 먼저 visual-analysis handoff를 완료한다.

Visual Analysis는 다음만 수행한다.

- 실제 지정된 source/page를 본다.
- 질문과 QuestionPlan issue에 필요한 시각적 사실을 관찰한다.
- 관찰 위치를 `POINT`, `BBOX`, `LINESTRING`, `POLYGON`으로 기록한다.
- source SHA-256, page, coordinate system을 보존한다.

Visual Analysis가 해서는 안 되는 일:

- 법규 적합/부적합 결론 생성
- RuleResult 또는 CalculationResult 생성
- 질문 문장에 적힌 사실을 이미지에서 확인한 것처럼 복제
- 보이지 않는 치수·용도·경계·설비를 추정
- 존재하지 않는 page나 임의 bbox 생성

runtime 검증을 통과한 output만 `DrawingCandidate`가 된다. 미완료 상태는 `VISUAL_ANALYSIS_REQUIRED`, source/page 준비 실패는 정확한 visual reason code로 유지한다.

## 4. Track A 작성과 즉시 검증

Codex는 `track-a-bundle.json`과 `TRACK_A_INSTRUCTIONS.md`만 사용한다. Track A는 제공된 normative evidence, validated drawing candidates, 계산·규칙 결과를 설명할 수 있으나 새 authority를 만들 수 없다.

`inputs.question_plan`의 issue/fact/assumption/dependency를 유지한다. `inputs.retrieval_lineage`는 normative evidence lineage이고, `inputs.case_visual_context`는 case-specific visual lineage다. 둘을 서로 대체하지 않는다.

작성 직후 반드시 검증한다.

```powershell
evidence-review review-question submit-track-a `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-a-output <track-a-output.json>
```

Track A 검증 전에는 Track B를 작성하지 않는다.

## 5. Track B 독립 감사

Track B는 검증된 Track A의 모든 claim을 독립 감사한다.

```powershell
evidence-review review-question submit-track-b `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-b-output <track-b-output.json> `
  --publish
```

Track B 통과 후 finalizer가 `final-review-packet.json`과 `review.html`을 만든다. `READY_FOR_HUMAN_REVIEW`는 자동 승인 상태가 아니다. `ABSTAIN`은 기록된 사유를 유지한다.

## 5.1 Attempt ownership and retry boundary

External Track outputs use numbered attempt files: `track-a-attempt-<N>.json` and `track-b-attempt-<N>.json`. The first handoff expects attempt 1. After successful validation, the runtime owns and creates the canonical `track-a-output.json` or `track-b-output.json`; external files remain preserved as submitted.

After Track A validation, the run is `WAITING_TRACK_B` and Track A must not be resubmitted. If finalization enters `FINALIZING` and the finalizer fails, recovery reuses only the runtime-owned canonical `track-b-output.json`. A hash-mismatched retry remains `TRACK_B_RETRY_MISMATCH`; an external Track B attempt after a valid canonical exists is `TRACK_B_REGENERATION_FORBIDDEN`. **do not regenerate** an external Track B attempt.

## 6. Review Workspace와 사람 결정

시각자료가 있는 경우 Review Workspace는 실제 source page/image와 validated geometry overlay를 함께 보여준다. 법규 citation viewer와 case drawing viewer는 구분하되 같은 claim/finding에서 연결할 수 있다. 시각자료가 없는 질문에서는 drawing viewer를 만들지 않는다.

보호 브라우저:

```powershell
evidence-review review-run serve `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --reviewer-id <REVIEWER-ID> `
  --detach `
  --idle-timeout-seconds 5
```

사용자 결정은 다음 네 가지다.

| 값 | 화면 표시 |
|---|---|
| `SATISFIED` | 내용 확인 완료 |
| `NOT_SATISFIED` | 내용에 오류 있음 |
| `CONDITIONAL` | 조건부 확인 |
| `ADDITIONAL_REVIEW_REQUIRED` | 추가 자료 필요 |

결정은 append-only human-decision record로 저장하고 machine packet의 `human_decision`은 수정하지 않는다. 유효한 결정이 존재하면 화면 상태만 `REVIEW_COMPLETED`로 투영할 수 있다.

보관용 `file:` HTML은 서버에 직접 저장할 수 없다. **결정 JSON 다운로드**는 유효한 envelope를 만들며 HTML 파일 저장과는 별개다. 다운로드한 envelope는 다음 승인 경로로 반영한다.

```powershell
evidence-review review-run import-decision `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --envelope <human-decision-envelope.json>
```

현재 packet SHA-256과 envelope hash가 다르면 import를 거부한다. 기존 decision record를 덮어쓰지 않는다.

## 화면 계약

기본 화면 우선순위:

1. 검토 결과와 1문장 결론
2. CASE visual 자료가 있으면 실제 도면/이미지와 문제 위치 overlay
3. normative 원문 근거와 page/bbox
4. 실제 항목이 있을 때만 추가 확인
5. 검토자 결정

run ID, citation/evidence/revision ID, hash, confidence factor/weight는 기본 화면에서 제거하고 접힌 감사 정보에 보존한다.

## 중단 조건

| 조건 | 처리 |
|---|---|
| `ACTIVE_WORKSPACE_NOT_BOUND` | filesystem 추측 금지, `$ERS_PDF` 준비·bind 요구 |
| `ACTIVE_WORKSPACE_STALE` | review 시작 금지, workspace 재검증·재bind 요구 |
| normative evidence가 필요한데 `evidence.sqlite` 없음 | REFERENCE corpus 준비 요구 |
| REFERENCE parser/source 상태가 `PENDING_*`, `BLOCKED`, `FAILED` | reference blocking reason 보존 |
| CASE visual source 준비 실패 | visual source reason만 기록; reference parser 오류로 변환 금지 |
| CASE visual analysis 미완료 | `VISUAL_ANALYSIS_REQUIRED` |
| Planner 출력 누락/검증 실패 | `WAITING_QUESTION_PLAN` / `PLANNER_FAILED` |
| 유효 Plan 검색 결과 0건 | `RETRIEVAL_NO_EVIDENCE` |
| 필요한 승인 계산/규칙 없음 | 추정 금지, missing input 또는 `ABSTAIN` |
| Track A 검증 실패 | Track B 시작 금지 |
| Track B 검증 실패 | finalization 금지 |
| packet/HTML 누락 | 브라우저 완료 주장 금지 |
| packet hash mismatch | 결정 저장/import 거부 |

## 금지

- active binding 없이 저장소에서 `evidence.sqlite`를 검색해 workspace 추측
- PDF 확장자만 보고 `$ERS_PDF`를 호출
- `CASE_DRAWING`을 `REFERENCE_DOCUMENT`로 바꿔 parser에 전달
- CASE_DRAWING PDF에 OpenDataLoader/reference parser 성공을 visual review 선행조건으로 요구
- Question Planner를 건너뛰고 자연어 질문 전체를 retrieval에 전달
- Planner/Visual Analysis 단계에서 답변·법규 결론·confidence·rule status 생성
- 사용자에게 중간 JSON 수작업 요구
- 모델이 계산 결과·규칙 결과·citation을 새로 생성
- 미확인 drawing candidate를 Math/Rule input으로 사용
- `READY_FOR_HUMAN_REVIEW`를 사람 승인으로 표현
- machine packet의 `human_decision` 수정
