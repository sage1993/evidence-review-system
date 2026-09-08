---
name: ers-pdf
description: Use when a user invokes $ERS_PDF or asks Codex Desktop to prepare REFERENCE_DOCUMENT PDFs as searchable Evidence Review System evidence corpus. Do not use for case drawings that the user wants visually inspected.
---

# ERS PDF Parsing

## 목적

`$ERS_PDF`는 **REFERENCE_DOCUMENT 역할의 PDF**를 Evidence Review System의 검색 가능한 evidence corpus로 준비한다. 법령·조례·지침·보고서·기준서처럼 이후 retrieval과 citation에 사용할 문서가 대상이다. 이 단계는 규제 결론을 만들지 않는다.

PDF 확장자는 Skill 선택 기준이 아니다. 사용 목적이 우선한다.

| 요청 | 이 Skill 사용 여부 |
|---|---|
| `이 법령 PDF를 근거자료로 등록해` | 사용 |
| `이 보고서를 ERS 검색 근거로 준비해` | 사용 |
| `이 PDF 도면을 보고 출입구를 검토해` | 사용하지 않음 |
| `이 평면도 PDF에서 문제가 있는 부분을 찾아줘` | 사용하지 않음 |
| `이 PNG/사진을 보고 판단해` | 사용하지 않음 |

사용자가 PDF 자체의 도면·배치·형상·위치·치수·시설 상태를 **보고 판단**해 달라고 한 경우 해당 파일은 `CASE_DRAWING` 또는 `SUPPORTING_IMAGE`이고 `$ERS_REVIEW`의 case-visual 경로로 넘긴다.

## 기본 parser

REFERENCE_DOCUMENT PDF의 기본 parser는 `opendataloader-pdf`(OpenDataLoader PDF)다. parser 실행과 parser artifact 보존은 ERS deterministic source binding보다 선행한다.

## 필수 절차

1. 사용자가 명시적으로 제공하거나 지정한 **REFERENCE_DOCUMENT PDF만** 사용한다. 저장소 샘플을 임의 선택하지 않는다.
2. 파일의 역할이 불명확하면 PDF라는 이유로 parser를 실행하지 않는다. 요청 목적에서 `REFERENCE_DOCUMENT`인지 `CASE_DRAWING`/`SUPPORTING_IMAGE`인지 먼저 결정한다.
3. 원본 PDF를 별도 source 경로에 보존하고 SHA-256, byte size, page count, document identity를 기록한다.
4. immutable parser artifact가 있으면 source/hash binding을 검증한다. 없으면 OpenDataLoader PDF를 새 output directory에 실행한다. parser가 없으면 중단한다.
5. `parser-run.json`, raw JSON, Markdown, 추출 이미지, 로그, parser version/configuration, source hash를 함께 보존하며 덮어쓰지 않는다.
6. two-run reproducibility와 parser warning 수집을 fresh output으로 수행한다. mismatch나 parser failure를 성공으로 바꾸지 않는다.
7. source-batch v2 manifest의 `REFERENCE_DOCUMENT` 항목에 parser-time source SHA-256을 기록한다.

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

8. source routing과 ingest를 실행한다.

```powershell
evidence-review source-batch prepare `
  --root <workspace> `
  --manifest <workspace>\manifests\source-batch.json

evidence-review source-batch ingest `
  --root <workspace> `
  --manifest <workspace>\manifests\source-batch.json `
  --output <workspace>\evidence\evidence.sqlite
