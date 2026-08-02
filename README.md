# Evidence Review System

사용자가 제공하는 서로 다른 PDF와 parser artifact를 **출처 추적 가능한 evidence database**로 변환하고, 검색·계산·규칙 실행 결과를 사람이 최종 검토하도록 지원하는 범용 문서 검토 런타임이다.

> 시스템은 적합·부적합을 최종 결정하지 않는다. `READY_FOR_HUMAN_REVIEW`는 사람이 검토할 준비가 됐다는 뜻이며 승인 상태가 아니다.

## 적용 대상

입력 PDF의 파일명, 문서명, 분야, 페이지 수는 매번 달라도 된다.

- 법령·조례·운영기준
- 일반 보고서와 사업계획서
- 표 중심 자료
- 이미지 기반 스캔 PDF
- 건축 도면 PDF
- 사용자가 별도로 제공한 참고 이미지·표

초기 개발에 사용된 안심주택 자료는 테스트 fixture 중 하나일 뿐이다. 신규 처리 로직은 문서명이나 `law-1`, `law-2` 같은 파일명에 의존하지 않는다.

## 핵심 원칙

| 원칙 | 적용 방식 |
|---|---|
| 원본 우선 | PDF 원본 SHA-256, parser artifact hash, page, bbox를 기록한다. |
| 파일명 비종속 | 내부 ID는 명시적 ID 또는 원본 SHA-256으로 생성한다. |
| 명시적 parser binding | parser 종류와 artifact를 source-batch manifest에 선언한다. |
| 결정적 실행 | 동일한 정규화 입력은 동일한 JSON, snapshot hash, Run ID를 만든다. |
| 계산 분리 | 숫자 계산은 등록된 Math Engine 공식으로만 수행한다. |
| 규칙 승인 | 사람이 승인한 버전 규칙만 Rule Engine에서 실행한다. |
| 불확실성 보존 | parser 누락, source 충돌, 확인되지 않은 도면값은 보류 또는 `ABSTAIN` 처리한다. |
| 사람 최종 결정 | 기계 packet의 `human_decision`은 항상 `null`이며 사람 결정은 별도 기록한다. |

## 처리 흐름

```text
사용자 PDF와 parser artifact 등록
→ source-batch prepare로 역할·parser·상태 검증
→ 원본 SHA-256 및 document/revision ID 생성
→ parser-ready reference ingest
→ page_id 기반 문단·표·visual evidence 생성
→ evidence.sqlite 및 FTS index 생성
→ 도면은 별도 drawing backend에서 confirmation 처리
→ 질문별 evidence 검색
→ 필요한 계산·승인 규칙 실행
→ Track A 설명 / Track B 감사
→ review.html 및 final-review-packet.json 생성
→ 사람 최종 검토
```

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

`ansim_review`은 기존 실행 환경과 artifact 호환을 위해 유지되는 내부 Python namespace이다. 신규 사용자-facing 명칭과 JSON format은 `evidence-review`를 사용한다.

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
│  ├─ source-batch.json
│  └─ visual-manifest.json
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
│  └─ manifests\active.json
└─ runs
   ├─ final-review-packet.json
   └─ RUN-XXXXXXXXXXXXXXXXXXXX
