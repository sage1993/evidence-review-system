# Grist Desktop QA Acceptance Procedure

## 목적과 한계

이 절차는 legacy `.grist` 작업공간의 화면 표시 상태를 Windows의 Grist Desktop에서 사람이 확인하고, 그 사실을 `evidence-review/grist-desktop-qa` version 1 JSON artifact로 보존하기 위한 것이다.

- 검토 scope는 `LEGACY_UI_QA`다.
- identity claim은 `LEGACY_NON_CANONICAL`이다.
- 화면에 이미지나 링크가 정상 표시돼도 canonical identity가 생성되거나 증명되는 것은 아니다.
- QA artifact는 process evidence이며 암호학적 검토자 신원 증명이 아니다.
- CI는 실제 Grist Desktop 화면 검토를 수행할 수 없다.

코드 검증과 CI가 모두 성공해도 실제 Windows 화면 검토가 없으면 Issue #38을 닫지 않는다. 실제 artifact를 작성하고 validator 결과가 PASS인 기록을 제출해야 한다.

## 준비 파일

동일한 workspace root 아래에 다음 파일을 준비한다.

1. 검토할 원본 `.grist` 파일
2. `04_visuals/manifests/visual_manifest.csv`
3. Issue #37 inspector로 만든 `runs/legacy-visual-inspection.json`
4. 대표 화면을 입증할 필요가 있을 때 사용할 스크린샷 파일
5. 네 종류의 대표 asset 파일

모든 artifact 경로는 workspace-relative POSIX path를 사용한다. 절대 경로, `..`, 역슬래시, drive-letter 경로를 사용하지 않는다.

## 1. Legacy visual preflight

검토 전에 CSV와 실제 crop asset을 검사한다.

```powershell
evidence-review legacy inspect-visual-manifest `
  --manifest 04_visuals/manifests/visual_manifest.csv `
  --root . `
  --output runs/legacy-visual-inspection.json
