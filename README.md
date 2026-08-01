# Evidence Review System

사용자가 제공하는 서로 다른 PDF와 파서 결과를 **출처 추적 가능한 증거 데이터베이스**로 변환하고, 검색·계산·규칙 실행 결과를 사람이 최종 검토하도록 지원하는 범용 문서 검토 런타임이다.

> 이 시스템은 적합·부적합을 최종 결정하지 않는다. `READY_FOR_HUMAN_REVIEW`는 사람이 검토할 준비가 완료됐다는 뜻이며 승인 상태가 아니다.

## 적용 대상

입력 PDF의 파일명, 문서명, 분야, 페이지 수는 매번 달라도 된다. 예를 들면 다음 자료를 같은 입력 계약으로 등록할 수 있다.

- 법령·조례·운영기준
- 일반 보고서와 사업계획서
- 표 중심 자료
- 이미지 기반 스캔 PDF
- 건축 도면 PDF
- 사용자가 별도로 제공한 참고 이미지·표

초기 개발에 사용된 안심주택 기준 자료는 일반적인 테스트 샘플 중 하나일 뿐이다. 신규 처리 로직은 해당 문서명이나 `law-1`, `law-2` 같은 파일명에 의존하지 않는다.

## 핵심 원칙

| 원칙 | 적용 방식 |
|---|---|
| 원본 우선 | PDF 원본 SHA-256, 페이지, 좌표, parser artifact를 기록한다. |
| 파일명 비종속 | 내부 문서 ID는 명시적 ID 또는 원본 SHA-256으로 생성한다. |
| 결정적 실행 | 동일한 정규화 입력은 동일한 JSON, Run ID, 결과 해시를 만든다. |
| 계산 분리 | 숫자 계산은 등록된 Math Engine 공식으로만 수행한다. |
| 규칙 승인 | 사람이 승인한 버전 규칙만 Rule Engine에서 실행한다. |
| 불확실성 보존 | 파서 결과 누락, 출처 충돌, 입력 부족은 보류 또는 `ABSTAIN` 처리한다. |
| 사람 최종 결정 | 기계 packet의 `human_decision`은 항상 `null`이며 사람 결정은 별도 기록한다. |

## 처리 흐름

```text
사용자 PDF 등록
→ 원본 SHA-256 및 역할 기록
→ parser artifact 또는 drawing-backend route 확인
→ document ID·revision ID 생성
→ 페이지·문단·표·이미지 evidence 생성
→ evidence.sqlite 및 FTS 인덱스 생성
→ 도면 candidate·reviewer confirmation·confirmed input 생성
→ 질문별 evidence 검색
→ 필요한 계산·승인 규칙 실행
→ Track A 설명 / Track B 감사
→ review.html 및 final-review-packet.json 생성
→ 사람 최종 검토
```

parser artifact가 없는 `REFERENCE_DOCUMENT`, `CASE_TABLE`, `SUPPORTING_IMAGE` 입력은 `PENDING_PARSER_OUTPUT` 상태로 남고 evidence ingest를 중단한다. parser가 없는 `CASE_DRAWING`은 `DRAWING_BACKEND_ONLY`로 분리되어 evidence DB 생성 대상에서 제외되고, M1 drawing backend의 immutable intake·수동 annotation·confirmation 흐름으로 전달된다. 도면만 포함된 source batch는 빈 evidence DB를 만들지 않고 `NO_EVIDENCE_SOURCES`로 거부한다.

## 요구 환경

- Python 3.11 이상
- Git
- 로컬 파일 시스템

런타임 패키지는 외부 Python 의존성이 없다. 테스트·정적 검증 도구는 `dev` extra로 설치한다.

## 설치

