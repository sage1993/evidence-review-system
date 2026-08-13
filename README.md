# Evidence Review System

Codex Desktop에서 사용자가 제공한 PDF를 로컬 근거 DB로 만들고, **모든 질문을 정식 근거 검토**로 처리한 뒤 비개발자용 Review Workspace를 여는 오프라인 문서 검토 도구입니다.

일반 사용자는 두 단축어만 기억하면 됩니다.

```text
$ERS_PDF 이 PDF 파싱해줘
$ERS_REVIEW <검토 질문>
```

## 1. 설치

필요 항목:

- Codex Desktop
- Evidence Review System 소스 또는 배포 ZIP
- 검토할 PDF
- OpenDataLoader PDF 등 지원되는 로컬 parser

소스 설치 예시:

```powershell
git clone https://github.com/sage1993/evidence-review-system.git
Set-Location evidence-review-system
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

개발·검증 도구까지 설치하려면:

```powershell
python -m pip install -e ".[dev]"
```

런타임은 PDF geometry 검증 등에 필요한 로컬 Python 의존성을 사용할 수 있지만 실행 중 외부 검색/API를 요구하지 않습니다. 새 오프라인 환경에 설치할 때는 필요한 wheel을 미리 준비해야 합니다.

## 2. PDF 준비 — `$ERS_PDF`

PDF를 첨부하거나 경로를 지정한 뒤 다음처럼 요청합니다.

```text
$ERS_PDF 이 PDF 파싱해줘
```

Codex와 ERS는 다음을 준비합니다.

- 원본 PDF 보존과 SHA-256 기록
- parser artifact 및 source binding 검증
- parser warnings와 reproducibility 확인
- source-batch v2 검증
- 검색 가능한 `evidence.sqlite`
- revision 단위의 verified PDF page image cache

원본과 raw parser output은 덮어쓰지 않습니다. parser가 없거나 source hash가 맞지 않으면 성공으로 처리하지 않습니다. 도면처럼 사람 확인이 필요한 자료는 확인 전까지 계산·규칙 입력으로 사용하지 않습니다.

질문 가능한 상태가 되면 `$ERS_REVIEW <질문>`으로 넘어갑니다.

## 3. 질문 — `$ERS_REVIEW`

모든 질문은 하나의 정식 파이프라인을 사용합니다. 빠른 조회 모드는 없습니다.

```text
$ERS_REVIEW 이 사업의 주차 기준 충족 여부를 근거 페이지와 함께 검토해줘
```

내부 흐름:

```text
질문
→ 로컬 근거 검색
→ 정식 review request
→ Track A 작성
→ Track A 즉시 검증
→ Track B 독립 감사
→ Track B 검증
→ final-review-packet.json
→ review.html
→ 보호 브라우저
→ 사람 결정
```

사용자는 query JSON, review request, Track A/B 중간 파일을 손으로 작성하지 않습니다. Codex가 runtime이 만든 handoff를 따라 외부 Track 작업을 수행하고, runtime은 각 결과를 deterministic하게 검증합니다.

계산이 필요한 질문은 승인된 Math Engine 결과를, 규칙이 필요한 질문은 승인된 Rule Engine 결과를 사용합니다. 대화 중 임의 계산이나 규칙 판정을 만들어 끼워 넣지 않습니다.

## 4. Review Workspace

정식 검토가 완료되면 `review.html`을 보호된 localhost 주소로 엽니다.

기본 화면은 비개발자 기준으로 다음 순서입니다.

1. **검토 결과** — 한국어 상태와 1문장 결론
2. **판단 근거** — PDF 원문, 페이지, 인용 좌표(bbox)
3. **추가 확인** — 누락·충돌·예외 등이 실제로 있을 때만 표시
4. **검토자 의견** — 결정과 메모

단일 근거 주장에서는 불필요한 항목 네비게이터를 숨깁니다. 규칙·계산이 0건이면 빈 섹션을 만들지 않습니다. run ID, citation/evidence/revision ID, hash, confidence factor/weight 등은 기본 화면에서 빼고 접힌 **감사 정보**에 보존합니다.

`READY_FOR_HUMAN_REVIEW`는 사람이 검토할 준비가 되었다는 뜻이며 자동 승인이나 적합 판정이 아닙니다.

## 5. 사람 결정

보호 브라우저에서는 일반적으로 사용자가 입력하는 것은 다음 둘뿐입니다.

- 결정
- 검토 의견

화면 결정값:

| 표시 | 내부 값 |
|---|---|
| 내용 확인 완료 | `SATISFIED` |
| 내용에 오류 있음 | `NOT_SATISFIED` |
| 조건부 확인 | `CONDITIONAL` |
| 추가 자료 필요 | `ADDITIONAL_REVIEW_REQUIRED` |

검토자 ID는 보호 세션 시작 시 지정할 수 있고, packet hash는 현재 immutable packet에서 자동으로 결합됩니다. 검토 시각은 서버가 timezone이 포함된 ISO-8601 형식으로 생성합니다.

결정 기록은 `human-decisions/` 아래에 **append-only 별도 파일**로 저장됩니다. machine packet과 `review.html`은 수정하지 않습니다. 유효한 결정이 생기면 화면에서 `REVIEW_COMPLETED`를 표시할 수 있습니다.

## 6. 보관용 HTML

`review.html`을 파일로 직접 열면 보호 서버가 없으므로 결정 저장이 되지 않습니다. 이 경우 **결정 JSON 다운로드**로 5필드 envelope를 만들 수 있습니다.

HTML 파일 저장과 결정 기록 저장은 서로 다른 작업입니다. 다운로드한 envelope는 승인된 import 명령으로 현재 packet hash를 다시 검증한 뒤 append-only 기록으로 반영합니다.

```powershell
evidence-review review-run import-decision `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --envelope <human-decision-envelope.json>
```

