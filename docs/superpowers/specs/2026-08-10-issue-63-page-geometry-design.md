# Issue #63 — PDF Page Geometry Validation Design

Date: 2026-08-10
Issue: #63 `[P1] 페이지 크기 누락 시 A4(595×842) fallback으로 bbox 좌표가 왜곡될 수 있음`
Branch: `agent/issue-63-page-geometry-design`

## 1. 목적

OpenDataLoader parser artifact에 page width/height가 없거나 잘못된 경우 현재 구현이 `595.0 × 842.0`을 사용하여 정상 geometry처럼 처리하는 동작을 제거한다.

이 설계의 목표는 원본 PDF에서 확인한 page geometry를 canonical source로 삼고, parser geometry와 교차 검증하여 bbox provenance가 실제 PDF와 일치하지 않는 상태로 evidence database 또는 Review Workspace까지 전달되지 않도록 하는 것이다.

핵심 원칙은 다음과 같다.

1. 임의 A4 fallback을 사용하지 않는다.
2. 원본 PDF geometry를 canonical page geometry로 사용한다.
3. parser geometry는 신뢰 가능한 경우에도 PDF geometry와 교차 검증한다.
4. geometry를 확정할 수 없거나 parser와 PDF가 의미 있게 불일치하면 fail-closed 한다.
5. ingestion, evidence database, citation bbox, page-image metadata, Review Workspace overlay가 동일한 page coordinate contract를 사용한다.
6. 기존 정상 bbox golden case는 유지한다.

## 2. 현재 문제

현재 `src/ansim_review/parsing/odl_source.py`의 `parser_page_dimensions()`는 parser artifact의 `pages` 배열에서 유효한 width/height를 찾지 못하면 `595.0 × 842.0`을 반환한다.

`OpenDataLoaderJsonAdapter.parse()`는 이 값을 `PageDimensions`로 만들고 같은 width/height를 `parser_bbox()`에 전달한다. 그 결과 잘못된 page geometry가 다음 단계로 정상 데이터처럼 전파될 수 있다.

```text
parser artifact
  -> parser_page_dimensions()
  -> PageDimensions
  -> bbox normalization
  -> NormalizedParserContribution
  -> source_batch_importer
  -> evidence.pages(width, height)
  -> retrieval/citation
  -> Review Workspace overlay
```

Review Workspace는 별도로 생성된 page-image metadata의 `pdf_width`/`pdf_height`를 SVG `viewBox`와 bbox bounds 검사에 사용한다. 따라서 ingestion 시 저장된 page geometry와 page-image geometry가 서로 다른 출처에서 만들어지며, 두 값이 불일치해도 현재는 이를 전체 pipeline에서 명시적으로 검증하지 않는다.

이 문제는 단순 UI scaling 문제가 아니라 좌표 기반 provenance가 실제 원본과 달라질 수 있는 silent data corruption 문제로 취급한다.

## 3. 범위

### 포함

- OpenDataLoader JSON adapter의 page geometry 결정
- 원본 PDF의 CropBox/MediaBox geometry 읽기
- parser dimensions의 존재/유효성 판정
- parser dimensions와 PDF dimensions 교차 검증
- parser/PDF page count 교차 검증
- bbox normalization에 canonical PDF dimensions 사용
- evidence DB에 canonical dimensions 저장
- Review Workspace에서 DB geometry와 page-image geometry 일치 검증
- A4/A3/landscape/custom-size/CropBox fixture
- malformed/zero/negative/non-finite geometry regression
- 기존 bbox golden case 회귀 검증

### 제외

- OpenDataLoader 자체 parser 구현 변경
- 새로운 parser 종류 추가
- PDF 렌더링 엔진 교체
- evidence DB schema migration
- bbox 저장 포맷 변경
- 임의 보정 또는 heuristic scaling

## 4. Canonical Page Geometry 계약

### 4.1 좌표 단위

