# Legacy Document Lineage Migration Design

## 1. 목적

동일한 원본 PDF가 legacy document ID와 canonical document ID로 중복 등록된 evidence schema v2 데이터베이스를 대상으로, 사람이 검토한 명시적 lineage manifest에 따라 안전한 중복 계보만 copy-on-write 방식으로 정리한다.

대표 사례:

- legacy document ID: `LAW3`
- canonical document ID: `DOC-ACFD68E34043268C`
- 두 document가 동일한 원본 PDF SHA-256을 가리킴

이 기능은 filename, directory, prefix, row order 또는 단일 revision 존재 여부로 identity를 추론하지 않는다.

## 2. 핵심 결정

### 2.1 명시적 권위 입력

migration은 `evidence-review/legacy-lineage-manifest` version 1 JSON 없이는 실행할 수 없다.

각 mapping은 다음 값을 사람이 명시해야 한다.

- `legacy_document_id`
- `canonical_document_id`
- `source_sha256`
- `revision_mappings`
  - `legacy_revision_id`
  - `canonical_revision_id`
- `reviewer_id`
- `reviewed_at`
- `reason`

`reviewed_at`은 timezone offset이 포함된 ISO 8601 timestamp여야 한다.

### 2.2 schema v3 미도입

canonical output database는 기존 evidence schema v2를 유지한다.

legacy alias는 DB 내부 신규 table로 넣지 않고, 다음 외부 create-only artifact에서 보존한다.

- `legacy-lineage-aliases.json`
- `legacy-lineage-migration-report.json`

정상 조회·검색·신규 ingest 경로는 canonical ID만 사용한다.

### 2.3 copy-on-write

원본 database는 read-only URI와 `PRAGMA query_only = ON`으로 연다.

migration은 다음 파일만 새로 만든다.

- output evidence SQLite database
- alias registry JSON
- migration report JSON

source와 output 경로는 달라야 하며 기존 output은 덮어쓰지 않는다.

### 2.4 안전한 graph 병합만 허용

legacy revision graph와 canonical revision graph는 source hash만 같다고 자동 병합하지 않는다.

다음 계층별 equivalence가 모두 확인돼야 한다.

1. revision metadata
   - source hash
   - byte size
   - page count
2. page mapping
   - page number
   - width
   - height
3. evidence payload
   - elements
   - clauses
   - tables
   - visuals
4. auxiliary relations
   - links
   - review flags
   - retrieval records

차이가 있으면 migration을 수행하지 않고 deterministic unresolved item을 반환한다.

## 3. Manifest 계약

