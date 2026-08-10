# Evidence Review System

PDF를 근거가 남는 검색·계산 자료로 바꾸고, 마지막 판단은 사람이 하도록 돕는 문서 검토 프로그램입니다.

> **중요:** 이 프로그램은 승인·적합·부적합을 최종 결정하지 않습니다. `READY_FOR_HUMAN_REVIEW`는 “사람이 검토할 준비가 됨”이라는 뜻입니다.

## 먼저 이해하기

이 프로그램의 흐름은 간단히 다음과 같습니다.

```text
원본 PDF와 parser 결과 준비
→ 파일 연결 상태 확인
→ 검색용 evidence DB 생성
→ 질문에 맞는 근거 검색
→ 필요한 계산과 승인된 규칙 실행
→ 검토용 HTML과 결과 packet 생성
→ 사람이 원본 근거를 확인하고 최종 결정
```

여기서 `parser artifact`는 PDF 안의 글자·표·페이지 위치를 읽어 둔 별도 결과 파일입니다. 참고 문서나 표를 검색하려면 원본 PDF만으로는 부족하고, 등록된 parser 결과가 필요합니다.

## 어떤 PDF를 처리할 수 있나요?

| 자료 | 처리 방식 |
|---|---|
| 법령, 기준, 보고서, 사업계획서 | parser 결과가 있으면 검색용 DB에 넣을 수 있습니다. |
| 표 중심 자료 | `CASE_TABLE` 또는 `REFERENCE_DOCUMENT`로 등록합니다. |
| 이미지 기반 PDF | parser가 페이지와 이미지 내용을 제공해야 합니다. |
| 건축·사업 도면 | 일반 참고문서 검색과 분리해 도면 확인 절차를 거칩니다. 확인되지 않은 도면값은 계산에 사용하지 않습니다. |
| 참고 이미지 | 보조 자료로 보관할 수 있지만, 그 자체가 승인된 기준이 되지는 않습니다. |

파일명이나 제목만 보고 문서 종류를 추정하지 않습니다. 원본 파일과 parser 결과의 연결은 manifest와 SHA-256 해시로 확인합니다.

## 1. 준비물과 설치

### 필요한 것

- Windows PowerShell 또는 터미널
- Python 3.11 이상
- Git
- 원본 PDF
- 검색하려는 참고문서의 parser 결과 파일

현재 런타임은 외부 API나 인터넷 검색 없이 로컬 파일을 처리합니다.

### 설치

PowerShell에서 다음을 실행합니다.

```powershell
git clone https://github.com/sage1993/evidence-review-system.git
Set-Location evidence-review-system

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

설치가 끝났는지 확인합니다.

```powershell
evidence-review --help
```

`python -m ansim_review --help`도 동작하지만, 새 작업에서는 `evidence-review` 명령을 사용합니다.

## 2. 작업 폴더 만들기

프로젝트 폴더와 원본 자료를 별도 작업 폴더에 둡니다. 아래 경로는 예시이므로 본인의 경로로 바꾸세요.

```text
F:\evidence-review-workspace
├─ inputs
│  ├─ original
│  │  ├─ reference.pdf        ← 참고 기준 PDF
│  │  └─ project-drawing.pdf  ← 검토 대상 도면 PDF(선택)
│  └─ parser
│     └─ reference.json       ← reference.pdf에 대응하는 parser 결과
├─ manifests
│  └─ source-batch.json
├─ evidence
└─ runs
```

원본 PDF와 raw parser 결과는 보존해야 합니다. 프로그램이 만든 결과를 원본 폴더에 덮어쓰지 마세요.

## 3. source manifest 작성하기

manifest는 “어떤 파일을 어떤 역할로 사용할지” 적는 JSON 파일입니다. `manifests\source-batch.json`을 만들고 다음과 같이 작성합니다.

```json
{
  "format": "evidence-review/source-batch",
  "version": 2,
  "sources": [
    {
      "source_path": "inputs/original/reference.pdf",
      "role": "REFERENCE_DOCUMENT",
      "document_id": null,
      "display_title": "검토 기준 문서",
      "parser": {
        "kind": "OPENDATALOADER_JSON",
        "artifact_path": "inputs/parser/reference.json",
        "options": {}
      }
    },
    {
      "source_path": "inputs/original/project-drawing.pdf",
      "role": "CASE_DRAWING",
      "document_id": "PROJECT-DRAWING-001",
      "display_title": "검토 대상 도면",
      "parser": null
    }
  ]
}
```

도면이 없으면 두 번째 항목은 삭제해도 됩니다. `source_path`와 `artifact_path`는 작업 폴더를 기준으로 한 상대경로여야 합니다.

주요 값은 다음 뜻입니다.

| 값 | 쉬운 뜻 |
|---|---|
| `REFERENCE_DOCUMENT` | 검색에 사용할 참고 기준 문서 |
| `CASE_TABLE` | 검색에 사용할 표 자료 |
| `CASE_DRAWING` | 별도 확인이 필요한 도면 |
| `SUPPORTING_IMAGE` | 보조 이미지 |
| `document_id` | 문서를 구분하는 ID. 비워 두면 원본 hash로 자동 생성 |
| `parser.kind` | parser 결과의 종류 |
| `parser.artifact_path` | PDF에 연결된 parser 결과 파일 |

## 4. 파일 연결 상태 확인하기

DB를 만들기 전에 다음 명령으로 파일 연결과 준비 상태를 확인합니다.

```powershell
evidence-review source-batch prepare `
  --root F:\evidence-review-workspace `
  --manifest F:\evidence-review-workspace\manifests\source-batch.json