```powershell
git clone https://github.com/sage1993/evidence-review-system.git
Set-Location evidence-review-system

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

설치 확인:

```powershell
evidence-review --help
python -m ansim_review --help
```

`ansim_review`은 기존 실행 환경과 artifact 호환을 위해 당분간 유지되는 내부 Python namespace이다. 신규 사용자-facing 명칭과 JSON format은 `evidence-review`를 사용한다.

## 권장 워크스페이스

```text
F:\evidence-review-workspace
├─ inputs
│  ├─ original
│  │  ├─ reference-a.pdf
│  │  └─ project-drawing.pdf
│  └─ parser
│     └─ reference-a.json
├─ manifests
│  └─ source-batch.json
├─ evidence
│  └─ evidence.sqlite
├─ cases
│  └─ CASE-001
│     ├─ sources\drawings
│     ├─ candidates
│     ├─ confirmations
│     └─ confirmed-inputs.json
├─ rules
│  ├─ approved
│  └─ manifests
│     └─ active.json
├─ runs
│  ├─ final-review-packet.json
│  └─ RUN-XXXXXXXXXXXXXXXXXXXX
└─ page-images
```

폴더 이름 자체가 문서의 역할이나 ID를 결정하지 않는다. 입력 관계는 `source-batch.json`과 case manifest가 명시한다.

## 1. 임의 PDF 등록

### source-batch manifest

```json
{
  "format": "evidence-review/source-batch",
  "version": 1,
  "sources": [
    {
      "source_path": "inputs/original/reference-a.pdf",
      "role": "REFERENCE_DOCUMENT",
      "document_id": null,
      "display_title": "사용자 제공 참고 기준",
      "parser": {
        "kind": "OPENDATALOADER_JSON",
        "artifact_path": "inputs/parser/reference-a.json"
      }
    },
    {
      "source_path": "inputs/original/project-drawing.pdf",
      "role": "CASE_DRAWING",
      "document_id": "PROJECT-DRAWING-001",
      "display_title": "사업 도면",
      "parser": null
    }
  ]
}
```

### 필드 의미

| 필드 | 의미 |
|---|---|
| `source_path` | batch root 아래의 원본 파일 상대경로 |
| `role` | 참고문서, 도면, 표, 이미지 등 입력 역할 |
| `document_id` | 선택값. 없으면 원본 SHA-256으로 자동 생성 |
| `display_title` | 화면 표시용 제목이며 내부 ID에는 사용하지 않음 |
| `parser.kind` | parser adapter 종류 |
| `parser.artifact_path` | 원본과 연결된 parser 결과 상대경로 |

현재 범용 ingest에서 직접 지원하는 parser 종류는 `OPENDATALOADER_JSON`이다. 다른 parser는 adapter registry에 별도 구현해야 한다.

`CASE_DRAWING`에 parser가 없으면 source-batch 명세에는 유지하되 evidence DB에는 넣지 않는다. CLI 결과에서 해당 source는 `DRAWING_BACKEND_ONLY`로 반환되며, 도면 backend가 원본을 case-local immutable storage로 다시 복사한 뒤 처리한다. parser가 있는 도면은 일반 evidence ingest에도 포함할 수 있다.

### 증거 DB 생성

```powershell
evidence-review source-batch ingest `
  --root F:\evidence-review-workspace `
  --manifest F:\evidence-review-workspace\manifests\source-batch.json `
  --output F:\evidence-review-workspace\evidence\evidence.sqlite
```

생성 결과에는 다음 값이 포함된다.

- 자동 또는 명시적 `document_id`
- 원본 hash 기반 `revision_id`
- 원본 SHA-256
- snapshot hash
- 문서·페이지·요소 수
- source별 `READY_FOR_INGESTION`, `PENDING_PARSER_OUTPUT`, `DRAWING_BACKEND_ONLY` 상태

### 문서 ID 정책

- 명시적 ID가 있으면 안전한 machine ID 문법을 검증해 사용한다.
- 명시적 ID가 없으면 `DOC-<원본 SHA-256 앞 20자리>`를 사용한다.
- 동일 bytes와 다른 파일명은 같은 자동 문서 ID로 dedupe된다.
- 같은 파일명이라도 bytes가 다르면 다른 자동 문서 ID가 된다.
- 같은 명시적 문서 ID에 서로 다른 bytes를 연결할 수 없다.
- source-batch와 case manifest의 식별자는 공통 path-safe identifier 정책을 사용한다.

## 2. 증거 검색

```powershell
evidence-review query `
  --db F:\evidence-review-workspace\evidence\evidence.sqlite `
  --request F:\review-case\evidence-query.json `
  --output F:\review-case\evidence-bundle.json
```

검색 결과는 문서 ID, revision ID, 페이지, evidence ID, bbox, 원본 SHA-256을 포함한다.

## 3. 결정적 계산

```powershell
evidence-review math-run `
  --request F:\review-case\calculation-request.json `
  --output F:\review-case\calculation-result.json
```

계산은 등록된 공식 ID와 버전으로만 실행한다. 결과에는 입력, 치환식, 원시 결과, 표시 결과, formula manifest hash와 result hash가 기록된다.

## 4. 검토 Run 준비

신규 요청 format은 `evidence-review/review-run-request`이다.

```powershell
evidence-review review-run prepare `
  --workspace F:\evidence-review-workspace `
  --request F:\review-case\review-request.json