```

Ingest owns corpus finalization. Before the writer closes and the database is
published, the runtime materializes clauses, structural links, legal-reference
links, and the final retrieval projection, then verifies the final logical
snapshot hash and SQLite integrity:

```text
source-batch ingest
→ deterministic finalization
→ final logical hash/index verification
→ writer close
→ create-only publish
→ exact closed-file SHA-256
```

Do not run or document a review-time clause/index repair step. A legacy or
unfinalized workspace must be re-prepared through `$ERS_PDF`; `$ERS_REVIEW`
must fail closed without changing its database.

9. final Review Workspace의 normative citation viewer가 같은 PDF page를 다시 렌더하지 않도록 각 revision의 verified page-image cache를 한 번 준비한다.

```text
<workspace>/page-images/<REVISION-ID>/page-0001.png
<workspace>/page-images/<REVISION-ID>/page-0001.json
...
```

page metadata는 source hash, page number, PDF geometry, image SHA-256을 검증해야 한다. publish는 revision 단위로 원자적이어야 한다.

10. 다음 조건을 만족할 때만 REFERENCE_DOCUMENT corpus 준비 완료로 보고한다.

- parser-ready reference evidence ingest 성공
- `<workspace>/evidence/evidence.sqlite` 존재
- evidence database가 `lifecycle_state=FINALIZED`, `finalization_version=1`이며
  logical snapshot hash와 retrieval index hash가 일치
- finalization 후 writer가 닫힌 뒤 계산한 `evidence.sqlite` 파일 SHA-256 기록
- 필요한 revision page-image cache 검증 가능
- source state가 `READY_TO_EVALUATE`

`PENDING_PARSER_OUTPUT`, `BLOCKED`, `FAILED`는 그대로 보존한다.

11. 위 준비 조건이 모두 충족된 뒤에만 이번 `$ERS_PDF` 결과 workspace를 다음 `$ERS_REVIEW`의 active workspace로 bind한다.

```powershell
evidence-review workspace bind `
  --repository-root . `
  --workspace <workspace>
```

binding은 저장소 로컬 제어 상태 `.ers/active-workspace.json`에 exact absolute workspace path, logical evidence snapshot identity, 그리고 닫힌 finalized `evidence.sqlite`의 exact file SHA-256을 기록한다. logical snapshot hash는 canonical evidence rows의 identity이고 file SHA-256은 bind된 물리 artifact의 identity다. 같은 logical hash를 가진 별도 rebuild가 같은 SQLite bytes를 보장하지는 않지만, 한 번 bind된 artifact의 file SHA-256은 review lifecycle 전체에서 변하지 않아야 한다. 원본 PDF, parser artifact, evidence DB 자체를 변경하지 않는다. 새로 준비 완료된 workspace를 bind하면 이 로컬 pointer만 교체되고 기존 workspace 산출물은 보존된다.

`workspace bind`가 실패하면 `$ERS_REVIEW` handoff 준비가 완료되었다고 보고하지 않는다. 준비가 완료되지 않은 workspace를 active workspace로 bind하지 않는다.

## CASE visual PDF와의 경계

`CASE_DRAWING` PDF에는 다음 작업을 수행하지 않는다.

- OpenDataLoader reference parsing
- reference source-batch ingest
- reference parser two-run reproducibility를 visual review 선행조건으로 요구
- `PARSER_SOURCE_PDF_INVALID`를 case visual 판단 실패 사유로 사용

CASE visual PDF는 원본 bytes를 immutable drawing source로 보존하고 필요한 page를 렌더한 뒤 visual-analysis handoff로 넘긴다. 해당 절차는 `$ERS_REVIEW`가 소유한다.

## 사용자에게 반환할 내용

REFERENCE_DOCUMENT에 대해서만 다음을 반환한다.

- 보존된 원본 PDF와 workspace 위치
- parser/source 상태와 warnings
- searchable evidence 준비 여부 또는 정확한 blocking reason
- page-image cache 준비 여부
- active workspace binding 성공 여부
- 준비와 binding 완료 시 다음 입력: `$ERS_REVIEW <질문>`

## 금지

- PDF 확장자만으로 이 Skill 활성화
- 사용자가 `보고 판단`하라고 준 도면 PDF를 REFERENCE_DOCUMENT로 재분류
- CASE_DRAWING/SUPPORTING_IMAGE를 OpenDataLoader reference parser에 전달
- 원본 PDF 또는 raw parser output 덮어쓰기
- filename/title에서 role, authority, date, identity 추정
- parser-time source hash 대신 다른 hash 사용
- 누락 text/table/bbox/parser metadata 생성
- invalid/missing page image를 정상 cache로 게시
- Review Workspace를 열 때마다 reference PDF page image 재렌더
- 준비가 완료되지 않은 workspace를 active workspace로 bind

## Handoff

REFERENCE_DOCUMENT 준비와 active workspace binding이 성공하면 정식 질문은 `$ERS_REVIEW`로 넘긴다. `$ERS_PDF` 단계에서 QuestionPlan 이후의 Track A/B, Visual Analysis, 규제 결론을 만들지 않는다.