## 7. 성능 기록

정식 review run은 각 단계 시간을 `run-metrics-events/`와 파생 `run-metrics.json`에 기록합니다.

- deterministic non-model hard budget: 5초
- packet/HTML 이후 protected server + browser dispatch hard budget: 2초
- Track A/B 외부 대기시간은 별도 집계
- 실패 후 재시도만 retry로 집계

metrics는 성능 관측용이며 Run ID나 packet hash를 바꾸지 않습니다.

실제 성능 수용은 Windows Python 3.11/3.13에서 같은 단순 질문을 3회 실행하고 p50/p95를 기록해 판단합니다.

## 8. 잘 안 될 때

- **parser 결과 없음:** `$ERS_PDF` 단계에서 parser 설치·source binding을 해결합니다.
- **근거 DB 없음:** `evidence.sqlite`가 만들어질 때까지 질문을 진행하지 않습니다.
- **도면 확인 필요:** 사람 확인 전에는 계산·규칙 입력으로 사용하지 않습니다.
- **Track A 검증 실패:** Track B를 시작하지 않고 Track A를 수정합니다.
- **HTML이 열리지 않음:** packet/HTML 생성 여부와 protected server 상태를 확인합니다.
- **결정 저장 실패:** reviewer ID, 현재 packet hash, 결정/메모, 보호 서버 상태를 확인합니다.
- **보관 HTML:** 서버 저장 대신 결정 JSON을 다운로드해 승인 import 경로를 사용합니다.

서버 상태 확인/종료:

```powershell
evidence-review review-run serve-status --workspace <workspace> --run-id <RUN-ID>
evidence-review review-run serve-stop --workspace <workspace> --run-id <RUN-ID>
```

## 9. 개발자·검토자 문서

- [Codex workflow](docs/CODEX_WORKFLOW.md)
- [Reviewer workflow](docs/REVIEWER_WORKFLOW.md)
- [Offline execution boundary](docs/OFFLINE_EXECUTION.md)
- [Manual acceptance policy](docs/MANUAL_ACCEPTANCE_POLICY.md)
- [Source Batch v2](docs/SOURCE_BATCH_V2.md)
- [PDF skills](skills/README.md)

Issue #87의 Windows 3.11/3.13 수동 E2E 기록은 `docs/acceptance/issue-87/README.md`에 보존합니다. 실행하지 않은 검증은 PASS로 쓰지 않고 `NOT_RUN`으로 기록합니다.