```

이 단계는 DB를 만들지 않습니다. 파일이 올바르게 연결됐는지와 다음에 해야 할 일을 알려 줍니다.

| 표시 | 뜻 | 다음 행동 |
|---|---|---|
| `PENDING_PARSER_OUTPUT` | 참고문서에 parser 결과가 없음 | parser 결과를 준비해 manifest에 연결합니다. |
| `PENDING_REFERENCE_INGESTION` | 참고문서를 DB에 넣을 준비가 됨 | `ingest`를 실행합니다. |
| `PENDING_DRAWING_INGESTION` | 도면을 별도 도면 절차로 보낼 상태 | 도면 확인 작업을 진행합니다. |
| `INPUT_CONFIRMATION_REQUIRED` | 사람이 도면 후보를 확인해야 함 | 확인 전에는 계산에 사용하지 않습니다. |
| `READY_TO_EVALUATE` | 필요한 입력과 확인이 준비됨 | 검색·계산·규칙 실행을 진행합니다. |
| `BLOCKED` | 지원하지 않는 parser나 권한 문제 | reason code를 확인하고 입력을 수정합니다. |
| `FAILED` | 파일 구성 또는 무결성 검증 실패 | 경로, hash, JSON 형식을 확인합니다. |

등록하지 않은 parser를 다른 parser로 자동 대체하지 않습니다.

## 5. 검색용 evidence DB 만들기

상태가 준비되면 다음 명령으로 검색용 SQLite DB를 만듭니다.

```powershell
evidence-review source-batch ingest `
  --root F:\evidence-review-workspace `
  --manifest F:\evidence-review-workspace\manifests\source-batch.json `
  --output F:\evidence-review-workspace\evidence\evidence.sqlite
```

성공하면 `evidence\evidence.sqlite`가 생기고, 문서 ID·페이지·근거 ID·원본 hash 등의 추적 정보가 함께 기록됩니다.

다음 경우에는 불완전한 DB를 만들지 않고 멈춥니다.

- 참고문서의 parser 결과가 없음
- 등록되지 않은 parser 종류를 사용함
- PDF와 parser 결과의 hash가 서로 다름
- 검색 가능한 참고 근거가 하나도 없음

## 6. 질문에 대한 근거 검색하기

검색할 질문을 `evidence-query.json`으로 저장합니다. 가장 단순한 형식은 다음과 같습니다.

```json
{
  "question": "검토하려는 조건은 무엇인가?",
  "limit": 20
}
```

그 다음 검색을 실행합니다.

```powershell
evidence-review query `
  --db F:\evidence-review-workspace\evidence\evidence.sqlite `
  --request F:\review-case\evidence-query.json `
  --output F:\review-case\evidence-bundle.json
