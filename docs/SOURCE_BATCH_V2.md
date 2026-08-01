# Source Batch v2 and Parser Registry

## 목적

`evidence-review/source-batch` version 2는 사용자가 제공하는 임의 PDF와 parser artifact를 파일명 추론 없이 연결한다. Manifest는 source 역할과 parser binding만 선언하며, 실제 parser 지원 여부는 deterministic registry가 판정한다.

## Canonical manifest

새로 작성하는 manifest는 항상 version 2를 사용한다.

```json
{
  "format": "evidence-review/source-batch",
  "version": 2,
  "sources": [
    {
      "source_path": "inputs/original/reference.pdf",
      "role": "REFERENCE_DOCUMENT",
      "document_id": null,
      "display_title": "검토 기준",
      "parser": {
        "kind": "OPENDATALOADER_JSON",
        "artifact_path": "inputs/parser/reference.json",
        "options": {}
      }
    },
    {
      "source_path": "inputs/original/drawing.pdf",
      "role": "CASE_DRAWING",
      "document_id": "DRAWING-001",
      "display_title": "사업 도면",
      "parser": null
    }
  ]
}
```

`source_path`와 `artifact_path`는 batch root 아래의 안전한 POSIX 상대경로여야 한다. 절대경로, `..`, Windows drive prefix, backslash는 거부한다.

## Version 1 compatibility

Version 1은 기존 `OPENDATALOADER_JSON` manifest를 읽기 위한 compatibility input이다.

- version 1 parser kind는 `OPENDATALOADER_JSON`만 허용한다.
- version 1에는 parser `options`가 없다.
- decoder는 version 1을 내부 version 2 model로 변환한다.
- canonical writer는 version 1을 다시 쓰지 않고 항상 version 2를 출력한다.

## Parser registry

Parser kind는 다음 machine identifier 문법을 사용한다.

```text
^[A-Z][A-Z0-9_]{0,63}$
```

Registry 특성:

- case-sensitive
- duplicate kind 거부
- unknown kind 자동 fallback 없음
- 등록 kind 출력은 정렬됨
- adapter 예외를 성공 상태로 변환하지 않음
- module-level mutable singleton 없음

기본 registry는 `OPENDATALOADER_JSON` adapter를 등록한다. 다른 parser를 지원하려면 `ParserAdapter`를 구현하고 명시적으로 registry에 등록해야 한다.

## Normalized parser contribution

Adapter는 DB identity를 생성하지 않는다. 다음 source-relative record만 반환한다.

- page number와 page dimensions
- page-relative element records
- page-relative table records
- page-relative visual records
- parser artifact SHA-256
- 선택적 display title

Importer가 source SHA-256에서 document·revision identity를 만들고 다음 page ID를 파생한다.

```text
<revision_id>-P<page_number:04d>
```

Contribution 불변식:

- page number는 1부터 연속이어야 함
- dimensions는 유한한 양수여야 함
- record가 선언되지 않은 page를 참조할 수 없음
- bbox는 page 경계 안에 있어야 함
- parser artifact hash는 lowercase SHA-256이어야 함
- 같은 kind 안에서 record key가 중복될 수 없음

## Source states

```text
RECEIVED
CLASSIFYING_INPUTS
PENDING_PARSER_OUTPUT
PENDING_REFERENCE_INGESTION
PENDING_DRAWING_INGESTION
INPUT_CONFIRMATION_REQUIRED
READY_TO_EVALUATE
BLOCKED
FAILED
```

주요 매핑:

| 조건 | 상태 |
|---|---|
| reference/table + parser 없음 | `PENDING_PARSER_OUTPUT` |
| reference/table + 등록 parser 준비 | `PENDING_REFERENCE_INGESTION` |
| reference ingest 완료 | `READY_TO_EVALUATE` |
| 등록되지 않은 parser kind | `BLOCKED` + `UNSUPPORTED_PARSER_KIND` |
| drawing source | `PENDING_DRAWING_INGESTION` |
| drawing 확인 필요 | `INPUT_CONFIRMATION_REQUIRED` |
| supporting image 단독 rule authority 시도 | `BLOCKED` + `SUPPORTING_EVIDENCE_ONLY` |
| 잘못된 source 구성 | `FAILED` |

`prepare`는 DB를 만들지 않고 위 상태를 출력한다.

```powershell
evidence-review source-batch prepare `
  --root F:\workspace `
  --manifest F:\workspace\manifests\source-batch.json
```

`ingest`는 parser-ready reference/table source만 DB에 기록한다.

```powershell
evidence-review source-batch ingest `
  --root F:\workspace `
  --manifest F:\workspace\manifests\source-batch.json `
  --output F:\workspace\evidence\evidence.sqlite
```

다음 조건에서는 output DB를 만들지 않는다.

- reference/table parser output 누락
- unsupported parser kind
- parser/source identity 불일치
- source batch에 parser-ready reference evidence가 없음

Parserless drawing은 valid reference ingest를 막지 않지만 reference DB에도 기록되지 않는다.

## Visual identity

Visual manifest는 다음 identity를 각 record에 직접 선언한다.

```json
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
```

Loader는 filename, parent folder, manifest filename에서 document 또는 page identity를 추론하지 않는다. DB binding 시 `pages -> revisions -> documents` join으로 세 identity가 동일 관계인지 확인한다.

동일한 image bytes가 여러 page에서 사용되면 SHA-256 기반 `duplicate_group`은 같을 수 있지만 visual ID와 page identity는 각각 유지된다.
