# Evidence Database Schema Migration

## 목적

Evidence schema v2는 페이지를 포함하는 모든 증거 레코드의 기준 식별자를 `pages.id`로 통일한다.

기존 schema v1은 `elements`에 `revision_id`, `page_id`, `page_number`를 중복 저장하고, `tables`와 `visuals`에는 `revision_id`와 `page_number`만 저장했다. 이 구조에서는 서로 다른 revision의 페이지를 동시에 가리키거나 존재하지 않는 페이지 번호를 기록할 수 있었다.

Schema v2에서는 다음 테이블이 `page_id`만 페이지 권위로 저장한다.

```text
elements
tables
visuals
```

문서 ID, revision ID, 페이지 번호와 원본 SHA-256은 다음 관계를 join해 산출한다.

```text
evidence record
-> pages
-> revisions
-> documents
```

## 기존 DB 열기 정책

런타임은 기존 데이터베이스를 자동 변경하지 않는다.

- schema v2 DB는 정상적으로 열린다.
- 정확히 인식되는 schema v1 DB는 `SchemaUpgradeRequired`로 거부된다.
- 구조를 확인할 수 없는 DB와 더 새로운 schema version은 `UnsupportedSchemaVersion`으로 거부된다.
- 존재하지 않는 DB는 자동 생성하지 않는다.
- 신규 DB 생성은 내부 생성 경로에서 명시적으로 수행한다.

## 마이그레이션 명령

PowerShell 예시:

```powershell
evidence-review evidence migrate `
  --source F:\evidence-review-workspace\evidence\evidence-v1.sqlite `
  --output F:\evidence-review-workspace\evidence\evidence-v2.sqlite
```

macOS 또는 Linux 예시:

```bash
evidence-review evidence migrate \
  --source /workspace/evidence/evidence-v1.sqlite \
  --output /workspace/evidence/evidence-v2.sqlite
```

성공 시 stdout에 다음 형식의 canonical JSON 상태가 출력된다.

```json
{
  "format": "evidence-review/evidence-migration-status",
  "version": 1,
  "status": "MIGRATED",
  "source_db": "...",
  "output_db": "...",
  "report": "...",
  "source_schema_version": 1,
  "output_schema_version": 2,
  "source_sha256": "...",
  "output_sha256": "...",
  "logical_snapshot_hash": "...",
  "counts": {}
}
```

## 생성 파일

성공한 마이그레이션은 두 파일을 생성한다.

```text
evidence-v2.sqlite
evidence-v2.sqlite.migration-report.json
```

보고서 형식은 다음과 같다.

```text
evidence-review/evidence-migration-report
```

보고서에는 다음 값이 기록된다.

- 원본과 출력 파일명
- 원본 schema version과 출력 schema version
- 원본 DB SHA-256
- 출력 DB SHA-256
- v1과 v2에서 동일해야 하는 logical snapshot hash
- 테이블별 레코드 수

## Copy-on-write 보장

마이그레이션은 원본 DB를 read-only로 연다.

처리 순서:

```text
원본 SHA-256 계산
-> schema v1 구조 확인
-> 기존 페이지 관계 검증
-> 모든 bbox 페이지 범위 검증
-> 임시 schema v2 DB 생성
-> 데이터 복사
-> retrieval_records와 FTS 재생성
-> logical snapshot hash 비교
-> PRAGMA integrity_check
-> PRAGMA foreign_key_check
-> 출력 SHA-256 계산
-> DB와 보고서 공개
```

다음 조건에서는 최종 출력 DB와 보고서를 만들지 않는다.

- element의 `page_id`, `revision_id`, `page_number`가 서로 다름
- table 또는 visual이 존재하지 않는 revision/page를 가리킴
- bbox 좌표가 뒤집힘
- bbox가 유한수가 아님
- bbox가 참조 페이지 범위를 벗어남
- migration 전후 logical snapshot hash가 다름
- SQLite integrity 또는 foreign-key 검사가 실패함
- 처리 중 원본 DB bytes가 변경됨

## 출력 파일 보호

다음 대상이 이미 있으면 마이그레이션은 덮어쓰지 않고 종료코드 1을 반환한다.

```text
--output 대상 DB
migration report 대상 파일
```

잘못된 입력, 인식할 수 없는 schema, 관계 무결성 오류 또는 bbox 오류는 종료코드 2를 반환한다.

## 논리 snapshot hash

물리 DB 구조가 달라도 동일한 증거 내용은 같은 logical snapshot hash를 가져야 한다.

Logical projection은 다음을 정규화한다.

- v1의 중복 페이지 메타데이터를 실제 `pages` 레코드와 대조
- v2의 `page_id`를 통해 revision과 페이지 번호를 join
- JSON 문자열을 JSON 객체로 파싱
- bbox 숫자를 동일한 실수 표현으로 정규화
- retrieval cache와 FTS는 논리 원본에서 제외하고 migration 후 재생성

따라서 whitespace나 정수·실수 JSON 표기 차이는 논리 hash를 바꾸지 않지만, 실제 증거 ID·본문·페이지·bbox·원본 hash 변경은 hash를 바꾼다.

## 마이그레이션 후 사용

검증이 끝난 후 워크스페이스가 참조하는 evidence DB를 새 파일로 교체한다.

교체 전에 다음 값을 보관한다.

```text
원본 DB
migration report
출력 DB SHA-256
logical snapshot hash
```

원본 DB는 즉시 삭제하지 않고 별도 보관한다. 운영 검증이 끝난 뒤에도 migration report와 함께 감사 자료로 유지하는 것을 권장한다.