```

`evidence-bundle.json`에는 찾은 근거와 함께 문서 ID, revision ID, 페이지 번호, evidence ID, 페이지 위치(`bbox`), 원본 SHA-256이 들어갑니다. 따라서 결과만 보지 말고 연결된 PDF의 해당 페이지를 함께 확인해야 합니다.

## 7. 필요한 숫자 계산 실행하기

계산은 임의로 계산하지 않고, 등록된 공식 ID와 버전으로만 실행합니다. 요청 파일 예시는 다음과 같습니다.

```json
{
  "formula_id": "FRONTAGE_RATIO",
  "formula_version": "1.0.0",
  "inputs": {
    "frontage_length_m": "30",
    "perimeter_length_m": "320",
    "threshold_ratio": "0.125"
  }
}
```

위 공식과 입력 이름은 저장소에 등록된 예시입니다. 실제 업무에서는 해당 프로젝트에서 승인한 formula ID·버전·입력 이름을 사용해야 합니다.

```powershell
evidence-review math-run `
  --request F:\review-case\calculation-request.json `
  --output F:\review-case\calculation-result.json
```

결과에는 입력값, 치환식, 결과값, 공식 manifest hash, 결과 hash가 기록됩니다. 계산 결과만 복사해 사용하지 말고, 어떤 근거에서 입력값이 나왔는지 함께 확인하세요.

## 8. 사람 검토용 Run 준비하기

검토 요청은 검토 대상(`case_id`), 질문(`question`), 첨부 파일의 역할과 hash를 포함해야 합니다. 실제 PDF의 hash와 파일 크기를 넣어야 하므로 아래 파일은 형식 참고용입니다.

```json
{
  "format": "evidence-review/review-request",
  "version": 1,
  "case_id": "CASE-001",
  "question": "이 기준을 충족하는가?",
  "attachments": [
    {
      "attachment_id": "ATT-001",
      "original_name": "reference.pdf",
      "stored_path": "inputs/original/reference.pdf",
      "sha256": "실제 PDF의 64자리 SHA-256",
      "byte_size": 123456,
      "mime": "application/pdf",
      "role": "REFERENCE_DOCUMENT",
      "role_confirmation": "USER_CONFIRMED",
      "proposed_role": null
    }
  ]
}
```

Windows에서 원본 hash와 파일 크기를 확인하는 예시는 다음과 같습니다.

```powershell
Get-FileHash F:\evidence-review-workspace\inputs\original\reference.pdf -Algorithm SHA256
(Get-Item F:\evidence-review-workspace\inputs\original\reference.pdf).Length
```

검토 Run을 준비합니다.

```powershell
evidence-review review-run prepare `
  --workspace F:\evidence-review-workspace `
  --request F:\review-case\review-request.json
```

준비가 끝나면 Run 폴더에 다음과 같은 파일이 생깁니다.

- `track-a-bundle.json`: 제공된 근거와 계산 결과를 설명할 자료
- `TRACK_A_INSTRUCTIONS.md`: Track A 작성 안내
- `TRACK_B_INSTRUCTIONS.md`: Track B 독립 감사 안내
- `confidence-input.json`: 신뢰도 입력 자료

Track A는 제공된 근거만 설명하고, Track B는 Track A의 주장을 독립적으로 점검합니다. 두 track 모두 사람의 최종 결정을 대신하지 않습니다.

## 9. 최종 검토 packet 만들기

Track A와 Track B 결과 파일이 준비된 뒤 Run을 마무리합니다.

```powershell
evidence-review review-run finalize `
  --workspace F:\evidence-review-workspace `
  --run-id RUN-XXXXXXXXXXXXXXXXXXXX `
  --track-a-output F:\review-case\track-a-output.json `
  --track-b-output F:\review-case\track-b-output.json `
  --publish `
  --open
