# Grist Desktop QA Artifact Design

## Goal

Issue #38의 legacy Grist Desktop 화면 검증을 사람이 수행하되, 검토 환경·원본 파일·대표 asset·선택적 스크린샷·화면별 판정·실패 위치를 하나의 엄격한 JSON artifact로 보존하고 재검증할 수 있게 한다.

## Non-goals

- Grist Desktop UI 자동화
- 화면 표시 성공을 canonical identity 증거로 사용
- legacy CSV를 canonical visual manifest로 변환
- 파일명·폴더명·접두어·행 순서로 document/revision/page identity 추론
- CI에서 실제 Grist Desktop 화면 검증을 완료했다고 주장

## Authority boundary

Artifact의 scope는 정확히 `LEGACY_UI_QA`이고 identity claim은 정확히 `LEGACY_NON_CANONICAL`이다. Artifact는 화면 검토 사실을 기록하지만 canonical evidence identity를 만들거나 수정하지 않는다.

Issue #37의 legacy inspection report를 preflight 입력으로 사용한다. Validator는 report가 다음 조건을 만족하는지 확인한다.

- `format == "evidence-review/legacy-visual-inspection"`
- `version == 1`
- `status == "LEGACY_NON_CANONICAL"`
- `conversion_supported == false`
- `source_sha256`가 artifact에 기록된 legacy visual CSV SHA-256과 일치

## Artifact format

Top-level format은 `evidence-review/grist-desktop-qa`, version은 `1`이다. 모든 필드는 명시적이며 unknown field는 거부한다.

### Review identity

- `reviewer_id`: 비어 있지 않은 검토자 식별자
- `reviewed_at`: timezone을 포함하는 ISO-8601 시각
- `grist_desktop_version`: 실제 사용한 Grist Desktop 버전
- `os`: 실제 사용한 운영체제와 버전

이 기록은 process evidence이며 암호학적 신원 검증을 뜻하지 않는다.

### Bound source files

다음 세 파일을 workspace-relative POSIX path와 lowercase SHA-256으로 고정한다.

- 원본 `.grist` 파일
- `04_visuals/manifests/visual_manifest.csv`
- Issue #37 legacy inspection report

Validator는 `--root` 아래 실제 파일을 열어 SHA-256을 다시 계산한다. 경로 탈출, 절대 경로, 역슬래시 경로는 거부한다.

### Required view checks

다음 view ID가 정확히 한 번씩 있어야 한다.

1. `ATTACHMENTS_FILE_LINK`
2. `VISUALS_THUMBNAIL`
3. `REFERENCE_LINK_PREVIEW`
4. `PAGE_RENDER`
5. `IMAGE_CONTEXT_CROP`
6. `TABLE_CROP`
7. `COMPOSITE_DIAGRAM`
8. `MISSING_BROKEN_LINK_SCAN`
9. `LEGACY_CANONICAL_SEPARATION`

각 view는 `PASS`, `FAIL`, `NOT_RUN` 중 하나와 비어 있지 않은 notes, 선택적 evidence ID 목록을 가진다. Evidence ID는 artifact의 evidence file 목록에 존재해야 한다.

### Representative samples

다음 네 content kind는 각각 최소 한 개의 PASS sample이 있어야 최종 PASS가 가능하다.

- `PAGE_RENDER`
- `IMAGE_CONTEXT_CROP`
- `TABLE_CROP`
- `COMPOSITE_DIAGRAM`

Sample은 `sample_id`, `content_kind`, legacy `row_id`, `asset_path`, `asset_sha256`, `result`, `evidence_ids`, `notes`를 가진다. Validator는 asset 파일의 실제 SHA-256을 재검증한다. `row_id`는 legacy 위치 표기이며 canonical identity가 아니다.

### Evidence files

스크린샷은 필요한 경우에만 첨부한다. 각 evidence file은 안전한 상대 경로와 SHA-256을 가진다. PASS/FAIL view와 sample은 존재하는 evidence ID만 참조할 수 있다.

### Findings

Finding은 다음을 기록한다.

- 고유 `finding_id`
- 연관 `view_id`
- `OPEN` 또는 `RESOLVED`
- nullable `row_id`
- nullable `file_path`
- 비어 있지 않은 description
- 선택적 evidence ID 목록

재현 가능성을 위해 `row_id`와 `file_path` 중 하나 이상이 있어야 한다. FAIL view마다 해당 view를 참조하는 OPEN finding이 최소 한 개 필요하다.

## Derived status

Artifact에 overall status를 입력하지 않는다. Validator가 다음 순서로 계산한다.

1. view가 `FAIL`, sample이 `FAIL`, 또는 OPEN finding이 있으면 `FAIL`
2. 그 외에 required view가 `NOT_RUN`이거나 required content kind의 PASS sample이 없으면 `INCOMPLETE`
3. 모든 required view가 PASS이고 네 required content kind에 PASS sample이 있으며 OPEN finding이 없으면 `PASS`

CLI exit code:

- `0`: valid artifact, derived status `PASS`
- `1`: valid artifact, derived status `FAIL` 또는 `INCOMPLETE`
- `2`: JSON/contract/path/hash/inspection binding 오류

## CLI

```powershell
evidence-review legacy validate-grist-qa `
  --artifact qa/grist-desktop-qa.json `
  --root .
```

Stdout은 canonical status document를 출력한다.

```json
{
  "format": "evidence-review/grist-desktop-qa-status",
  "version": 1,
  "status": "PASS",
  "accepted": true,
  "artifact_sha256": "...",
  "reviewer_id": "...",
  "reviewed_at": "...",
  "view_counts": {"PASS": 9, "FAIL": 0, "NOT_RUN": 0},
  "open_finding_count": 0
}
```

## Error handling

- Contract field 누락·unknown field·중복 ID는 `ValueError`
- unsafe path 또는 missing file은 검증 실패
- 실제 SHA-256 불일치는 검증 실패
- inspection report 의미 경계 불일치는 검증 실패
- 유효하지만 미완료 또는 실패한 수동 QA는 contract 오류가 아니라 derived status로 표현

## Test strategy

- strict decoder unit tests
- required view ID와 duplicate/missing tests
- FAIL view와 OPEN finding 관계 tests
- derived PASS/FAIL/INCOMPLETE tests
- safe path, missing file, hash mismatch tests
- legacy inspection report binding tests
- CLI integration tests와 exit code tests
- canonical status byte determinism test
- 문서에서 수동 검토와 canonical authority 분리를 고정하는 regression test

## Acceptance boundary

이 구현이 병합돼도 Issue #38의 실제 Grist Desktop 화면 QA는 완료되지 않는다. 실제 Windows 환경에서 artifact를 작성하고 validator가 `PASS`를 반환한 기록이 제출돼야 Issue #38을 닫을 수 있다.
