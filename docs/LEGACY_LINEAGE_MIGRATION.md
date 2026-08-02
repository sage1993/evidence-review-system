# Legacy Document Lineage Migration

## 목적

이 절차는 동일한 원본 PDF가 legacy document ID와 canonical document ID로 중복 등록된 evidence database를 정리한다. 대표 사례는 legacy `LAW3`와 canonical `DOC-ACFD68E34043268C`가 동일 source를 가리키는 경우다.

Migration은 사람 검토를 거친 `evidence-review/legacy-lineage-manifest` version 1만 권위 입력으로 사용한다. 파일명, 폴더명, ID 접두어, 문서 제목, 행 순서 또는 revision 개수로 alias를 추론하지 않는다.

이 기능은 evidence **schema version 2** database만 대상으로 하는 **copy-on-write** migration이다. 원본 Grist, CSV, PDF, parser output과 source evidence database를 직접 수정하지 않는다.

## 보증 범위

Migration이 성공하면 다음을 보증한다.

- 실행 전 manifest의 `source_database_sha256`과 실제 **source SHA-256**이 일치한다.
- legacy와 canonical revision의 source hash, byte size, page count가 일치한다.
- page number와 page geometry가 정확히 일치한다.
- element, clause, table, visual payload가 graph-equivalent하다.
- link, review flag, retrieval record에 canonical counterpart가 존재한다.
- legacy duplicate graph만 제거되고 canonical graph는 유지된다.
- 출력 database가 `PRAGMA integrity_check`에서 `ok`를 반환한다.
- 출력 database의 `PRAGMA foreign_key_check` 결과가 비어 있다.
- **source database remains byte-identical** before and after execution.
- output database, alias registry와 report는 모두 **create-only**로 생성된다.

이 manifest는 검토자 이름과 timestamp를 기록하지만 **does not cryptographically verify reviewer identity**. 별도의 서명이나 조직 계정 인증을 제공하지 않는다.

## 비보증 및 차단 경계

다음 상황은 모두 `BLOCKED`로 처리하며 부분 migration을 수행하지 않는다.

- manifest 누락, unknown field 또는 잘못된 hash
- source database hash mismatch
- schema version 2가 아니거나 알 수 없는 user table이 존재함
- legacy 또는 canonical document/revision 누락
- revision ownership 또는 source hash 불일치
- page set 또는 geometry 불일치
- evidence counterpart 누락·중복·모호성
- link, review flag 또는 retrieval counterpart 누락
- source가 실행 중 변경됨
- output verification 실패

Legacy clause가 `REVIEWED`이고 canonical counterpart의 상태나 normalized text가 다르면 **reviewed-value conflict**로 차단한다. 이 migration은 canonical row를 자동으로 `REVIEWED`로 승격하거나 사람 검토값을 암묵적으로 덮어쓰지 않는다.

## Grist 보존 경계

Evidence schema version 2에는 Grist 내부 attachment/comment table이 없다. 따라서 이 migration은 **Grist attachment** 또는 Grist comment row를 변환하거나 삭제하지 않는다.

- 원본 `.grist` 파일과 attachment/file metadata는 Issue #38 acceptance artifact의 hash-bound evidence로 보존한다.
- Grist 내부 row 보존을 이 migration report가 주장하지 않는다.
- legacy visual inspection과 document lineage migration은 별도 경계다.
- document lineage migration은 legacy visual CSV를 canonical visual manifest로 변환하지 않는다.

## Manifest 준비

예제 파일:

`docs/examples/legacy-lineage-manifest.example.json`

이 예제는 `EXAMPLE_ONLY_NOT_REVIEWED`와 빈 `mappings`를 포함하므로 실행 가능한 acceptance authority가 아니다. 실제 실행 전 다음 값을 사람이 검토해 채워야 한다.

1. 원본 evidence database의 lowercase SHA-256
2. 검토자 ID와 timezone이 포함된 검토시각
3. legacy document ID
4. canonical document ID
5. 두 revision이 공유하는 immutable PDF source SHA-256
6. legacy revision ID와 canonical revision ID의 명시적 mapping
7. mapping reason

예시 구조:

```json
{
  "format": "evidence-review/legacy-lineage-manifest",
  "version": 1,
  "source_database_sha256": "<64 lowercase hex>",
  "reviewer_id": "ksh",
  "reviewed_at": "2026-08-02T16:49:00+09:00",
  "mappings": [
    {
      "legacy_document_id": "LAW3",
      "canonical_document_id": "DOC-ACFD68E34043268C",
      "source_sha256": "<64 lowercase hex>",
      "reason": "same immutable PDF registered under a legacy alias",
      "revision_mappings": [
        {
          "legacy_revision_id": "REV-LAW3-001",
          "canonical_revision_id": "REV-DOC-001"
        }
      ]
    }
  ]
}
```

## 실행

PowerShell:

```powershell
evidence-review evidence migrate-lineage `
  --source 01_database/evidence.sqlite `
  --manifest migration/legacy-lineage-manifest.json `
  --output migrated/evidence.sqlite
```

`evidence migrate-lineage`는 다음 순서로 동작한다.

1. manifest와 source database hash 검증
2. source를 read-only와 `PRAGMA query_only = ON`으로 열기
3. integrity, foreign key와 exact schema v2 검증
4. 전체 lineage graph plan 생성
5. unresolved가 있으면 copy 전에 중단
6. source bytes를 private temporary output으로 복사
7. transaction에서 검증된 legacy duplicate row만 child-to-parent 순서로 제거
8. canonical counterpart와 logical digest 재검증
9. source database 재해시
10. database와 두 JSON artifact를 함께 publish

## 산출물

`--output migrated/evidence.sqlite`를 지정하면 다음 세 파일이 생성된다.

- `migrated/evidence.sqlite`
- `migrated/evidence.sqlite.legacy-lineage-aliases.json`
- `migrated/evidence.sqlite.legacy-lineage-migration-report.json`

Alias registry의 format은 `evidence-review/legacy-lineage-aliases`다. `legacy-lineage-aliases.json`은 과거 ID를 canonical ID에 연결하는 historical lookup metadata이며 신규 source-batch identity authority가 아니다.

Migration report의 format은 `evidence-review/legacy-lineage-migration-report`다. `legacy-lineage-migration-report.json`에는 before/after count, source/output hash, manifest hash, logical lineage digest, removed legacy IDs, preserved canonical IDs와 integrity 결과가 기록된다.

기존 final 또는 temporary output이 하나라도 있으면 덮어쓰지 않는다.

## 종료 코드

- **Exit code 0**: migration과 모든 output verification 성공
- **Exit code 1**: final 또는 temporary output path가 이미 존재함
- **Exit code 2**: invalid manifest, hash mismatch, `BLOCKED` plan, schema/integrity 오류 또는 I/O 실패

성공 시 stdout은 `evidence-review/legacy-lineage-migration-status` canonical JSON을 출력한다.

## 사후 검증

CLI stdout의 `status`가 `MIGRATED`인지 확인한다. 이어서 SQLite에서 다음을 실행한다.

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;
SELECT id FROM documents ORDER BY id;
SELECT id, document_id, source_hash FROM revisions ORDER BY id;
```

기대 결과:

- `PRAGMA integrity_check` → `ok`
- `PRAGMA foreign_key_check` → 0 rows
- 선언한 legacy document/revision ID는 없음
- 선언한 canonical document/revision ID는 유지됨
- report의 source hash가 실행 전 source hash와 동일함

원본 database의 SHA-256을 다시 계산하여 실행 전 값과 같은지도 확인한다.

## 실패와 재시도

실패 시 생성 도중 만들어진 private temporary file과 이 실행이 publish한 final file을 제거한다. 기존 사용자 파일은 제거하지 않는다.

재시도는 다음 절차를 따른다.

1. 오류 reason code와 manifest mapping을 검토한다.
2. 원본 database를 직접 수정하지 않는다.
3. 필요하면 별도 검토를 통해 새 manifest를 만든다.
4. 이전에 사용하지 않은 빈 output path를 지정한다.
5. 동일한 command를 다시 실행한다.

`BLOCKED`를 우회하거나 일부 document만 암묵적으로 적용하는 옵션은 없다.

## 정상 경로와 분리

- source-batch importer는 alias registry를 읽지 않는다.
- canonical visual loader는 계속 explicit `document_id`, `revision_id`, `page_id`를 요구한다.
- release builder는 alias registry를 승인 또는 attestation 근거로 사용하지 않는다.
- 신규 artifact는 legacy ID를 생성하지 않는다.

이 PR은 migration 도구와 검증 계약을 제공한다. 실제 production `LAW3` migration은 실제 source database와 사람이 검토한 manifest를 별도로 제공해 실행해야 한다.