모든 page geometry와 bbox는 PDF point 단위를 사용한다.

- `1 point = 1/72 inch`
- canonical bbox 형식은 `[left, bottom, right, top]`
- canonical page-local origin은 선택된 effective page box의 좌하단을 `(0, 0)`으로 본다.

DB에 저장하는 `pages.width`와 `pages.height`는 effective page box의 크기이며 절대 PDF object 좌표의 upper-right 값이 아니다.

즉 box가 `[llx, lly, urx, ury]`이면 다음과 같이 계산한다.

```text
width  = urx - llx
height = ury - lly
```

이 규칙은 CropBox 또는 MediaBox의 lower-left가 0이 아닌 PDF에서도 잘못된 page size를 만들지 않도록 한다.

### 4.2 Effective page box 선택

페이지별 canonical geometry는 다음 순서로 결정한다.

1. 유효한 CropBox를 사용할 수 있으면 CropBox를 사용한다.
2. CropBox를 사용할 수 없으면 유효한 MediaBox를 사용한다.
3. 둘 다 finite positive geometry를 만들 수 없으면 `PAGE_DIMENSIONS_UNAVAILABLE`로 실패한다.

유효한 box의 조건은 다음과 같다.

- 네 좌표 모두 finite number
- `urx > llx`
- `ury > lly`
- 계산된 width/height가 각각 0보다 큼

CropBox와 MediaBox의 존재 여부보다 실제 계산 가능한 geometry 여부를 우선한다. pypdf가 inherited box를 해석하는 경우에도 최종적으로 얻은 box 값의 유효성을 검사한다.

### 4.3 Rotation

이 이슈의 canonical evidence coordinate system은 **선택된 effective page box의 unrotated PDF user space**로 유지한다.

- `/Rotate` 값은 PDF geometry resolver가 함께 읽고 검증한다.
- 허용 값은 정규화된 `0`, `90`, `180`, `270`이다.
- `PageDimensions.width/height` 자체는 rotation으로 swap하지 않는다.
- OpenDataLoader의 현재 bbox contract는 `PDF_BOTTOM_LEFT`이므로 parser bbox는 이미 canonical PDF user-space 좌표로 취급하며 이 이슈에서 임의 inverse rotation을 추가하지 않는다.
- page-image producer/renderer는 canonical PDF width/height와 화면 이미지 orientation의 관계를 유지해야 하며 Review Workspace에서는 page-image metadata와 DB geometry를 교차 검증한다.

따라서 `landscape`는 width > height인 실제 page box로 처리하며, landscape 여부를 A4 portrait fallback 또는 `/Rotate` 추정으로 만들지 않는다.

비정상 `/Rotate` 값이 canonical orientation을 결정할 수 없게 만드는 경우에는 geometry를 추정하지 않고 `PAGE_ROTATION_INVALID`로 실패한다.

## 5. PDF Geometry Resolver

새 모듈을 `src/ansim_review/parsing/pdf_page_geometry.py`에 둔다.

책임은 다음 하나로 제한한다.

> 원본 PDF를 읽어 페이지별 검증된 canonical geometry를 결정한다.

권장 데이터 모델:

```text
PdfPageGeometry
- page_number: int
- width: float
- height: float
- box_kind: "CROP_BOX" | "MEDIA_BOX"
- origin_x: float
- origin_y: float
- rotation: int
```

`origin_x`/`origin_y`는 향후 absolute PDF user-space 좌표와 page-local 좌표 변환 검증에 사용할 수 있도록 resolver 내부 결과에 보존한다. 현재 `PageDimensions`와 evidence DB에는 width/height만 전달한다.

Resolver는 PDF당 `PdfReader`를 한 번만 생성하고 모든 page geometry를 한 번에 읽는다. 페이지마다 파일을 다시 열지 않는다.

예상 public boundary:

```text
read_pdf_page_geometries(source_path: Path) -> tuple[PdfPageGeometry, ...]
```

