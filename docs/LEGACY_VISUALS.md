# Legacy Grist Visual Compatibility Boundary

## 상태와 권위 범위

기존 `04_visuals/manifests/visual_manifest.csv`는 과거 Grist 작업공간을 확인하기 위한 읽기 전용 자료다. 신규 evidence identity의 권위 자료가 아니며 모든 inspection report는 다음 상태를 기록한다.

```json
{
  "status": "LEGACY_NON_CANONICAL",
  "conversion_supported": false
}
```

Inspection 성공은 CSV를 읽고 구조·경로·해시 문제를 보고할 수 있다는 뜻이다. Canonical visual manifest로 승격됐다는 뜻이 아니다. 이 버전은 legacy CSV를 canonical visual manifest로 자동 변환하지 않는다.

## Identity gap

Legacy CSV에는 신규 visual identity에 필요한 `revision_id`와 `page_id`가 없다. 기존 `document_id`도 숫자 또는 `LAW1` 계열 문자열처럼 과거 작업공간 내부 값일 수 있어 신규 canonical `document_id`와 동일하다고 볼 수 없다.

다음 정보로 identity를 추론하지 않는다.

- 파일명 또는 폴더명
- `LAW1`, `LAW2` 같은 접두어
- CSV 행 순서 또는 page 숫자만의 조합
- DB에 revision이 하나뿐이라는 사실
- `source_path` 또는 `crop_path`
- 이미지 파일의 이름이나 저장 위치

따라서 파일명에서 문서나 페이지를 추론하지 않으며, 행의 `page`는 과거 표시값으로만 검사한다.

## Read-only inspection

다음 명령은 legacy CSV를 검사하고 create-only JSON report를 만든다.

```powershell
evidence-review legacy inspect-visual-manifest `
  --manifest 04_visuals/manifests/visual_manifest.csv `
  --root . `
  --output runs/legacy-visual-inspection.json
```

`--root`를 지정하면 `crop_path`가 root 아래에 있는지 확인하고 실제 asset SHA-256을 비교한다. 지정하지 않으면 CSV 자체의 형식만 검사한다. 어떤 경우에도 inspector는 canonical visual record를 생성하거나 evidence database를 수정하지 않는다.

검사 항목:

- UTF-8 BOM 및 정확한 17개 legacy column header
- 빈 행과 중복 `visual_id`
- `document_id` 누락
- 양의 정수 `page`
- workspace-relative POSIX `source_path`와 `crop_path`
- lowercase SHA-256 형식
- 선택한 asset의 존재 여부와 SHA-256 일치 여부

Report의 `issues`가 비어 있어도 상태는 계속 `LEGACY_NON_CANONICAL`이다. `conversion_supported`는 항상 `false`다.

## 향후 변환을 허용할 수 있는 조건

별도 converter를 만들려면 각 행에 대해 다음 권위 자료가 모두 명시적으로 제공돼야 한다.

- `EXPLICIT_DOCUMENT_ALIAS`: legacy `document_id`와 canonical `document_id`의 검토된 alias
- `EXPLICIT_REVISION_ID`: 대상 canonical `revision_id`
- `DB_RESOLVED_PAGE_ID`: `(revision_id, page_number)`가 DB에서 정확히 하나의 `page_id`로 확인됨
- `EXPLICIT_VISUAL_KIND_MAP`: legacy `visual_type`과 canonical kind의 검토된 매핑
- `EXPLICIT_ASSET_PATH_POLICY`: `source_path`와 `crop_path` 중 어떤 asset을 사용할지 명시
- `ASSET_SHA256_MATCH`: 선택한 실제 asset의 SHA-256 일치

하나라도 없으면 행은 unresolved로 유지해야 하며 자동 선택하거나 fallback하지 않는다. Alias, revision, page authority를 별도 입력으로 받지 않는 converter는 구현 대상이 아니다.

## Canonical loader와의 분리

Canonical loader는 JSON format `evidence-review/visual-manifest`만 읽는다. 각 record의 `document_id`, `revision_id`, `page_id`를 필수로 요구하고 DB의 `pages → revisions → documents` 관계를 재검증한다.

Legacy inspector는 다음 작업을 하지 않는다.

- canonical `VisualRecord` 생성
- source-batch 또는 release builder의 자동 입력으로 사용
- evidence database에 visual 삽입
- filename/path 기반 identity 보정
- legacy row 수정 또는 정규화

## Grist QA와 보존

Issue #38의 Grist Desktop QA에서는 이 inspection report를 legacy artifact inventory의 입력으로 사용할 수 있다. 그러나 Grist 화면에서 이미지가 보인다는 사실만으로 canonical identity가 증명되지는 않는다. QA artifact에는 원본 Grist 파일 hash, CSV hash, asset hash, 표시 결과와 검토자 기록을 별도로 보존해야 한다.

## Legacy reader 제거 조건

legacy reader 제거는 다음 조건을 모두 만족한 후 별도 호환성 변경으로 진행한다.

1. Issue #38의 Grist Desktop QA와 acceptance artifact가 완료됨
2. 보존해야 할 legacy Grist 파일·CSV·asset 목록과 hash가 확정됨
3. 향후 접근 방법과 archive 위치가 문서화됨
4. 지원 종료 버전과 제거 예정 버전이 공지됨
5. 신규 canonical workflow가 legacy CSV를 참조하지 않는다는 회귀 검증이 있음

이 조건이 완료되기 전까지 reader는 inspection-only로 유지하며, 신규 writer는 legacy CSV를 출력하지 않는다.
