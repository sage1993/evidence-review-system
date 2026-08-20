---
name: ers-review
description: Use when a user invokes $ERS_REVIEW or asks Codex Desktop to answer a question from a parsed Evidence Review System workspace.
---

# ERS Review

## 목적

`$ERS_REVIEW <질문>`은 파싱된 ERS workspace에서 **모든 질문을 정식 검토(formal review)** 로 처리한다. 빠른 조회 모드는 없다. 사용자는 QuestionPlan, query JSON, review-run request, Track A/B 중간 JSON을 직접 작성하지 않는다.

프로젝트 Python runtime은 모델을 호출하지 않는다. Codex가 외부 AI 역할로 **QuestionPlan → Track A → Track B** handoff를 각각 작성하고, 프로젝트 runtime은 각 결과를 검증·고정한다. Question Planner는 무엇을 검토·검색할지만 구조화하며 답변이나 법적·기술적 결론을 만들지 않는다.

## 사전 조건

1. `$ERS_PDF`로 준비되고 active workspace로 bind된 workspace를 사용한다.
2. `<workspace>/evidence/evidence.sqlite`가 있어야 한다.
3. 인용 가능한 revision의 page image cache가 `<workspace>/page-images/<REVISION-ID>/`에 준비되어 있어야 한다.
4. 계산이 필요한 질문은 승인된 `CalculationResult`, 규칙이 필요한 질문은 승인된 `RuleResult`를 먼저 확보한다. prose에서 새 계산값이나 규칙 결과를 만들지 않는다.

사전 조건이 충족되지 않으면 질문에 답하지 말고 정확한 blocking state를 보고한다.

## 권위 흐름

### 0. Active workspace 재검증

`$ERS_REVIEW`를 시작할 때 filesystem에서 workspace 후보를 추측하지 않는다. 먼저 `$ERS_PDF`가 저장한 repository-local binding을 runtime으로 재검증한다.

```powershell
evidence-review workspace active `
  --repository-root .
```

정상 상태는 `ACTIVE`다. stdout의 `workspace`, `evidence_snapshot_hash`, `evidence_db_sha256`을 이번 review의 고정 입력으로 사용하고, 이후 모든 `--workspace`에는 반환된 **동일한 workspace path**만 전달한다.

`ACTIVE_WORKSPACE_NOT_BOUND`이면 임의의 workspace를 선택하지 말고 `$ERS_PDF`를 먼저 완료하도록 보고한다. `ACTIVE_WORKSPACE_STALE`이면 bind 시점 이후 evidence snapshot 또는 workspace identity가 바뀐 것이므로 review를 시작하지 말고 해당 workspace를 다시 검증·bind한다.

저장소나 상위 디렉터리에서 `evidence.sqlite`를 재귀 검색하지 않는다. 수정시간이 가장 최신인 workspace, 첫 번째 검색 결과, 최근 run 경로를 active workspace 대신 선택하지 않는다. 사용자가 별도 workspace를 명시적으로 지정하더라도 그 경로를 먼저 `$ERS_PDF` 준비·검증 경계로 통과시키고 active binding을 갱신한 뒤 review를 시작한다.

### 1. Question Planner handoff 준비

모든 자연어 질문은 retrieval 전에 Question Planner 단계를 거친다. 먼저 runtime이 evidence-free planner handoff를 만든다.

```powershell
evidence-review review-question prepare-plan `
  --workspace <workspace> `
  --question "<질문>"
```

정상 상태는 `WAITING_QUESTION_PLAN`이다. stdout에는 질문 본문을 다시 노출하지 않고 다음 경로를 제공한다.

```text
question-planner-bundle.json
QUESTION_PLANNER_INSTRUCTIONS.md
question-plan-output.json
```

Codex는 **반드시** `question-planner-bundle.json`과 `QUESTION_PLANNER_INSTRUCTIONS.md`를 읽은 뒤 `question-plan-output.json`을 작성한다. 이 단계에서는 evidence DB나 검색 결과를 읽어 답을 미리 만들지 않는다.

QuestionPlan 작성 원칙:

- 원래 질문을 그대로 보존한다.
- 사용자가 명시한 사실, 가정, 숫자, 부정 조건, 예외, 고유명사, 인용 조문을 누락하지 않는다.
- 독립적인 근거가 필요한 경우에만 issue를 분리한다.
- 필요한 최소한의 bounded search request만 만든다.
- 질문에 실제 포함된 법령·조문은 `source=user`, 추정한 법령·조문은 `source=planner`로 구분한다.
- `answer`, `conclusion`, `decision`, 적합/부적합 판정, confidence, rule status를 만들지 않는다.
- 별도의 SIMPLE/COMPOUND/COMPLEX 분류를 만들지 않는다.

Planner가 추정한 법령명·조문·검색어는 **검색 가설**일 뿐 근거가 아니다. 실제 authority는 이후 evidence store에서 검색·인용된 자료만 가진다.

### 2. QuestionPlan 검증 후 retrieval 및 Run 준비

Codex가 작성한 Plan을 runtime에 제출한다.

```powershell
evidence-review review-question prepare `
  --workspace <workspace> `
  --question "<질문>" `
  --question-plan-output <question-plan-output.json>
```