실패는 machine-readable reason code가 포함된 명시적 예외로 전달한다.

## 6. Parser Geometry 해석

현재 `parser_page_dimensions()`는 반환 타입 자체가 "정상값"과 "fallback"을 구분하지 못한다. 이를 다음 두 단계로 분리한다.

### 6.1 parser dimension extraction

parser artifact에서 page별 width/height를 찾되 다음 세 상태를 구분한다.

- `ABSENT`: width/height가 제공되지 않음
- `VALID`: finite positive width/height 제공
- `INVALID`: 필드는 존재하지만 bool, non-number, NaN, infinity, zero, negative 등으로 잘못됨

`INVALID`는 `ABSENT`로 취급하지 않는다.

### 6.2 parser/PDF reconciliation

페이지별 최종 판단은 다음과 같다.

| Parser geometry | PDF geometry | 결과 |
|---|---|---|
| ABSENT | VALID | PDF geometry 사용 |
| VALID | VALID + 일치 | PDF geometry 사용 |
| VALID | VALID + 불일치 | `PARSER_PDF_PAGE_DIMENSIONS_MISMATCH` |
| INVALID | VALID | `PARSER_PAGE_DIMENSIONS_INVALID` |
| any | unavailable | `PAGE_DIMENSIONS_UNAVAILABLE` |

parser dimensions는 canonical source가 아니라 **검증 대상**이다. 최종 `NormalizedParserContribution.page_dimensions`에는 항상 PDF에서 검증된 width/height를 기록한다.

## 7. 비교 허용오차

parser와 PDF dimensions의 비교 tolerance는 `0.5 pt`로 한다.

페이지별 조건:

```text
abs(parser_width  - pdf_width)  <= 0.5
abs(parser_height - pdf_height) <= 0.5
```

둘 중 하나라도 초과하면 mismatch다.

이 tolerance는 기존 bbox normalization의 boundary tolerance와 동일한 magnitude를 사용하여 소수점 serialization 또는 parser rounding 때문에 정상 문서를 차단하지 않으면서 의미 있는 geometry drift는 허용하지 않는다.

비율 기반 tolerance 또는 자동 scaling은 사용하지 않는다. geometry mismatch를 자동 보정하면 잘못된 좌표가 정상값처럼 저장될 수 있기 때문이다.

## 8. Page Count 검증

parser의 `number of pages`/`page_count` 또는 element-derived page count와 원본 PDF page count도 ingestion 전에 비교한다.

- 같으면 계속 진행
- 다르면 `PARSER_PDF_PAGE_COUNT_MISMATCH`

parser page count가 선언되지 않았지만 elements로 계산 가능한 경우 기존 동작을 유지하되, 최종 계산값을 PDF page count와 비교한다.

PDF page count를 확인할 수 없으면 page geometry 자체도 확정할 수 없으므로 ingestion을 진행하지 않는다.

## 9. ODL Adapter 변경

`OpenDataLoaderJsonAdapter.parse()`의 순서를 다음과 같이 변경한다.

```text
1. parser artifact JSON 읽기
2. parser source filename binding 검증
3. raw elements 로드
4. parser page count 결정
5. 원본 PDF geometry 전체 읽기
6. parser/PDF page count 비교
7. 각 page의 parser geometry 상태 추출
8. parser/PDF geometry reconciliation
9. canonical PDF geometry로 PageDimensions 생성
10. 같은 canonical geometry로 bbox normalization
11. NormalizedParserContribution 생성
```

중요한 invariant:

```text
PageDimensions used for bbox normalization
== PageDimensions stored in evidence DB
== geometry later expected by Review Workspace
```

A4 상수와 silent fallback은 완전히 삭제한다.

## 10. Error / Reason Code 계약

최소 reason code는 다음과 같이 고정한다.