```

`--open`은 생성된 검토 HTML을 기본 브라우저로 엽니다. 결과 폴더에는 보통 다음 파일이 있습니다.

- `review.html`: 사람이 읽고 확인하는 화면
- `final-review-packet.json`: 최종 검토용 기계 packet

검토자는 다음을 확인해야 합니다.

- PDF의 문서 ID·revision ID·페이지가 실제 원본과 맞는가?
- 인용된 evidence ID와 페이지 위치가 실제 내용과 맞는가?
- 계산 입력과 공식 버전이 맞는가?
- 규칙 결과와 예외·충돌·보류 사유가 빠지지 않았는가?
- `human_decision`이 아직 `null`인가?

`--publish`는 사용할 packet을 선택하는 동작일 뿐, 승인이나 전자서명이 아닙니다.

## 도면 PDF를 사용하는 경우

도면은 글자 검색만으로 안전하게 판단하기 어려울 수 있습니다. 도면에서 추출된 값은 후보로 보관하고, 사람이 원본 도면에서 위치와 의미를 확인한 뒤에만 확정 입력으로 사용할 수 있습니다.

로컬 브라우저 화면을 사용하는 경우 확인 화면과 최종 검토 화면은 분리됩니다.

```text
http://127.0.0.1:<port>/runs/<RUN-ID>/confirmation
http://127.0.0.1:<port>/runs/<RUN-ID>/review
```

확인 전의 도면 후보, 충돌하는 후보, 확인이 필요한 값은 Math Engine이나 Rule Engine 입력으로 사용하지 않습니다.

## 자주 막히는 경우

| 상황 | 확인할 것 |
|---|---|
| `PENDING_PARSER_OUTPUT` | parser 결과 파일이 실제로 있는지, manifest의 `artifact_path`가 맞는지 확인합니다. |
| `UNSUPPORTED_PARSER_KIND` | `parser.kind`가 등록된 종류인지 확인합니다. 다른 종류로 자동 대체되지 않습니다. |
| `BLOCKED` | 명령 출력의 reason code를 읽고 parser, authority, 경로 문제를 수정합니다. |
| `INPUT_CONFIRMATION_REQUIRED` | 도면 후보를 사람이 확인해야 합니다. 확인 전에는 정상적인 대기 상태입니다. |
| output 파일이 이미 있음 | 원본 결과를 덮어쓰지 않도록 새 출력 경로를 사용합니다. |
| hash mismatch | PDF가 바뀌었거나 다른 parser 결과를 연결한 것입니다. 원본을 보존하고 다시 등록합니다. |
| `ABSTAIN` | 근거·입력·규칙이 부족하거나 충돌해 자동으로 결론을 내리지 않은 상태입니다. 사람이 원인을 확인해야 합니다. |

## 안전 원칙

- 원본 PDF와 raw parser 결과를 덮어쓰지 않습니다.
- 파일명만 보고 문서 종류나 법적 효력을 추정하지 않습니다.
- parser 결과가 없는 참고문서의 내용을 임의로 만들어내지 않습니다.
- 확인되지 않은 도면값을 계산·규칙 입력으로 사용하지 않습니다.
- 기계 packet에 사람의 결정을 직접 삽입하지 않습니다.
- 외부 API나 인터넷 검색 결과를 근거로 사용하지 않습니다.

## 고급 작업

처음 사용하는 사람은 위의 기본 흐름만 따라도 됩니다. 다음 작업은 담당 개발자·검토자가 상세 문서를 읽고 진행하세요.

- [Source Batch v2 및 Parser Registry](docs/SOURCE_BATCH_V2.md)
- [검토자 작업 절차](docs/REVIEWER_WORKFLOW.md)
- [Codex 작업 절차](docs/CODEX_WORKFLOW.md)
- [ChatGPT Web 작업 절차](docs/CHATGPT_WEB_WORKFLOW.md)
- [오프라인 실행 경계](docs/OFFLINE_EXECUTION.md)
- [Legacy document lineage migration](docs/LEGACY_LINEAGE_MIGRATION.md)
- [Track A 숫자 문법](docs/TRACK_A_NUMERIC_GRAMMAR.md)

### Legacy database migration

기존 evidence database를 별도 파일로 마이그레이션해야 하는 경우에만 사용합니다. 원본 DB는 수정하지 않습니다.

```powershell
evidence-review evidence migrate-lineage `
  --source 01_database/evidence.sqlite `
  --manifest migration/legacy-lineage-manifest.json `
  --output migrated/evidence.sqlite
```

### 릴리스 검증

릴리스용 process attestation은 일반 사용자 작업이 아닙니다. 정확한 candidate hash와 packet hash를 확인한 named reviewer가 작성해야 합니다.

```powershell
evidence-review release validate-attestation `
  --attestation releases/evidence-review-v1.0/human-attestation.json `
  --candidate-hash <release-candidate-sha256> `
  --packet-hash <final-review-packet-sha256>
```

자세한 릴리스·오프라인·legacy 규칙은 위 문서를 기준으로 합니다.

## 개발자 검증

코드를 수정한 경우 저장소 루트에서 다음 검증을 실행합니다.

```powershell
evidence-review documentation validate `
  --repository-root . `
  --config documentation-integrity.json `
  --output build/documentation-integrity-report.json

pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

## 주의할 상태

최종 packet의 `human_decision`은 사람이 별도 기록하기 전까지 `null`이어야 합니다. `READY_FOR_HUMAN_REVIEW`가 표시되어도 원본 PDF와 모든 인용·계산·예외를 직접 확인한 뒤 별도 사람 결정을 기록해야 합니다.
