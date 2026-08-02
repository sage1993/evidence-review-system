# Legacy Visual Identity Policy Design

## 목적

기존 `04_visuals/manifests/visual_manifest.csv`를 신규 canonical visual manifest와 명확히 분리하고, legacy 행에 없는 `revision_id`와 `page_id`를 파일명·폴더명·페이지 순서로 추론하지 않도록 한다.

## 결정

Legacy CSV는 `LEGACY_NON_CANONICAL` 상태의 읽기 전용 자료로 유지한다. 이번 버전에서는 canonical manifest converter를 제공하지 않는다. 변환은 다음 권위 자료가 모두 준비된 후 별도 이슈에서만 허용한다.

- legacy `document_id`와 canonical `document_id`의 명시적 alias 기록
- 대상 `revision_id`의 명시적 지정
- `(revision_id, page_number)`가 DB에서 정확히 하나의 `page_id`로 확인됨
- visual type과 canonical kind의 명시적 매핑
- 선택할 asset path column과 workspace root의 명시적 지정
- 실제 asset SHA-256 일치

`document_id` 접두어, 파일명, 폴더명, `LAW1` 문자열, 단일 revision 존재 여부만으로 identity를 만들지 않는다.

## 아키텍처

### Legacy reader 경계

`src/ansim_review/parsing/legacy_visual_manifest.py`는 CSV를 읽고 inspection report만 생성한다. 이 모듈은 canonical `VisualRecord`를 생성하거나 `load_visual_manifest`에 데이터를 전달하지 않는다.

### Inspection report

Report format은 `evidence-review/legacy-visual-inspection` version 1이다.

주요 필드:

- `status`: 항상 `LEGACY_NON_CANONICAL` 또는 입력 자체가 손상된 경우 예외
- `source_path`, `source_sha256`
- `row_count`
- `header`
- `identity_gaps`: `revision_id`, `page_id`
- `document_ids`: 원문 문자열을 정렬·중복 제거해 보존
- `issue_counts`
- `issues`: row number, visual ID, code, detail
- `conversion_supported`: `false`
- `conversion_requirements`: 향후 converter가 요구할 권위 자료 목록

### 검증 항목

- UTF-8 BOM은 허용하며 `utf-8-sig`로 읽는다.
- legacy header는 정확히 검증한다.
- 빈 행과 중복 `visual_id`를 거부한다.
- `document_id`, `page`, `source_path`, `crop_path`, `sha256`의 누락·형식을 보고한다.
- `page`는 양의 정수만 허용한다.
- 경로는 workspace-relative POSIX 경로만 허용한다.
- SHA-256은 lowercase 64자리만 허용한다.
- 실제 asset 검증은 `root`가 제공된 경우 수행한다. 파일 누락과 hash mismatch를 issue로 기록한다.
- issue가 있어도 입력 CSV가 구조적으로 읽을 수 있으면 report를 생성한다. 이는 canonical 승인을 의미하지 않는다.

## CLI

다음 명령을 추가한다.

```powershell
evidence-review legacy inspect-visual-manifest `
  --manifest 04_visuals/manifests/visual_manifest.csv `
  --root . `
  --output runs/legacy-visual-inspection.json
```

- output은 create-only다.
- 성공 exit code는 0이다. `LEGACY_NON_CANONICAL`은 예상 상태이며 명령 실패가 아니다.
- 파일 없음, CSV 구조 오류, 잘못된 output path는 exit code 2다.
- output 존재는 exit code 1이다.

## Canonical 경계

- `load_visual_manifest`는 JSON `evidence-review/visual-manifest`만 계속 허용한다.
- generic source-batch와 release builder는 legacy CSV를 자동 탐색하지 않는다.
- 신규 writer는 CSV 또는 legacy visual format을 출력하지 않는다.
- legacy inspector는 `contracts/legacy_formats.py`에 등록된 명시적 read-only 경계로 취급한다.

## 문서와 종료 조건

README와 별도 legacy 문서에서 다음을 명시한다.

- legacy CSV는 신규 evidence identity의 권위가 아니다.
- inspection PASS와 canonical conversion은 다른 개념이다.
- converter는 명시적 alias/revision/page authority가 준비되기 전까지 제공하지 않는다.
- legacy reader 제거는 legacy Grist QA 완료, 보존 대상 artifact 목록 확정, 지원 종료 버전 공지 후 가능하다.

## 테스트

- valid legacy CSV inspection golden
- BOM 입력
- duplicate visual ID
- invalid page/path/hash
- missing asset/hash mismatch
- deterministic byte-equivalent report
- canonical loader가 CSV를 받지 않음
- CLI create-only와 exit code
- 문서에 `LEGACY_NON_CANONICAL`, `conversion_supported: false`, no-inference 정책 존재

## 비범위

- canonical JSON 변환
- Grist Desktop 화면 QA
- legacy DB 수정
- asset 복사·재배치
- alias 자동 생성