| Code | 의미 | 처리 |
|---|---|---|
| `PAGE_DIMENSIONS_UNAVAILABLE` | PDF page box에서 canonical geometry를 얻을 수 없음 | fail-closed |
| `PARSER_PAGE_DIMENSIONS_INVALID` | parser가 명시적으로 잘못된 dimension 제공 | fail-closed |
| `PARSER_PDF_PAGE_DIMENSIONS_MISMATCH` | parser와 PDF dimension이 tolerance 밖에서 불일치 | fail-closed |
| `PARSER_PDF_PAGE_COUNT_MISMATCH` | parser와 원본 PDF page count 불일치 | fail-closed |
| `PAGE_ROTATION_INVALID` | canonical orientation을 정할 수 없는 rotation | fail-closed |
| `PAGE_RENDER_GEOMETRY_MISMATCH` | DB page geometry와 verified page-image geometry 불일치 | Review Workspace render 거부 |

이슈 #63의 silent corruption 위험을 고려하여 mismatch는 warning-only로 진행시키지 않는다.

예외 메시지는 기존 저장소 패턴과 동일하게 reason code를 문자열에 포함하여 CLI와 테스트에서 deterministic하게 확인할 수 있게 한다.

이 이슈에서는 source state enum을 추가하지 않는다. geometry 오류는 parser-ready source를 정상 ingest할 수 없는 상태이므로 현재 importer boundary에서 명시적 실패로 처리한다. 향후 CLI에서 구조화된 source report가 필요하면 별도 이슈에서 error-to-readiness projection을 추가할 수 있다.

## 11. Evidence DB 계약

DB schema는 변경하지 않는다.

현재 `pages`에 저장되는 다음 값의 의미만 엄격히 한다.

```text
pages.width  = canonical effective PDF page-box width
pages.height = canonical effective PDF page-box height
```

잘못되거나 추정된 geometry는 DB에 저장하지 않는다.

bbox는 기존 canonical `[left, bottom, right, top]` 형식을 유지하고 `NormalizedParserContribution`의 validation을 그대로 통과해야 한다.

따라서 기존 snapshot/retrieval schema와 migration은 필요하지 않다.

## 12. Review Workspace Geometry 검증

현재 renderer는 verified page-image metadata의 `pdf_width`/`pdf_height`를 읽어 SVG `viewBox`와 citation bounds 검증에 사용한다.

Issue #63 해결 후에는 renderer가 page-image metadata만 신뢰하지 않고 evidence DB의 canonical geometry와도 일치하는지 확인해야 한다.

### 12.1 Builder 변경

`review_packet/builder.py`의 citation resolution에서 citation이 속한 `pages` row의 width/height를 함께 조회한다.

view model의 citation 또는 page asset identity에 다음 canonical geometry를 포함한다.

```text
page_width
page_height
```

같은 revision/page를 공유하는 citations는 같은 geometry를 가져야 한다.

### 12.2 Renderer 변경

`html_renderer.py`에서 verified page-image metadata를 읽은 뒤 다음을 검사한다.

```text
abs(db_page_width  - page_image.pdf_width)  <= 0.5
abs(db_page_height - page_image.pdf_height) <= 0.5
```

불일치하면 `PAGE_RENDER_GEOMETRY_MISMATCH`로 HTML rendering을 중단한다.

일치한 경우에만 해당 geometry로:

- bbox bounds 검사
- SVG `viewBox`
- bottom-left -> SVG y 변환
- overlay rect

을 생성한다.

이 검사는 ingestion 후 page-image generation 또는 cache가 잘못된 경우에도 overlay가 정상처럼 보이는 것을 막는 두 번째 방어선이다.

## 13. 테스트 전략

구현은 TDD 순서로 진행한다. 첫 단계는 현재 A4 fallback이 문제임을 재현하는 failing tests다.

### 13.1 PDF fixture factory

테스트에서 임의 byte string을 "PDF"처럼 사용하는 ingest fixture를 geometry 검증 경로에 사용하지 않는다.