```

폴더 이름은 문서 역할, parser 종류, document ID, page ID를 결정하지 않는다. 모든 관계는 manifest와 hash로 명시한다.

## 1. Source batch v2

새 manifest는 version 2로 작성한다.

```json
{
  "format": "evidence-review/source-batch",
  "version": 2,
  "sources": [
    {
      "source_path": "inputs/original/reference-a.pdf",
      "role": "REFERENCE_DOCUMENT",
      "document_id": null,
      "display_title": "사용자 제공 참고 기준",
      "parser": {
        "kind": "OPENDATALOADER_JSON",
        "artifact_path": "inputs/parser/reference-a.json",
        "options": {}
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
| `source_path` | batch root 아래 원본 파일의 안전한 상대경로 |
| `role` | `REFERENCE_DOCUMENT`, `CASE_DRAWING`, `CASE_TABLE`, `SUPPORTING_IMAGE` |
| `document_id` | 선택값. 없으면 원본 SHA-256에서 자동 생성 |
| `display_title` | 표시용 제목. identity 생성에 사용하지 않음 |
| `parser.kind` | registry에 등록된 대문자 machine identifier |
| `parser.artifact_path` | source에 연결된 parser artifact 상대경로 |
| `parser.options` | adapter 전용 명시적 옵션 object |

Version 1 manifest는 기존 `OPENDATALOADER_JSON` 입력을 읽기 위해서만 지원한다. Decoder는 v1을 내부 v2 모델로 변환하며, writer는 항상 v2를 출력한다.

## 2. DB 생성 전 상태 확인

```powershell
evidence-review source-batch prepare `
  --root F:\evidence-review-workspace `
  --manifest F:\evidence-review-workspace\manifests\source-batch.json
```

이 명령은 DB를 만들지 않고 source별 상태와 reason code를 출력한다.

| 상태 | 의미 |
|---|---|
| `PENDING_PARSER_OUTPUT` | reference/table에 parser artifact가 없음 |
| `PENDING_REFERENCE_INGESTION` | 등록된 parser가 준비돼 reference ingest 가능 |
| `PENDING_DRAWING_INGESTION` | drawing backend로 전달해야 함 |
| `INPUT_CONFIRMATION_REQUIRED` | 도면 candidate에 reviewer confirmation이 필요함 |
| `READY_TO_EVALUATE` | ingest와 필요한 확인이 완료돼 평가 가능 |
| `BLOCKED` | unsupported parser 또는 authority 제한으로 진행 불가 |
| `FAILED` | source 구성이나 무결성 검증 실패 |

등록되지 않은 parser kind는 자동 fallback하지 않고 `BLOCKED`와 `UNSUPPORTED_PARSER_KIND`를 반환한다.

## 3. Evidence DB 생성

```powershell
evidence-review source-batch ingest `
  --root F:\evidence-review-workspace `
  --manifest F:\evidence-review-workspace\manifests\source-batch.json `
  --output F:\evidence-review-workspace\evidence\evidence.sqlite
```

Importer는 parser-ready `REFERENCE_DOCUMENT`와 `CASE_TABLE`만 DB에 기록한다. Parserless drawing은 valid reference ingest를 막지 않지만 reference DB에는 들어가지 않는다.

다음 경우 output DB를 만들지 않는다.

- reference/table parser output 누락
- unsupported parser kind
- parser metadata와 source PDF 불일치
- source 또는 parser artifact hash 변경
- parser-ready reference evidence가 하나도 없음

성공 결과에는 document ID, revision ID, source SHA-256, snapshot hash, record counts, source별 상태가 포함된다.

### ID 정책

- 명시적 `document_id`가 있으면 path-safe machine ID 문법을 검증한다.
- 없으면 `DOC-<원본 SHA-256 앞 20자리>`를 사용한다.
- 동일 bytes와 다른 파일명은 같은 자동 document ID로 dedupe한다.
- 같은 파일명이라도 bytes가 다르면 다른 자동 document ID가 된다.
- 같은 명시적 document ID에 서로 다른 bytes를 연결할 수 없다.
- page ID는 importer가 `<revision_id>-P<4자리 page number>`로 생성한다.
- parser adapter는 document, revision, page ID를 생성하지 않는다.

## 4. Parser registry

기본 registry는 `OPENDATALOADER_JSON` adapter를 등록한다. 다른 parser는 `ParserAdapter`를 구현하고 registry에 명시적으로 등록한다.

Registry는 다음을 보장한다.

- case-sensitive kind
- duplicate kind 거부
- unknown kind fallback 금지
- 안정적으로 정렬된 kind 목록
- adapter 예외를 성공으로 변환하지 않음
- module-level mutable singleton 미사용

Adapter의 normalized contribution에는 page dimensions와 page-relative element, table, visual record만 포함된다. Page 연속성, bbox 범위, parser artifact hash는 ingest 전에 검증한다.

## 5. Visual manifest

Visual identity는 파일명에서 추론하지 않는다.

```json
{
  "format": "evidence-review/visual-manifest",
  "version": 1,
  "records": [
    {
      "id": "VISUAL-001",
      "document_id": "DOC-001",
      "revision_id": "DOC-001-abcdef123456",
      "page_id": "DOC-001-abcdef123456-P0001",
      "kind": "page_render",
      "path": "visuals/page-1.png",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "bbox": null,
      "source_evidence_ids": []
    }
  ]
}
```

Loader는 `document_id`, `revision_id`, `page_id`를 필수로 요구한다. DB binding 시 `pages → revisions → documents` join으로 관계를 재검증한다. 같은 image bytes가 여러 페이지에 있어도 visual ID와 page identity는 각각 유지한다.

## 6. Evidence 검색

```powershell
evidence-review query `
  --db F:\evidence-review-workspace\evidence\evidence.sqlite `
  --request F:\review-case\evidence-query.json `
  --output F:\review-case\evidence-bundle.json
```

검색 결과는 document ID, revision ID, page, evidence ID, bbox, source SHA-256을 포함한다.

## 7. 결정적 계산

```powershell
evidence-review math-run `
  --request F:\review-case\calculation-request.json `
  --output F:\review-case\calculation-result.json
```

계산은 등록된 formula ID와 version으로만 실행한다. 결과에는 입력, 치환식, raw/display result, formula manifest hash, result hash가 기록된다.

## 8. 검토 Run

```powershell
evidence-review review-run prepare `
  --workspace F:\evidence-review-workspace `
  --request F:\review-case\review-request.json
```

Prepared run의 다음 파일을 사용한다.

- `track-a-bundle.json`
- `TRACK_A_INSTRUCTIONS.md`
- `TRACK_B_INSTRUCTIONS.md`
- `confidence-input.json`

Track A는 제공된 evidence·calculation·rule result만 설명한다. Track B는 Track A claim을 독립적으로 감사한다. 두 track 모두 사람 결정, confidence, drawing confirmation을 만들 수 없다.

Finalization:

```powershell
evidence-review review-run finalize `
  --workspace F:\evidence-review-workspace `
  --run-id RUN-XXXXXXXXXXXXXXXXXXXX `
  --track-a-output F:\review-case\track-a-output.json `
  --track-b-output F:\review-case\track-b-output.json `
  --publish
```

`--publish`는 release builder가 사용할 packet을 선택할 뿐, 승인이나 전자서명을 의미하지 않는다.

## 9. 릴리스 Process Attestation

릴리스 승인은 공개키 전자서명이 아니라 내부 절차용 `PROCESS_ATTESTATION` 모델을 사용한다. Named reviewer는 정확한 release candidate hash와 packet hash를 확인한 뒤 다음 canonical 기록을 append-only로 생성한다.

```text
releases/evidence-review-v1.0/human-attestation.json
```

Attestation 계약의 핵심값:

```json
{
  "format": "evidence-review/human-attestation",
  "version": 1,
  "assurance_level": "PROCESS_ATTESTATION",
  "attestation": "REVIEWED_AND_ACCEPTED_FOR_RELEASE"
}
```

Release manifest는 검증 범위를 별도 필드로 명시한다.

```json
{
  "attestation_assurance": "PROCESS_ATTESTATION",
  "cryptographic_identity_verified": false
}
```

실제 attestation에는 reviewer ID, timezone 포함 검토 시각, release candidate hash, packet hash와 모든 필수 checklist evidence가 포함되어야 한다. 현재 release policy에 expected reviewer ID가 설정된 경우 exact string mismatch는 실패한다.

검증 명령:

```powershell
evidence-review release validate-attestation `
  --attestation releases/evidence-review-v1.0/human-attestation.json `
  --candidate-hash <release-candidate-sha256> `
  --packet-hash <final-review-packet-sha256>
```

JSON 기록 보유 자체는 reviewer identity의 암호학적 증명이 아니다. 시스템은 공개키, 인증서 또는 계정 세션을 검증하지 않으며 release manifest의 `cryptographic_identity_verified`는 항상 `false`다. Attestation 누락, 형식 오류, reviewer policy 불일치, 오래된 candidate hash 또는 packet hash 불일치가 있으면 release는 `BLOCKED`로 유지된다.

## 10. 최종 릴리스 ZIP 재검증

Release builder는 process attestation을 검증하기 전에 최종 `codex-workspace.zip`과 `chatgpt-web-runtime.zip`을 다시 연다. `codex-workspace.zip`의 `bundle-manifest.json`과 `chatgpt-web-runtime.zip`의 `runtime-manifest.json`을 실제 member bytes와 비교한다.

검증은 **without extracting** 방식으로 수행된다. 각 고유 `ZipInfo`를 직접 읽으며 다음 항목을 확인한다.

- 최종 출력 디렉터리의 필수 파일 누락과 예상하지 않은 파일
- manifest와 실제 ZIP member의 누락·추가·중복
- 절대경로, `.`·`..`, 빈 경로 요소, 역슬래시, drive-prefixed 경로
- Windows에서 충돌하는 case-fold collisions
- manifest의 size와 실제 byte 수
- manifest의 SHA-256과 실제 member hash

결과는 `release-validation.json`의 `release_output`에 기록된다. 하나라도 불일치하면 `RELEASE_OUTPUT_VALIDATION_FAILED`가 추가되고, process attestation이 있더라도 release는 `BLOCKED` 상태를 유지한다.

## 11. Legacy document lineage migration

동일 PDF가 legacy document ID와 canonical document ID로 중복 등록된 evidence schema v2 database는 사람이 검토한 manifest를 사용해 copy-on-write로 정리한다.

```powershell
evidence-review evidence migrate-lineage `
  --source 01_database/evidence.sqlite `
  --manifest migration/legacy-lineage-manifest.json `
  --output migrated/evidence.sqlite
```

`evidence migrate-lineage`는 source database hash, 명시적 revision mapping, page geometry, evidence payload, link, review flag와 retrieval counterpart가 모두 일치할 때만 legacy duplicate graph를 제거한다. 어떤 unresolved 항목도 부분 적용하지 않으며 원본 database를 수정하지 않는다.

상세 manifest 계약, output artifact, 종료 코드와 사후 검증 절차는 [LEGACY_LINEAGE_MIGRATION.md](docs/LEGACY_LINEAGE_MIGRATION.md)를 따른다. Alias registry는 historical lookup metadata일 뿐 신규 source-batch 또는 visual identity authority가 아니다.

## 안전 경계

- PDF 파일명이나 제목으로 문서 종류를 추정하지 않는다.
- parser artifact가 없는 reference 내용을 만들어내지 않는다.
- unknown parser를 다른 parser로 자동 처리하지 않는다.
- parser adapter가 DB identity를 소유하지 않는다.
- visual identity를 파일명이나 폴더명에서 추론하지 않는다.
- parserless drawing을 자동 evidence로 취급하지 않는다.
- 확인되지 않은 도면값을 Math/Rule Engine 입력으로 사용하지 않는다.
- Track A가 새 숫자를 계산하거나 표기를 임의 정규화하지 않는다.
- 사람의 결정은 기계 packet과 분리한다.

## Legacy 호환

다음은 기존 workspace와 artifact 이행을 위해서만 유지한다.

- 내부 Python namespace `ansim_review`
- 이전 CLI 별칭 `ansim-review`
- source-batch version 1 reader
- `ansim/*` 기존 review-run format
- 번호 폴더 기반 legacy migration adapter
- 기존 `ansim-v1.0` release artifact와 `ansim/human-acceptance` inspection reader

Legacy acceptance는 이력 확인에만 사용하며 신규 릴리스를 승인할 수 없다. 신규 프로젝트는 위 legacy 구조를 기본 입력 방식으로 사용하지 않는다.

## 개발 검증

```powershell
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

## 상세 문서

- [Source Batch v2 및 Parser Registry](docs/SOURCE_BATCH_V2.md)
- [Codex 작업 절차](docs/CODEX_WORKFLOW.md)
- [ChatGPT Web 작업 절차](docs/CHATGPT_WEB_WORKFLOW.md)
- [검토자 작업 절차](docs/REVIEWER_WORKFLOW.md)
- [오프라인 실행 경계](docs/OFFLINE_EXECUTION.md)
- [Legacy document lineage migration](docs/LEGACY_LINEAGE_MIGRATION.md)
- [Track A 숫자 문법](docs/TRACK_A_NUMERIC_GRAMMAR.md)
- [범용 PDF 및 hardening 설계](docs/superpowers/specs/2026-08-02-generic-pdf-and-hardening-design.md)