사용자가 **직접 명시한** 검색 확장어가 있는 경우에만 `--expansion`을 추가할 수 있다. Planner가 만든 search request를 다시 `--expansion`으로 중복 전달하지 않는다. 계산·규칙 결과가 필요한 경우에만 다음 옵션을 추가한다.

```text
--expansion <explicit-user-search-term>
--calculation-result <path>
--rule-result <path>
--approved-rule-result-id <id>
```

runtime은 retrieval 전에 QuestionPlan을 fail-closed 검증한다. Plan이 잘못되면 `PLANNER_FAILED`로 종료하며 이를 `RETRIEVAL_NO_EVIDENCE`나 `ABSTAIN`으로 표현하지 않는다. Plan을 수정한 뒤 같은 단계부터 다시 실행한다.

검증된 Plan은 `origin=llm` 검색 요청으로 변환되고, 사용자가 직접 준 동일 검색어가 있으면 user origin이 우선하되 Planner의 `issue → search_request` lineage는 보존한다.

준비 단계가 만드는 다음 파일은 runtime 산출물이다.

```text
question-plan.json
evidence-query.json
review-request.json
track-a-bundle.json
next-action-track-a.json
```

`question_plan_sha256`과 canonical plan projection은 immutable review request에 포함된다. 동일한 **validated QuestionPlan + evidence snapshot + deterministic inputs**를 다시 실행하면 같은 deterministic 준비 결과를 재현한다. 외부 AI가 같은 질문에서 항상 같은 Plan을 만들 것이라고 가정하지 않는다.

검색 결과가 0건이면 `RETRIEVAL_NO_EVIDENCE`와 `retrieval-guidance.json`을 확인한다. 임의의 광범위 검색어를 추가해 우회하지 않는다. 이미 준비된 formal review next-action이 있으면 근거 없음 상태를 그대로 유지한 채 Track A/B 및 finalizer 경계를 따라 최종 `ABSTAIN` 여부를 검증한다.

### 3. Track A 작성과 즉시 검증

Codex는 `track-a-bundle.json`과 `TRACK_A_INSTRUCTIONS.md`만 사용해 Track A를 작성한다. Track A는 제공된 근거·계산·규칙을 설명할 수 있으나 새로운 근거, 계산, 규칙 상태, 사람 판정을 만들 수 없다.

`inputs.question_plan`이 있으면 검증된 issue/fact/assumption/dependency 구조를 유지한다. `inputs.retrieval_lineage`는 어떤 search request가 어떤 evidence로 이어졌는지 설명하는 추적 정보일 뿐 evidence 권위를 높이지 않는다. Planner의 `source=planner` legal anchor를 근거처럼 인용하지 않는다.

각 외부 생성 시도는 run 디렉터리의 canonical 파일이 아닌 attempt 전용 경로에 작성한다.

```text
track-a-attempt-<N>.json
```

모델이나 orchestration은 canonical `track-a-output.json`을 직접 생성·덮어쓰기하지 않는다. attempt 파일을 `submit-track-a`에 전달하고, 검증에 성공한 결과만 runtime이 canonical output으로 고정한다.

작성 직후 Track B를 시작하기 전에 반드시 검증한다.