```

Inspection report는 다음 의미 경계를 유지해야 한다.

```json
{
  "status": "LEGACY_NON_CANONICAL",
  "conversion_supported": false
}
```

Inspector의 `issues`가 비어 있어도 legacy 자료가 canonical visual manifest로 변환된 것은 아니다.

## 2. 검토 환경 기록

Grist Desktop을 실행하기 전에 다음 정보를 기록한다.

- 실제 검토자 식별자 `reviewer_id`
- timezone이 포함된 `reviewed_at`
- Grist Desktop의 실제 버전 `grist_desktop_version`
- Windows 버전과 build를 포함한 `os`
- 검토한 `.grist` 파일의 workspace-relative path와 SHA-256
- legacy CSV path와 SHA-256
- inspection report path와 SHA-256

검토 도중 `.grist`, CSV, inspection report 또는 대표 asset을 수정했다면 기존 hash를 재사용하지 말고 검토를 처음부터 다시 수행한다.

## 3. 필수 화면 검토

다음 9개 view를 모두 실제 Grist Desktop에서 확인한다. 각 view는 `PASS`, `FAIL`, `NOT_RUN` 중 하나로 기록하고 구체적인 notes를 남긴다.

### ATTACHMENTS_FILE_LINK

Attachments 테이블 또는 파일 link가 열리고, 대상 파일을 식별할 수 있는지 확인한다. 링크가 누락되거나 잘못된 파일을 가리키면 FAIL이다.

### VISUALS_THUMBNAIL

Visuals 화면에서 thumbnail이 표시되는지 확인한다. 빈 셀, 깨진 이미지, 다른 행의 이미지가 표시되면 FAIL이다.

### REFERENCE_LINK_PREVIEW

Reference link 또는 preview가 기대한 대상과 연결되는지 확인한다. 행을 열 수 없거나 preview가 다른 자료를 표시하면 FAIL이다.

### PAGE_RENDER

페이지 전체 render가 읽을 수 있는 크기와 방향으로 표시되는지 확인한다. 최소 한 개의 대표 `PAGE_RENDER` sample을 선택한다.

### IMAGE_CONTEXT_CROP

본문 이미지와 주변 문맥을 포함하는 crop이 표시되는지 확인한다. 최소 한 개의 대표 `IMAGE_CONTEXT_CROP` sample을 선택한다.

### TABLE_CROP

표 crop이 잘리지 않고 행·열 맥락을 확인할 수 있는지 검토한다. 최소 한 개의 대표 `TABLE_CROP` sample을 선택한다.

### COMPOSITE_DIAGRAM

복합 도면이나 여러 요소가 포함된 diagram이 의도한 전체 구성으로 보이는지 검토한다. 최소 한 개의 대표 `COMPOSITE_DIAGRAM` sample을 선택한다.

### MISSING_BROKEN_LINK_SCAN

Visuals, Attachments, References를 순회하며 누락 파일, 깨진 링크, hash가 맞지 않는 asset, 빈 preview를 확인한다.

### LEGACY_CANONICAL_SEPARATION

Grist 화면의 legacy `document_id`, page 숫자, 파일명 또는 폴더명이 canonical `document_id`, `revision_id`, `page_id`로 오인되지 않았는지 확인한다. 화면 표시 성공을 canonical identity 증거로 기록하면 FAIL이다.

## 4. 대표 sample 기록

다음 네 content kind 각각에 대해 최소 한 개의 PASS sample이 있어야 최종 PASS가 가능하다.

- `PAGE_RENDER`
- `IMAGE_CONTEXT_CROP`
- `TABLE_CROP`
- `COMPOSITE_DIAGRAM`

각 sample에 다음을 기록한다.

- 고유 `sample_id`
- `content_kind`
- 재현 가능한 legacy `row_id`
- 실제 확인한 `asset_path`
- 실제 asset의 lowercase SHA-256
- `PASS` 또는 `FAIL`
- 필요한 경우 연결된 screenshot evidence ID
- 무엇을 확인했는지 설명하는 notes

`row_id`는 legacy 위치 표기일 뿐 canonical identity가 아니다.

## 5. Screenshot evidence

스크린샷은 모든 PASS에 의무는 아니지만, 실패 화면·복합 화면·검토자 간 해석 차이가 예상되는 화면에는 남기는 것을 권장한다.

각 screenshot은 다음 값을 가진다.

- 고유 `evidence_id`
- workspace-relative path
- lowercase SHA-256

View, sample, finding은 artifact의 `evidence_files`에 존재하는 ID만 참조할 수 있다.

## 6. Finding 작성

문제가 발견되면 finding에 다음을 기록한다.

- 고유 `finding_id`
- 관련 필수 `view_id`
- `OPEN` 또는 `RESOLVED`
- legacy `row_id` 또는 관련 `file_path` 중 최소 하나
- 재현 가능한 description
- 필요한 screenshot evidence ID

View를 FAIL로 기록하면 같은 view를 가리키는 OPEN finding이 최소 한 개 있어야 한다. 실패 위치를 파일명 추론이나 임의 page identity로 보정하지 않는다.

## 7. Artifact 작성

`docs/examples/grist-desktop-qa.example.json`을 복사해 실제 값으로 채운다. 예제는 모든 view가 `NOT_RUN`이고 sample이 없으므로 실제 acceptance evidence가 아니다.

입력 artifact에는 overall status를 직접 쓰지 않는다. Validator가 관찰 결과에서 상태를 계산한다.

- 하나 이상의 FAIL view, FAIL sample 또는 OPEN finding: `FAIL`
- 실패는 없지만 NOT_RUN view 또는 필수 PASS sample 누락: `INCOMPLETE`
- 9개 view가 모두 PASS이고 네 종류 sample이 각각 PASS이며 OPEN finding이 없음: `PASS`

## 8. Validator 실행

```powershell
evidence-review legacy validate-grist-qa `
  --artifact qa/grist-desktop-qa.json `
  --root .
```

Validator는 다음을 재검증한다.

- JSON format, version, scope와 identity claim
- 필수 view와 ID 참조 무결성
- `.grist`, CSV, inspection report, screenshot, 대표 asset의 실제 SHA-256
- 모든 경로가 workspace root 내부인지 여부
- inspection report가 `LEGACY_NON_CANONICAL` 및 `conversion_supported: false`를 유지하는지 여부
- inspection report의 source hash가 동일한 legacy CSV hash와 일치하는지 여부

종료 코드는 다음과 같다.

| 코드 | 의미 |
|---:|---|
| 0 | 유효한 artifact이며 derived status가 `PASS` |
| 1 | 유효한 artifact이나 derived status가 `FAIL` 또는 `INCOMPLETE` |
| 2 | JSON, 계약, 경로, 파일 또는 SHA-256 검증 실패 |

Stdout의 `evidence-review/grist-desktop-qa-status` JSON과 입력 artifact를 함께 보존한다.

## 9. Issue #38 완료 조건

다음 자료가 모두 있어야 Issue #38을 닫을 수 있다.

1. 실제 Windows 환경에서 작성한 QA artifact
2. 실제 Grist Desktop 버전과 OS 기록
3. 원본 `.grist`, CSV, inspection report와 대표 asset hash 일치
4. 9개 필수 view가 모두 PASS
5. 네 대표 content kind에 각각 PASS sample 존재
6. OPEN finding 없음
7. validator 결과가 PASS이고 exit code가 0인 실행 기록

PR의 자동 테스트 성공, 예제 JSON, `INCOMPLETE` artifact만으로는 Issue #38을 닫지 않는다.