`pypdf.PdfWriter`를 사용하여 실제 유효한 최소 PDF를 생성하는 helper를 추가한다.

지원 fixture:

- A4 portrait: 약 `595 × 842`
- A4 landscape: `842 × 595`
- A3 portrait: 약 `842 × 1191`
- A3 landscape: 약 `1191 × 842`
- custom size: 예 `1000 × 700`
- CropBox가 MediaBox보다 작은 page
- non-zero CropBox origin
- multi-page mixed sizes

정확한 test expectation은 fixture 생성 시 지정한 point 값을 사용하며 ISO nominal mm를 재계산해서 비교하지 않는다.

### 13.2 Unit tests — PDF geometry resolver

신규 `tests/unit/parsing/test_pdf_page_geometry.py`에서 검증한다.

- CropBox width/height 계산
- MediaBox fallback
- non-zero lower-left origin 처리
- portrait/landscape 유지
- multi-page mixed size
- invalid geometry fail-closed
- rotation normalization/validation

### 13.3 Unit tests — ODL adapter

`tests/unit/parsing/test_odl_adapter.py`를 확장한다.

- parser dimensions 있음 + PDF와 일치
- parser dimensions 없음 + PDF geometry 사용
- parser dimensions mismatch
- parser dimension zero
- parser dimension negative
- parser dimension NaN/infinity를 JSON/runtime boundary에서 거부
- parser/PDF page count mismatch
- 기존 stable element IDs 유지

### 13.4 Unit tests — bbox regression

`tests/unit/parsing/test_coordinate_normalization.py` 및 신규 ODL integration-style unit test에서 검증한다.

- 기존 golden bbox 좌표 유지
- A3 landscape bbox가 A4 bounds로 잘못 reject되지 않음
- 실제 page bounds 밖 bbox는 계속 reject
- 0.5pt 이내 경계 clamp 동작 유지

### 13.5 Source batch importer tests

현재 `test_source_batch_importer.py`의 실제 ingest path에 사용되는 synthetic invalid PDF bytes는 valid PDF fixture로 교체한다.

단, PDF 내용을 열지 않는 prepare/hash/dedup 전용 테스트는 기존 arbitrary bytes를 유지할 수 있다. 테스트 목적과 geometry parsing 의존성을 불필요하게 결합하지 않는다.

검증 항목:

- missing parser dimensions라도 valid source PDF가 있으면 ingest 성공
- evidence `pages.width/height`가 PDF fixture와 일치
- mismatch 시 output DB가 생성되지 않음
- geometry failure가 empty/partial evidence DB를 남기지 않음

### 13.6 Review Workspace integration tests

`tests/integration/review_packet/test_html_renderer.py`를 확장한다.

- DB/citation canonical geometry와 page-image metadata 일치 시 기존 overlay 유지
- A3 landscape `viewBox`와 rect 정확성
- custom-size `viewBox` 정확성
- DB/page-image mismatch 시 `PAGE_RENDER_GEOMETRY_MISMATCH`
- bbox가 verified bounds 밖이면 기존 rejection 유지

기존 A4 print CSS의 `@page size: A4`는 인쇄 레이아웃 설정이며 source PDF geometry와 별개이므로 이 이슈에서 변경하지 않는다.

## 14. 회귀 방지 Invariants

다음 조건을 테스트로 고정한다.

1. `595 × 842`라는 값은 실제 PDF 또는 parser fixture가 그 크기를 명시할 때만 나타날 수 있다.
2. parser dimension이 없다는 이유만으로 특정 용지 크기를 생성하지 않는다.
3. bbox normalization에 사용한 width/height와 DB에 저장된 width/height가 동일하다.
4. Review Workspace overlay geometry는 DB geometry와 verified page-image geometry가 일치할 때만 사용한다.
5. geometry mismatch는 자동 scaling으로 복구하지 않는다.
6. failure path에서 partial evidence DB를 정상 결과로 남기지 않는다.
7. 기존 정상 A4 golden bbox는 동일 좌표를 유지한다.