```powershell
evidence-review review-question submit-track-a `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-a-output <track-a-attempt-N.json>
```

검증 실패 시 **새 attempt 경로**에서 같은 단계를 수정한다. 검증 실패한 attempt를 canonical 파일로 재사용하지 않는다. `FILEEXISTSERROR`는 정상적인 모델 retry 신호가 아니며, canonical output 소유권을 침범했거나 이미 다음 상태로 진행한 orchestration 오류로 처리한다.

`submit-track-a`가 성공해 workflow가 `WAITING_TRACK_B`로 전환되면 해당 stage는 완료된 것이다. **Track A 외부 호출을 다시 수행하지 않는다.** 이후 오류는 Track B 또는 finalization 단계에서 복구하며 Track A를 다시 생성하지 않는다.

### 4. Track B 독립 감사

Track B는 검증된 Track A의 **모든 claim을 한 번씩** 독립 감사한다. Track A를 재작성하거나 사람 판정을 만들지 않는다.

Track B도 external attempt 전용 경로를 사용한다.

```text
track-b-attempt-<N>.json
```

모델이나 orchestration은 canonical `track-b-output.json`을 직접 생성·덮어쓰기하지 않는다. attempt 파일을 runtime에 제출하고 검증된 결과만 canonical output으로 고정한다.

```powershell
evidence-review review-question submit-track-b `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-b-output <track-b-attempt-N.json> `
  --publish
```

Track B 외부 생성 루프의 종료 조건은 `submit-track-b` 검증 결과다.

- Track B를 생성하기 전 현재 workflow가 `WAITING_TRACK_B`인지 확인한다. 이미 `FINALIZING`, `READY_FOR_HUMAN_REVIEW`, `ABSTAIN`이거나 canonical `track-b-output.json`/final packet이 존재하면 외부 Track B를 생성하지 않는다.
- **`submit-track-b` 성공 응답을 받은 즉시 Track B 외부 생성 루프를 종료한다.** 성공한 attempt 번호를 증가시키거나 새 `track-b-attempt-<N+1>.json`을 만들지 않는다.
- `track-b-attempt-<N+1>.json`은 **직전 `submit-track-b`가 검증 실패를 반환한 경우에만** 허용한다. FILEEXISTS, publication, finalizer, server, browser 오류는 Track B validation failure로 재분류하지 않는다.
- packet/HTML 생성 후 보호 브라우저 handoff 실패는 Track B 재생성 사유가 아니다. 동일 run의 기존 packet을 사용해 `review-run serve` 단계만 복구한다.

Track B 검증을 통과해 finalization이 시작되거나 최종 packet이 생성되면 **Track B 외부 호출을 다시 수행하지 않는다.** `READY_FOR_HUMAN_REVIEW` 또는 `ABSTAIN`이 반환된 뒤에는 같은 run에 대해 모델을 다시 호출하지 않고 기존 immutable artifact를 사용한다.

Track B 검증을 통과하면 기존 finalizer가 `final-review-packet.json`과 `review.html`을 만든다. `READY_FOR_HUMAN_REVIEW`는 자동 승인 상태가 아니다. `ABSTAIN`은 기록된 사유를 유지한다.

### 5. 보호 브라우저 열기

가능하면 reviewer identity를 시작 시 고정한다.

```powershell
evidence-review review-run serve `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --reviewer-id <REVIEWER-ID> `
  --detach `
  --idle-timeout-seconds 5
```

Detached protected review servers default to a 1800-second monotonic idle timeout. Use a finite positive override only for an explicit acceptance window; valid protected requests refresh activity and rejected requests do not.

보호 URL은 `127.0.0.1`의 run-scoped token 경로다. packet/HTML 생성 이후 브라우저 handoff가 실패하면 완료로 보고하지 않는다. 이 경우 Track A/B를 다시 생성하지 않고 기존 final packet에서 browser/server handoff만 재시도한다.

`--reviewer-id`를 생략한 경우 결정 저장 또는 보관 envelope 생성 시 reviewer ID를 한 번 확인한다.

### 6. 사람 결정

기본 화면에서 사용자가 입력하는 것은 다음 둘뿐이다.

- 결정
- 검토 의견

결정 값은 다음 네 가지다.

| 값 | 화면 표시 |
|---|---|
| `SATISFIED` | 내용 확인 완료 |
| `NOT_SATISFIED` | 내용에 오류 있음 |
| `CONDITIONAL` | 조건부 확인 |
| `ADDITIONAL_REVIEW_REQUIRED` | 추가 자료 필요 |

보호 서버는 reviewer ID와 현재 packet hash를 결합하고, `reviewed_at`을 timezone이 포함된 ISO-8601 시각으로 서버에서 생성한다. 결정은 `human-decisions/` 아래 append-only JSON으로 저장되며 machine packet과 `review.html`은 변경하지 않는다. 유효한 결정이 존재하면 화면 상태만 `REVIEW_COMPLETED`로 투영할 수 있다.

