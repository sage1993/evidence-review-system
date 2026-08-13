---
name: ers-pdf
description: Use when a user invokes $ERS_PDF or asks Codex Desktop to prepare PDFs for Evidence Review System formal review.
---

# ERS PDF Parsing

## 목적

`$ERS_PDF`는 사용자가 제공한 PDF를 Evidence Review System의 정식 질문 파이프라인에서 사용할 수 있도록 준비한다. 이 단계는 규제 결론을 만들지 않는다.

## 필수 절차

1. 사용자가 명시적으로 제공하거나 지정한 PDF만 사용한다. 저장소 샘플을 임의로 선택하지 않는다.
2. 원본 PDF를 별도 source 경로에 보존하고 SHA-256, byte size, page count, document identity를 기록한다.
3. immutable parser artifact가 있으면 source와 hash binding을 검증한다. 없으면 OpenDataLoader PDF를 새 output directory에 실행한다. parser가 없으면 중단한다.
4. `parser-run.json`, raw JSON, Markdown, 추출 이미지, 로그, parser version/configuration, source hash를 함께 보존하며 덮어쓰지 않는다.
5. two-run reproducibility와 parser warning 수집을 fresh output으로 수행한다. mismatch나 parser failure를 성공으로 바꾸지 않는다.
6. source-batch v2 manifest를 만들고 각 `OPENDATALOADER_JSON` 항목의 `parser.options.source_sha256`에 **그 parser artifact를 실제로 만든 PDF bytes의 SHA-256**을 기록한다. 알 수 없는 값은 추정하지 않는다.

```json
{
  "source_path": "inputs/reference.pdf",
  "role": "REFERENCE_DOCUMENT",
  "parser": {
    "kind": "OPENDATALOADER_JSON",
    "artifact_path": "parser/reference.json",
    "options": {
      "source_sha256": "<parser-time-source-sha256>"
    }
  }
}
```

7. source routing과 ingest를 실행한다.

```powershell
evidence-review source-batch prepare `
  --root <workspace> `
  --manifest <workspace>\manifests\source-batch.json

evidence-review source-batch ingest `
  --root <workspace> `
  --manifest <workspace>\manifests\source-batch.json `
  --output <workspace>\evidence\evidence.sqlite
```

8. final Review Workspace가 인용 페이지를 다시 렌더하지 않도록, 각 revision의 verified page image cache를 **한 번만** 준비·게시한다. canonical 위치는 다음과 같다.

```text
<workspace>/page-images/<REVISION-ID>/page-0001.png
<workspace>/page-images/<REVISION-ID>/page-0001.json
...
```

page metadata는 source hash, page number, PDF geometry, image SHA-256을 원본과 검증해야 한다. publish는 revision 단위로 원자적이어야 하며 실패한 다중 source 작업이 이미 유효한 공유 cache를 삭제하면 안 된다. Review HTML은 이 cache를 검증해서 사용하며 질문마다 같은 PDF page image를 다시 생성하지 않는다.

9. 다음 조건을 모두 만족할 때만 질문 준비 완료로 보고한다.

- parser-ready reference/table evidence ingest 성공
- `<workspace>/evidence/evidence.sqlite` 존재
- 필요한 revision page image cache가 검증 가능
- source state가 `READY_TO_EVALUATE`

`PENDING_PARSER_OUTPUT`, `PENDING_DRAWING_INGESTION`, `INPUT_CONFIRMATION_REQUIRED`, `BLOCKED`, `FAILED`는 그대로 보존한다.

## 사용자에게 반환할 내용

- 보존된 원본 PDF와 workspace 위치
- parser/source 상태와 warnings
- searchable evidence 준비 여부 또는 정확한 blocking reason
- page image cache 준비 여부
- 준비가 완료된 경우 다음 입력: `$ERS_REVIEW <질문>`

도면 전용 PDF는 확인되지 않은 값을 reference evidence나 Math/Rule input으로 취급하지 않는다. 필요한 drawing confirmation이 끝날 때까지 질문 평가 준비 완료라고 표현하지 않는다.

## 금지

- 원본 PDF 또는 raw parser output 덮어쓰기
- filename/title에서 role, authority, date, identity 추정
- parser-time source hash 대신 다른 PDF hash 사용
- 누락 text/table/bbox/parser metadata 생성
- unconfirmed drawing candidate를 계산·규칙 입력으로 사용
- invalid/missing page image를 정상 cache로 게시
- Review Workspace를 열 때마다 PDF page image 재렌더

## Handoff

PDF 준비가 성공하면 정식 질문은 반드시 `$ERS_REVIEW`로 넘긴다. `$ERS_PDF` 단계에서 Track A/B 또는 규제 결론을 만들지 않는다.
