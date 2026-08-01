# Evidence Review System

PDF·파서 결과·Grist 자료를 **출처 추적 가능한 증거 데이터베이스**로 변환하고, 결정적 검색·계산·규칙 실행 결과를 바탕으로 사람이 최종 검토하는 법규 검토 런타임입니다.

현재 안정 태그: `ansim-v1.0`

> **중요:** 시스템은 검토 근거를 생성하지만 최종 판정을 내리지 않습니다.  
> `READY_FOR_HUMAN_REVIEW`는 승인 또는 적합 판정이 아니라 **사람이 검토할 준비가 완료됐다는 상태**입니다.

## 프로그램 개요

이 프로젝트는 법규·운영기준·도면 관련 자료를 AI가 임의로 해석하고 결론을 내리는 방식이 아니라, 다음 순서로 검토 근거를 고정합니다.

1. 원본 PDF와 파서 결과의 SHA-256, 페이지, 좌표, 개정 정보를 기록합니다.
2. 증거 레코드를 SQLite 스냅샷으로 저장합니다.
3. 검색 결과마다 문서·개정·페이지·evidence ID·bbox·원본 해시를 연결합니다.
4. 숫자 계산은 등록된 Math Engine에서만 실행합니다.
5. 판정 기준은 사람이 승인한 Rule Engine 규칙만 실행합니다.
6. Track A가 근거를 설명하고, 독립된 Track B가 모든 설명을 다시 감사합니다.
7. Confidence Policy와 강제 기권 규칙을 적용합니다.
8. 최종 결과를 `review.html`과 `final-review-packet.json`으로 생성합니다.
9. 사람의 결정은 기계 패킷과 분리된 append-only 파일에 기록합니다.

### 핵심 원칙

- **사람이 최종 결정**: AI와 규칙 엔진은 근거·계산·상태만 제공합니다.
- **출처 우선**: 모든 사실 주장은 원본 문서의 페이지와 bbox에 연결됩니다.
- **결정적 실행**: 동일 입력은 동일한 JSON과 해시를 생성해야 합니다.
- **오프라인 실행**: 프로젝트 코드에서 모델 API나 외부 검색 API를 호출하지 않습니다.
- **불확실성 보존**: 입력 누락, 출처 충돌, 낮은 신뢰도, Track B 거부 시 `ABSTAIN` 처리합니다.
- **기계 결과와 사람 기록 분리**: 기계 패킷의 `human_decision`은 항상 `null`입니다.

## 주요 구성 요소

| 구성 요소 | 역할 |
|---|---|
| Evidence Store | PDF·파서·표·이미지 증거를 SQLite에 저장하고 스냅샷 해시를 생성합니다. |
| Hybrid Retrieval | FTS, 구조화 검색, 관계 검색 결과를 결정적으로 결합합니다. |
| Math Engine | 등록된 버전의 계산식만 실행하고 입력·치환·결과 해시를 기록합니다. |
| Rule Engine | 사람이 승인한 JSON 규칙만 실행하고 `SATISFIED`, `NOT_SATISFIED`, `INDETERMINATE`, `ENGINE_ERROR`를 반환합니다. |
| Track A | 제공된 증거·계산·규칙 결과를 설명합니다. 직접 계산하거나 판정을 변경할 수 없습니다. |
| Track B | Track A의 모든 claim을 독립적으로 감사합니다. Track A를 다시 작성하지 않습니다. |
| Confidence / Abstention | 근거 완전성·추적성·규칙 범위 등을 점수화하고 강제 기권 사유를 적용합니다. |
| Review Packet | 원문 인용, 페이지 이미지, bbox overlay, 계산·규칙·신뢰도 추적을 HTML과 JSON으로 출력합니다. |
| Release Builder | Codex workspace, ChatGPT Web ZIP, SQLite, 승인 규칙과 검토 패킷을 재현 가능한 릴리스로 묶습니다. |

## 요구 환경

- Python 3.11 이상
- Git
- 로컬 파일 시스템
- PowerShell 예시는 Windows 기준이며 macOS/Linux에서는 경로와 가상환경 활성화 명령을 조정해야 합니다.

런타임 패키지는 외부 Python 의존성이 없습니다. 테스트와 정적 검증에는 `dev` 의존성을 설치합니다.

## 설치

```powershell
git clone https://github.com/sage1993/evidence-review-system.git
Set-Location evidence-review-system

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e "."
```

개발·검증 도구까지 설치하려면 다음을 사용합니다.

```powershell
python -m pip install -e ".[dev]"
```

설치 확인:

```powershell
ansim-review --help
python -m ansim_review --help
```