보관용 `file:` HTML은 서버에 직접 저장할 수 없다. **결정 JSON 다운로드**는 유효한 5필드 envelope를 만들며, HTML 파일 저장과는 별개다. 다운로드한 envelope는 다음 승인 경로로 반영한다.

```powershell
evidence-review review-run import-decision `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --envelope <human-decision-envelope.json>
```

현재 packet SHA-256과 envelope hash가 다르면 import를 거부한다. 기존 decision record를 덮어쓰지 않는다.

## 화면 계약

기본 Review Workspace는 비개발자 기준으로 다음 순서만 우선 표시한다.

1. 검토 결과와 1문장 결론
2. 원문 근거와 page/bbox
3. 실제 항목이 있을 때만 추가 확인
4. 검토자 결정

단일 claim이면 항목 네비게이터를 숨긴다. 규칙·계산이 0건이면 해당 탭을 만들지 않는다. run ID, citation/evidence/revision ID, hash, confidence factor/weight 등은 기본 화면에서 제거하고 접힌 **감사 정보**에 보존한다.

## 성능·관측 계약

각 run은 `run-metrics-events/`의 create-only event와 파생 `run-metrics.json`을 가진다. metrics는 비권위 산출물이며 Run ID, manifest, final packet hash에 포함되지 않는다.

- deterministic non-model 구간 hard budget: 5초
- packet/HTML 이후 protected server + browser dispatch hard budget: 2초
- Question Planner/Track A/Track B 외부 대기시간은 deterministic total과 분리
- 실패 후 재시도만 retry로 집계
- 검증 성공 후 같은 stage의 외부 호출은 0회여야 하며, 성공 이후 호출은 retry가 아니라 orchestration 오류다.

실제 수용 판정은 Windows Python 3.13에서 3회 timing과 p50/p95를 기록한 뒤 한다.

## 중단 조건

| 조건 | 처리 |
|---|---|
| `ACTIVE_WORKSPACE_NOT_BOUND` | filesystem 추측 금지, `$ERS_PDF` 선행 요구 |
| `ACTIVE_WORKSPACE_STALE` | review 시작 금지, workspace 재검증·재bind 요구 |
| `evidence.sqlite` 없음 | `$ERS_PDF` 선행 요구 |
| parser/source 상태가 `PENDING_*`, `BLOCKED`, `FAILED` | 정확한 상태와 reason 보고 |
| Planner handoff 또는 출력 누락 | `WAITING_QUESTION_PLAN` 유지, retrieval 시작 금지 |
| QuestionPlan 검증 실패 | `PLANNER_FAILED`, retrieval/Track A 시작 금지 |
| 유효 Plan의 검색 결과 0건 | `RETRIEVAL_NO_EVIDENCE`를 유지하고 임의 검색 확장 금지 |
| 필요한 승인 계산/규칙 없음 | 추정하지 않고 추가 입력 요구 또는 `ABSTAIN` |
| Track A 검증 실패 | Track B 시작 금지; 새 attempt 경로에서만 수정 |
| Track A 검증 성공 / `WAITING_TRACK_B` | Track A 외부 호출 금지 |
| Track B 검증 실패 | finalization 금지; 새 attempt 경로에서만 수정 |
| Track B 검증 성공 / finalization 진입 | Track B 외부 호출 금지 |
| packet/HTML 누락 | 브라우저 완료 주장 금지 |
| protected URL 실패 | Track A/B 재호출 금지, URL/browser handoff만 복구 |
| packet hash mismatch | 결정 저장/import 거부 |

## 금지

- active binding 없이 저장소에서 `evidence.sqlite`를 검색해 workspace 추측
- Question Planner를 건너뛰고 자연어 질문 전체를 곧바로 retrieval에 전달
- Planner 단계에서 답변·결론·적합성·confidence 생성
- quick mode 또는 정식 검토 우회
- 사용자에게 중간 JSON 수작업 요구
- 모델이 숫자·규칙 결과·citation을 새로 만드는 행위
- 모델이 canonical `track-a-output.json` 또는 canonical `track-b-output.json`을 직접 작성·덮어쓰기
- 검증 성공한 Track A/Track B stage에 대해 외부 AI를 다시 호출
- `READY_FOR_HUMAN_REVIEW`를 승인으로 표현
- machine packet의 `human_decision` 수정
- metrics를 권위 해시에 포함