예시:

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
          "canonical_revision_id": "REV-DOC-ACFD68E34043268C-001"
        }
      ]
    }
  ]
}
```

Strict validation rules:

- unknown fields rejected
- empty strings rejected
- lowercase SHA-256 only
- duplicate legacy document ID rejected
- duplicate canonical target in conflicting mappings rejected
- legacy ID and canonical ID must differ
- revision IDs must be unique across all mappings
- one legacy revision maps to exactly one canonical revision
- one canonical revision cannot receive two legacy revisions unless all three graphs are byte-equivalent; version 1 rejects this case instead of inferring equivalence
- source database hash must match actual source bytes before any work starts

## 4. Graph model

### 4.1 Stable logical fingerprints

Physical SQLite byte equality is not used for graph comparison.

Each row is projected into canonical JSON and hashed with SHA-256.

Projection rules:

- sort object keys through canonical JSON
- sort row collections by stable primary key
- preserve raw JSON text semantics by decoding and re-encoding canonical JSON where the schema field stores JSON
- preserve human-reviewed text exactly
- normalize neither identifiers nor free text
- exclude only database-local row ordering and SQLite storage details

### 4.2 Page equivalence

Pages are paired by explicit revision mapping and exact page number.

Required equality:

- page count identical
- every page number exists exactly once on both sides
- width and height are exact numeric values after SQLite decoding

No nearest-size tolerance is permitted.

### 4.3 Evidence equivalence

Rows whose parent page or revision differs are compared after replacing the legacy parent ID with the mapped canonical parent ID in the logical projection.

An entity is equivalent only when all non-identity payload fields match.

Identity handling:

- equal primary IDs: direct match
- different primary IDs: match by deterministic content fingerprint within the mapped parent
- zero matches: unresolved missing counterpart
- multiple matches: unresolved ambiguous counterpart

### 4.4 Human-reviewed data

The following values must be preserved exactly:

- `clauses.review_status`
- `clauses.normalized_text`
- `review_flags` rows and statuses
- review-related link rows
- retrieval text derived from reviewed records

If the canonical counterpart is `AUTOMATIC` and the legacy counterpart is `REVIEWED`, version 1 does not silently overwrite the canonical row during comparison. It records `REVIEWED_VALUE_CONFLICT` and blocks migration unless the canonical row already contains the same reviewed value and status.

This prevents a lineage migration from becoming an implicit review promotion mechanism.

## 5. Migration planner

Public interface:

```python
plan_legacy_lineage_migration(
    source_database: Path,
    manifest: LegacyLineageManifest,
) -> LegacyLineagePlan
```

The planner:

1. verifies source database hash
2. requires evidence schema version 2
3. runs `PRAGMA integrity_check` and `PRAGMA foreign_key_check`
4. verifies every legacy and canonical document exists
5. verifies every declared revision belongs to the declared document
6. verifies source hash, byte size and page count
7. builds page and evidence mappings
8. verifies links, review flags and retrieval records
9. returns a deterministic plan or deterministic unresolved items

A plan with any unresolved item has status `BLOCKED` and cannot be applied.

## 6. Copy-on-write applier

Public interface:

```python
apply_legacy_lineage_migration(
    source_database: Path,
    manifest_path: Path,
    output_database: Path,
) -> LegacyLineageMigrationResult
```

Apply sequence:

1. validate manifest and source hash
2. create plan
3. refuse `BLOCKED` plan
4. copy source bytes to a private temporary output path
5. open temporary output with foreign keys enabled
6. begin `IMMEDIATE` transaction
7. map legacy page/evidence IDs to canonical counterparts
8. rewrite auxiliary references only where an equivalent canonical target exists
9. delete equivalent legacy graph rows in child-to-parent order
10. delete legacy revisions and legacy document rows
11. rebuild retrieval index deterministically
12. run integrity, foreign-key and logical snapshot checks
13. commit transaction
14. write alias registry and report to temporary create-only paths
15. atomically move all three outputs into final paths
16. re-hash source and fail if source changed during execution

No output survives a failed migration.

## 7. Deletion and reference order

The migration removes only rows proved equivalent.

Logical order:

1. duplicate retrieval records
2. links that point to legacy IDs after equivalent canonical link verification
3. review flags after canonical equivalent verification
4. elements, tables, visuals and clauses
5. pages
6. revisions
7. legacy documents

Rows that cannot be mapped exactly block the entire migration. Partial migration is not supported.

## 8. Alias registry

Format: `evidence-review/legacy-lineage-aliases`, version 1.

Each entry contains:

- legacy document ID
- canonical document ID
- source SHA-256
- legacy revision ID
- canonical revision ID
- reviewer ID
- reviewed timestamp
- migration report hash

The registry is historical lookup metadata only.

It must not be accepted by source-batch ingest as document identity authority and must not cause new artifacts to emit legacy IDs.

## 9. Migration report

Format: `evidence-review/legacy-lineage-migration-report`, version 1.

Required fields:

- status: `MIGRATED` or `BLOCKED`
- source database file name and SHA-256
- output database file name and SHA-256 when migrated
- manifest SHA-256
- reviewer ID and timestamp
- mapping counts
- before/after table counts
- before/after logical snapshot lineage digest
- removed legacy IDs
- preserved canonical IDs
- preservation counts for reviewed clauses, flags, links and retrieval rows
- sorted unresolved items
- integrity and foreign-key results

The report does not claim that the reviewer cryptographically signed the mapping.

## 10. CLI

```powershell
evidence-review evidence migrate-lineage `
  --source 01_database/evidence.sqlite `
  --manifest migration/legacy-lineage-manifest.json `
  --output migrated/evidence.sqlite
```