## 워크스페이스 구조

실제 경로는 변경할 수 있지만, 아래 파일과 디렉터리 구조를 기준으로 동작합니다.

```text
F:\ansim-workspace
├─ evidence
│  └─ ansim-evidence.sqlite
├─ rules
│  ├─ approved
│  └─ manifests
│     └─ active.json
├─ runs
│  ├─ final-review-packet.json
│  └─ RUN-XXXXXXXXXXXXXXXXXXXX
│     ├─ track-a-bundle.json
│     ├─ confidence-input.json
│     ├─ TRACK_A_INSTRUCTIONS.md
│     ├─ TRACK_B_INSTRUCTIONS.md
│     ├─ final-review-packet.json
│     └─ review.html
├─ releases
│  └─ ansim-v1.0
│     └─ acceptance-record.json
├─ src
│  └─ ansim_review
├─ skills
└─ AGENTS.md
```

기존 Ansim/Grist 자료를 마이그레이션할 때의 원본 구조는 다음 항목을 인식합니다.

```text
01_database/          # .grist 자료
02_source_pdf/        # 원본 PDF, 파서 JSON·메타데이터
03_extracted_images/  # 추출 이미지
04_visuals/           # 표 crop 등 시각 자료
05_exports/           # clause 및 기타 내보내기 자료
```

## 사용 방법

### 1. 기존 자료 마이그레이션

마이그레이션은 원본·Grist 파일을 날짜별로 백업하고, 작업 전후 원본 트리 해시가 동일한지 확인한 뒤 증거 스냅샷을 생성합니다.

```powershell
python scripts/migrate_ansim_workspace.py `
  F:\기존-ansim-workspace `
  F:\ansim-workspace `
  --date 2026-08-01
```

정상 완료 시 다음 메시지가 출력됩니다.

```text
ANSIM_MIGRATION_COMPLETE
```

### 2. 증거 검색

검색 요청 JSON과 SQLite 증거 DB를 이용해 출처가 연결된 evidence bundle을 생성합니다.

```powershell
ansim-review query `
  --db F:\ansim-workspace\evidence\ansim-evidence.sqlite `
  --request F:\ansim-case\evidence-query.json `
  --output F:\ansim-case\evidence-bundle.json
```

출력 파일이 이미 존재하면 덮어쓰지 않고 종료합니다.

### 3. 결정적 계산 실행

자유 형식 문장으로 계산하지 않고, 등록된 공식 ID와 버전이 포함된 요청 JSON을 Math Engine에 전달합니다.

```powershell
ansim-review math-run `
  --request F:\ansim-case\calculation-request.json `
  --output F:\ansim-case\calculation-result.json
```

계산 결과에는 공식 ID·버전·입력·치환·상태·manifest hash·result hash가 포함됩니다.

### 4. 검토 run 준비

검색·계산·규칙 결과를 포함한 `ansim/review-run-request` 문서를 검증하고 변경 불가능한 run 디렉터리를 생성합니다.

```powershell
ansim-review review-run prepare `
  --workspace F:\ansim-workspace `
  --request F:\ansim-case\review-request.json
```

출력 예시:

```json
{
  "stage": "prepare",
  "status": "AWAITING_TRACK_OUTPUTS",
  "run_id": "RUN-XXXXXXXXXXXXXXXXXXXX"
}
```

생성된 run 디렉터리의 다음 파일만 Track 작업에 사용합니다.

- `track-a-bundle.json`
- `TRACK_A_INSTRUCTIONS.md`
- `TRACK_B_INSTRUCTIONS.md`
- `confidence-input.json`

### 5. Track A 설명 작성

Codex Desktop 또는 ChatGPT Web에 다음 파일을 제공합니다.

- `TRACK_A_INSTRUCTIONS.md`
- `track-a-bundle.json`

Track A는 다음 작업만 수행할 수 있습니다.

- 제공된 증거를 인용해 claim 설명
- CalculationResult와 RuleResult를 그대로 참조
- 예외·충돌·누락 정보 정리

Track A는 다음 작업을 할 수 없습니다.

- 새 계산 수행
- RuleResult 상태 변경
- confidence 또는 abstention 결정
- `human_decision` 입력

결과는 `track-a-output.json`으로 저장합니다.

### 6. Track B 독립 감사

새 대화 또는 독립된 실행에서 다음 파일을 제공합니다.

- `TRACK_B_INSTRUCTIONS.md`
- `track-a-bundle.json`
- `track-a-output.json`

Track B는 Track A의 모든 claim을 정확히 한 번씩 감사하고, 인용·계산·규칙 참조가 일치하는지 확인합니다. 결과는 `track-b-output.json`으로 저장합니다.

