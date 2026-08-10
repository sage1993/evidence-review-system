# PDF-to-Grist Skill Set

이 저장소에는 두 가지 사용 방식이 있습니다.

## Codex Desktop에서 가장 쉬운 사용법

사용자에게는 다음 두 단축어만 안내합니다.

- `$ERS_PDF 이 PDF 파일 파싱해줘` → [`ers-pdf/SKILL.md`](ers-pdf/SKILL.md)
- `$ERS_REVIEW 이 사업이 해당 기준을 충족하는지 검토해줘` → [`ers-review/SKILL.md`](ers-review/SKILL.md)

두 스킬은 내부 5단계 처리와 로컬 HTML 검토 화면을 자동으로 연결합니다. PDF 파싱이 준비되지 않았거나 근거가 부족하면 성공한 것처럼 진행하지 않습니다.

## 내부 단계 스킬

개발자나 운영자가 처리 단계를 직접 점검할 때만 다음 순서를 사용합니다.

1. `preserving-and-parsing-pdfs`
2. `structuring-pdf-content-and-visuals`
3. `cleaning-pdf-derived-data`
4. `building-and-exporting-grist-databases`
5. `validating-pdf-database-workflows`

## 공통 원칙

- 원본 PDF와 raw parser output을 덮어쓰지 않습니다.
- 원시 근거와 정규화·요약·해석 자료를 분리합니다.
- 파생 데이터에는 문서, 페이지, 좌표, source element ID 또는 source path를 남깁니다.
- parser 결과를 법적 해석이나 사실 확정으로 취급하지 않습니다.
- `READY_FOR_HUMAN_REVIEW`는 사람 검토 준비 상태이며 최종 승인 결과가 아닙니다.
