# Evidence Review System Skills

이 저장소의 현재 사용자용 Codex 진입점은 두 개입니다.

- `$ERS_PDF 이 PDF 파일 파싱해줘` → [`ers-pdf/SKILL.md`](ers-pdf/SKILL.md)
- `$ERS_REVIEW 이 사업이 해당 기준을 충족하는지 검토해줘` → [`ers-review/SKILL.md`](ers-review/SKILL.md)

## `$ERS_PDF`

PDF 준비 단계는 다음 책임을 가집니다.

- 원본 PDF와 SHA-256 보존
- parser output 및 source binding 검증
- parser warnings/reproducibility 확인
- source-batch v2 준비/검증
- 검색 가능한 `evidence.sqlite` 생성
- revision 단위 verified page-image cache 준비
- 도면 등 사람 확인이 필요한 자료를 확인 전 계산·규칙 입력으로 사용하지 않음

## `$ERS_REVIEW`

모든 질문은 하나의 정식 검토 흐름으로 처리합니다.

```text
질문
→ 로컬 근거 검색
→ formal review request
→ Track A 작성/검증
→ Track B 독립 감사/검증
→ final-review-packet.json
→ Review Workspace
→ 사람 결정
```

사용자가 query JSON, Track handoff metadata, packet hash, timestamp를 직접 작성하도록 요구하지 않습니다.

## 공통 원칙

- 원본 PDF와 raw parser output을 덮어쓰지 않습니다.
- 원시 근거와 정규화·요약·해석 자료를 분리합니다.
- 문서, revision, 페이지, 좌표, source hash를 유지합니다.
- parser 결과를 법적 해석이나 사실 확정으로 취급하지 않습니다.
- 계산은 승인된 Math Engine 결과를 사용합니다.
- 규칙 판정은 승인된 Rule Engine 결과를 사용합니다.
- `READY_FOR_HUMAN_REVIEW`는 사람 검토 준비 상태이며 최종 승인 결과가 아닙니다.
- 실행하지 않은 검증은 `PASS`가 아니라 `NOT_RUN`으로 기록합니다.

과거 PDF-to-Grist 단계형 skill은 현재 ERS 제품 경로가 아니며 active skill set에서 제거됩니다. 과거 내용이 필요한 경우 Git history를 사용합니다.