Exit codes:

- `0`: migration completed and all outputs verified
- `1`: output path already exists
- `2`: invalid manifest, hash mismatch, blocked plan, integrity failure or I/O failure

The command writes canonical JSON status to stdout.

## 11. Determinism

Given byte-identical source database and manifest:

- planner output canonical JSON bytes are identical
- alias registry canonical JSON bytes are identical except that no runtime-generated timestamp is allowed
- migration report canonical JSON bytes are identical
- logical output database digest is identical

SQLite physical file SHA-256 may vary if SQLite runtime versions differ. The report therefore records both physical SHA-256 and a canonical logical lineage digest. Same-runtime CI tests additionally require physical byte equality for repeated isolated runs.

## 12. Failure modes

Stable reason codes include:

- `SOURCE_DATABASE_HASH_MISMATCH`
- `SOURCE_SCHEMA_VERSION_UNSUPPORTED`
- `SOURCE_INTEGRITY_FAILED`
- `LEGACY_DOCUMENT_NOT_FOUND`
- `CANONICAL_DOCUMENT_NOT_FOUND`
- `REVISION_OWNERSHIP_MISMATCH`
- `REVISION_SOURCE_HASH_MISMATCH`
- `REVISION_METADATA_MISMATCH`
- `PAGE_SET_MISMATCH`
- `PAGE_GEOMETRY_MISMATCH`
- `EVIDENCE_COUNTERPART_MISSING`
- `EVIDENCE_COUNTERPART_AMBIGUOUS`
- `EVIDENCE_PAYLOAD_MISMATCH`
- `REVIEWED_VALUE_CONFLICT`
- `LINK_COUNTERPART_MISSING`
- `REVIEW_FLAG_COUNTERPART_MISSING`
- `RETRIEVAL_COUNTERPART_MISSING`
- `SOURCE_CHANGED_DURING_MIGRATION`
- `OUTPUT_VERIFICATION_FAILED`

Reason codes and unresolved items are sorted deterministically.

## 13. 테스트 전략

### Unit

- strict manifest decoding
- duplicate and ambiguous mapping rejection
- graph fingerprint stability
- parent-ID substitution during comparison
- reviewed-value conflict blocking
- deterministic plan and report serialization

### Integration

- exact duplicate legacy/canonical graph migrates
- source remains byte-identical
- output contains only canonical document/revision/page graph
- links, review flags and retrieval rows remain valid
- one mismatched table/visual/element blocks all output
- source hash tampering blocks before temporary output creation
- simulated failure leaves no output or temporary file
- repeated same-runtime runs produce byte-identical outputs
- CLI exit codes and create-only behavior

### Regression

- source-batch importer never reads alias registry
- canonical visual loader still requires explicit document/revision/page IDs
- existing v1-to-v2 migration and review preservation tests remain green
- release builder does not treat legacy alias registry as authorization evidence

## 14. 문서

Add:

- `docs/LEGACY_LINEAGE_MIGRATION.md`
- `docs/examples/legacy-lineage-manifest.example.json`

Update:

- `docs/LEGACY_VISUALS.md`
- `README.md`

Documentation must state that migration is explicit, copy-on-write, fail-closed and non-cryptographic with respect to reviewer identity.

## 15. 비범위

- Grist internal schema mutation
- source PDF or parser artifact mutation
- automatic alias discovery
- different source hash revisions merge
- canonical record review-status promotion
- fuzzy text or geometry matching
- schema v3 introduction
- legacy visual canonical conversion

## 16. 완료 조건

1. manifest is mandatory and strict
2. source database remains byte-identical
3. only graph-equivalent duplicates migrate
4. all relationships are preserved or the entire migration blocks
5. output database passes integrity and foreign-key checks
6. alias registry and report are deterministic create-only artifacts
7. reviewed values are preserved without implicit promotion
8. canonical normal path does not consume legacy aliases
9. all automated CI gates pass on Python 3.11 and 3.13, Windows and Ubuntu