## 15. 예상 변경 파일

### 신규

- `src/ansim_review/parsing/pdf_page_geometry.py`
- `tests/unit/parsing/test_pdf_page_geometry.py`
- 필요 시 `tests/helpers/pdf_fixtures.py`

### 수정

- `src/ansim_review/parsing/odl_source.py`
- `src/ansim_review/parsing/odl_adapter.py`
- `src/ansim_review/review_packet/builder.py`
- `src/ansim_review/review_packet/html_renderer.py`
- `tests/unit/parsing/test_odl_adapter.py`
- `tests/unit/parsing/test_coordinate_normalization.py`
- `tests/unit/parsing/test_source_batch_importer.py`
- `tests/integration/review_packet/test_html_renderer.py`

실제 구현 중 page-image metadata producer가 별도 모듈에 있는 것이 확인되면 그 모듈은 동일 geometry contract를 적용하는 범위 안에서만 수정한다. renderer 또는 parser와 무관한 리팩터링은 포함하지 않는다.

## 16. 구현 단계 경계

구현 계획은 다음 순서로 나눈다.

1. valid PDF fixture factory + failing geometry tests
2. PDF geometry resolver 구현
3. A4 fallback 제거 + parser dimension 상태 구분
4. ODL adapter PDF/parser reconciliation
5. source batch ingest regression 및 DB geometry 검증
6. Review Workspace DB/page-image geometry cross-check
7. A4/A3/landscape/custom/CropBox regression suite
8. full verification

각 단계는 독립적인 테스트 가능한 boundary를 가진다. parser geometry와 Review Workspace 변경을 한 번에 큰 patch로 만들지 않는다.

## 17. 완료 기준

Issue #63은 다음 조건을 모두 만족할 때 해결된 것으로 본다.

- parser page dimensions 누락 시 A4 고정값으로 silent fallback하지 않는다.
- 원본 PDF의 effective CropBox/MediaBox에서 실제 width/height를 읽는다.
- portrait/landscape/A3/custom-size PDF에서 bbox가 canonical geometry로 정규화된다.
- parser/PDF dimensions mismatch를 deterministic reason code로 탐지한다.
- parser/PDF page count mismatch를 탐지한다.
- malformed/zero/negative/non-finite parser dimensions를 정상 누락값으로 취급하지 않는다.
- geometry를 확인할 수 없으면 `PAGE_DIMENSIONS_UNAVAILABLE`로 fail-closed 한다.
- evidence DB의 page dimensions가 canonical PDF geometry와 일치한다.
- Review Workspace가 DB geometry와 verified page-image geometry가 일치할 때만 overlay를 렌더링한다.
- A4/A3/landscape/custom-size/CropBox fixtures가 자동 테스트에 포함된다.
- 기존 bbox golden case가 회귀하지 않는다.
- targeted tests PASS
- full `pytest` PASS
- `ruff` PASS
- `mypy` PASS
- `compileall` PASS

GitHub Actions가 저장소 운영상 사용 불가능하거나 과금 차단 상태인 경우에는 저장소의 기존 수동 검증 절차를 따르되, 자동화된 test command 자체의 PASS 증거를 남긴다.

## 18. 설계 결론

Issue #63은 단순히 `595 × 842` 상수를 `pypdf` 값으로 치환하는 hotfix로 처리하지 않는다.

원본 PDF geometry를 canonical source로 두고 parser와 교차 검증하며, 같은 geometry가 evidence DB와 Review Workspace까지 유지되는 **single geometry contract**로 해결한다.

이 방식은 A3/대형 도면/custom page box에서의 silent bbox corruption을 차단하면서도 현재 evidence schema와 bbox format은 유지하므로 변경 범위를 P1 문제 해결에 한정한다.
