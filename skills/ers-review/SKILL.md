---
name: ers-review
description: Use when a user invokes $ERS_REVIEW or asks Codex Desktop to answer a question from a parsed Evidence Review System workspace.
---

# ERS Review

## 목적

`$ERS_REVIEW <질문>`은 파싱된 ERS workspace에서 **모든 질문을 정식 검토(formal review)** 로 처리한다. 빠른 조회 모드는 없다. 사용자는 query JSON, review-run request, Track A/B 중간 JSON을 직접 작성하지 않는다.

프로젝트 Python runtime은 모델을 호출하지 않는다. Codex가 deterministic handoff를 읽어 Track A와 Track B를 각각 작성하고, 프로젝트 runtime은 각 결과를 검증·고정한다.

## 사전 조건

1. `$ERS_PDF`로 준비된 workspace를 사용한다.
2. `<workspace>/evidence/evidence.sqlite`가 있어야 한다.
3. 인용 가능한 revision의 page image cache가 `<workspace>/page-images/<REVISION-ID>/`에 준비되어 있어야 한다.
4. 계산이 필요한 질문은 승인된 `CalculationResult`, 규칙이 필요한 질문은 승인된 `RuleResult`를 먼저 확보한다. prose에서 새 계산값이나 규칙 결과를 만들지 않는다.

사전 조건이 충족되지 않으면 질문에 답하지 말고 정확한 blocking state를 보고한다.

## 권위 흐름

### 1. 질문 준비

```powershell
evidence-review review-question prepare `
  --workspace <workspace> `
  --question "<질문>"
```

사용자가 명시한 검색 확장어만 `--expansion`으로 추가할 수 있다. 계산·규칙 결과가 필요한 경우에만 다음 옵션을 추가한다.

```text
--calculation-result <path>
--rule-result <path>
--approved-rule-result-id <id>
```

준비 단계가 만드는 `review-request.json`, `evidence-query.json`, `track-a-bundle.json`, next-action 파일은 runtime 산출물이다. 사용자가 손으로 작성하지 않는다.

동일한 deterministic request를 다시 실행하면 같은 Run ID를 재개한다. append-only workflow event journal이 마지막 유효 상태를 결정한다.

### 2. Track A 작성과 즉시 검증

Codex는 `track-a-bundle.json`과 `TRACK_A_INSTRUCTIONS.md`만 사용해 Track A를 작성한다. Track A는 제공된 근거·계산·규칙을 설명할 수 있으나 새로운 근거, 계산, 규칙 상태, 사람 판정을 만들 수 없다.

작성 직후 Track B를 시작하기 전에 반드시 검증한다.

```powershell
evidence-review review-question submit-track-a `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-a-output <track-a-output.json>
```

검증 실패 시 같은 단계에서 수정한다. Track A가 검증되기 전에 Track B를 작성하지 않는다.

### 3. Track B 독립 감사

Track B는 검증된 Track A의 **모든 claim을 한 번씩** 독립 감사한다. Track A를 재작성하거나 사람 판정을 만들지 않는다.

```powershell
evidence-review review-question submit-track-b `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-b-output <track-b-output.json> `
  --publish
```

Track B 검증을 통과하면 기존 finalizer가 `final-review-packet.json`과 `review.html`을 만든다. `READY_FOR_HUMAN_REVIEW`는 자동 승인 상태가 아니다. `ABSTAIN`은 기록된 사유를 유지한다.

### 4. 보호 브라우저 열기

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

보호 URL은 `127.0.0.1`의 run-scoped token 경로다. packet/HTML 생성 이후 브라우저 handoff가 실패하면 완료로 보고하지 않는다.

`--reviewer-id`를 생략한 경우 결정 저장 또는 보관 envelope 생성 시 reviewer ID를 한 번 확인한다.

### 5. 사람 결정

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
- Track A/B 외부 대기시간은 deterministic total과 분리
- 실패 후 재시도만 retry로 집계

실제 수용 판정은 Windows Python 3.11/3.13에서 3회 timing과 p50/p95를 기록한 뒤 한다.

## 중단 조건

| 조건 | 처리 |
|---|---|
| `evidence.sqlite` 없음 | `$ERS_PDF` 선행 요구 |
| parser/source 상태가 `PENDING_*`, `BLOCKED`, `FAILED` | 정확한 상태와 reason 보고 |
| 필요한 승인 계산/규칙 없음 | 추정하지 않고 추가 입력 요구 또는 `ABSTAIN` |
| Track A 검증 실패 | Track B 시작 금지 |
| Track B 검증 실패 | finalization 금지 |
| packet/HTML 누락 | 브라우저 완료 주장 금지 |
| protected URL 실패 | URL/browser handoff 실패로 보고 |
| packet hash mismatch | 결정 저장/import 거부 |

## 금지

- quick mode 또는 정식 검토 우회
- 사용자에게 중간 JSON 수작업 요구
- 모델이 숫자·규칙 결과·citation을 새로 만드는 행위
- `READY_FOR_HUMAN_REVIEW`를 승인으로 표현
- machine packet의 `human_decision` 수정
- metrics를 권위 해시에 포함