### 7. 검토 패킷 확정

```powershell
ansim-review review-run finalize `
  --workspace F:\ansim-workspace `
  --run-id RUN-XXXXXXXXXXXXXXXXXXXX `
  --track-a-output F:\ansim-case\track-a-output.json `
  --track-b-output F:\ansim-case\track-b-output.json `
  --publish
```

finalize 단계는 다음을 검증합니다.

- 준비 단계 artifact의 SHA-256
- Track A 계약과 인용 무결성
- Track B의 독립 감사 범위
- Confidence Policy 계산
- 강제 abstention 사유
- 기존 출력 덮어쓰기 여부

주요 출력:

```text
runs/RUN-.../final-review-packet.json
runs/RUN-.../review.html
runs/final-review-packet.json      # --publish 사용 시
```

`--publish`는 릴리스 빌더가 사용할 패킷을 선택할 뿐이며 승인이나 사람 서명을 의미하지 않습니다.

### 8. 사람 검토

검토자는 `review.html`을 열고 다음 항목을 직접 확인합니다.

- 원문 인용과 문서·개정·페이지
- evidence ID와 source SHA-256
- bbox와 페이지 이미지 overlay
- 계산 입력·치환·결과 해시
- 규칙 ID·버전·상태·출처
- Track A 설명과 Track B 감사
- confidence factor와 contribution
- 예외·충돌·abstention reason

기계 패킷을 수정해 결정을 입력하지 않습니다. 사람의 결정과 릴리스 acceptance는 별도의 append-only JSON 파일에 기록해야 합니다.

## 상태 해석

| 상태 | 의미 |
|---|---|
| `READY_FOR_HUMAN_REVIEW` | 결정적 검증을 통과했고 사람이 검토할 준비가 됐습니다. 승인 상태가 아닙니다. |
| `ABSTAIN` | 입력 누락, 출처 충돌, Track B 거부, 낮은 confidence 등으로 기계가 결론 제시를 중단했습니다. |
| `SATISFIED` | 개별 승인 규칙의 조건을 충족했습니다. 전체 사업 승인 또는 법적 적합 판정과 동일하지 않습니다. |
| `NOT_SATISFIED` | 개별 규칙의 조건을 충족하지 못했습니다. |
| `INDETERMINATE` | 규칙 실행에 필요한 정보가 부족하거나 확정할 수 없습니다. |
| `ENGINE_ERROR` | 계산 또는 규칙 엔진 실행 중 구조적 오류가 발생했습니다. |

## 오프라인 패키지와 릴리스

릴리스 빌더는 다음 artifact를 생성합니다.

- `evidence.sqlite`
- `approved-rules.zip`
- `codex-workspace.zip`
- `chatgpt-web-runtime.zip`
- `release-validation.json`
- `final-review-packet.json`
- `release-manifest.json`

```powershell
python scripts/build_ansim_release.py `
  F:\ansim-workspace `
  F:\ansim-release-output
```

서명된 acceptance가 없거나 후보·패킷 해시가 일치하지 않으면 릴리스 상태는 `BLOCKED`이며 태그 생성을 허용하지 않습니다.

ChatGPT Web ZIP은 설치 없이 오프라인으로 실행할 수 있도록 구성되며, 원본 PDF는 기본적으로 포함하지 않습니다.

## 개발 검증

```powershell
python -m pip install -e ".[dev]"

pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

릴리스 재현성을 확인할 때는 같은 워크스페이스에서 두 번 빌드하고 `candidate_hash`, `packet_hash`, 모든 artifact SHA-256이 동일한지 비교합니다.

## 상세 문서

- [Codex 작업 절차](docs/CODEX_WORKFLOW.md)
- [ChatGPT Web 작업 절차](docs/CHATGPT_WEB_WORKFLOW.md)
- [검토자 작업 절차](docs/REVIEWER_WORKFLOW.md)
- [릴리스 acceptance 체크리스트](docs/acceptance/ANSIM_ACCEPTANCE_CHECKLIST.md)

## 안전 경계

- AI 응답만으로 법규 적합 여부를 확정하지 않습니다.
- 원문 확인 없이 요약·검색 결과만 사용하지 않습니다.
- 계산식을 자연어 답변에서 다시 계산하지 않습니다.
- 승인되지 않은 candidate rule은 실행 규칙으로 사용하지 않습니다.
- `READY_FOR_HUMAN_REVIEW`를 승인·허가·적합 판정으로 표현하지 않습니다.
- 사람의 결정은 기계 패킷과 분리해 기록합니다.