```

Run ID는 다음 전체 정규화 입력을 반영한다.

- 질문과 프로젝트 입력
- evidence
- 계산 결과
- 규칙 결과
- 승인 규칙 결과 ID
- confidence 입력

따라서 승인 규칙 또는 confidence 값이 달라지면 다른 Run ID가 생성된다.

## 5. Track A와 Track B

준비된 Run에서 다음 파일을 사용한다.

- `track-a-bundle.json`
- `TRACK_A_INSTRUCTIONS.md`
- `TRACK_B_INSTRUCTIONS.md`
- `confidence-input.json`

Track A는 제공된 증거·계산·규칙 결과를 설명할 수 있지만 새 계산, 규칙 상태 변경, confidence 결정, 사람 결정 입력은 할 수 없다. Track B는 모든 Track A claim을 독립적으로 감사한다.

결과 파일:

- `track-a-output.json`
- `track-b-output.json`

## 6. 검토 Packet 확정

```powershell
evidence-review review-run finalize `
  --workspace F:\evidence-review-workspace `
  --run-id RUN-XXXXXXXXXXXXXXXXXXXX `
  --track-a-output F:\review-case\track-a-output.json `
  --track-b-output F:\review-case\track-b-output.json `
  --publish
```

주요 출력:

```text
runs/RUN-.../final-review-packet.json
runs/RUN-.../review.html
runs/final-review-packet.json
```

`--publish`는 릴리스 빌더가 사용할 packet을 선택할 뿐, 승인이나 사람 서명을 의미하지 않는다.

## 상태 해석

| 상태 | 의미 |
|---|---|
| `PENDING_PARSER_OUTPUT` | evidence ingest 대상 원본 PDF에 parser artifact가 없어 ingest를 진행하지 않음 |
| `DRAWING_BACKEND_ONLY` | parser 없는 `CASE_DRAWING`을 evidence DB에서 제외하고 case drawing backend로 전달함 |
| `READY_FOR_HUMAN_REVIEW` | 결정적 검증을 통과해 사람이 검토할 준비가 됨 |
| `ABSTAIN` | 입력 누락·출처 충돌·감사 실패 등으로 기계 결론을 중단함 |
| `SATISFIED` | 개별 승인 규칙 조건을 충족함 |
| `NOT_SATISFIED` | 개별 승인 규칙 조건을 충족하지 못함 |
| `INDETERMINATE` | 개별 규칙 실행에 필요한 정보가 부족함 |
| `ENGINE_ERROR` | 계산 또는 규칙 엔진의 구조적 검증이 실패함 |

`NO_EVIDENCE_SOURCES`는 상태가 아니라 입력 오류다. source batch에 parser-ready evidence source가 하나도 없을 때 빈 evidence DB 생성을 방지하기 위해 반환한다.

## 안전 경계

- PDF 파일명이나 문서 제목으로 법규 종류를 추정하지 않는다.
- parser 결과가 없는 evidence source의 내용을 만들어내거나 빈 ingest를 완료하지 않는다.
- parser 없는 case drawing은 자동 evidence로 취급하지 않고 별도 backend에서 reviewer confirmation을 요구한다.
- 규칙 ID와 버전은 승인 파일 경로로 사용하기 전에 검증한다.
- 규칙 expression의 입력 참조는 승인 전에 input schema와 대조한다.
- 규칙은 실제로 참조한 계산 결과에만 의존한다.
- 사람의 결정은 기계 packet과 분리해 append-only 파일로 기록한다.

## Legacy 호환

다음 항목은 초기 샘플 워크스페이스와 기존 릴리스의 읽기·이행을 위해서만 남아 있다.

- 내부 Python namespace `ansim_review`
- 이전 CLI 별칭 `ansim-review`
- `ansim/*` 형식의 기존 review-run 요청
- `01_database`, `02_source_pdf`, `03_extracted_images`, `04_visuals`, `05_exports` 번호 폴더를 읽는 legacy migration adapter
- 기존 릴리스 스크립트와 `ansim-v1.0` artifact

신규 프로젝트는 위 legacy 구조를 기본 입력 방식으로 사용하지 않는다. 기존 artifact는 명시적 compatibility adapter를 통해서만 읽고, 신규 source batch와 Run은 `evidence-review/*` 형식으로 생성한다.

## 개발 검증

```powershell
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

## 상세 문서

- [범용 PDF 및 신뢰 경계 설계](docs/superpowers/specs/2026-08-02-generic-pdf-and-hardening-design.md)
- [범용 PDF 구현 계획](docs/superpowers/plans/2026-08-02-generic-pdf-and-hardening.md)
- [도면 근거 backend 설계](docs/superpowers/specs/2026-08-02-drawing-evidence-backend-design.md)
- [도면 근거 backend 구현 계획](docs/superpowers/plans/2026-08-02-drawing-evidence-backend.md)
- [Codex 작업 절차](docs/CODEX_WORKFLOW.md)
- [ChatGPT Web 작업 절차](docs/CHATGPT_WEB_WORKFLOW.md)
- [검토자 작업 절차](docs/REVIEWER_WORKFLOW.md)
