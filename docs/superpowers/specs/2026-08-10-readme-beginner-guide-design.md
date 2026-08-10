# 비개발자용 README 사용 안내서 설계

## 목적

GitHub README만 읽은 비개발자가 Evidence Review System의 역할을 이해하고, PDF와 필요한 parser artifact를 준비한 뒤, 기본 source-batch 및 review-run 흐름을 따라갈 수 있도록 한다.

## 독자와 성공 기준

- 독자는 Python·JSON·CLI에 익숙하지 않은 실무 사용자다.
- 설치가 필요한 이유와 준비해야 할 파일을 먼저 이해할 수 있어야 한다.
- 명령을 복사해 실행할 수 있고, 각 명령이 만드는 결과 파일을 알 수 있어야 한다.
- `READY_FOR_HUMAN_REVIEW`가 승인 완료가 아니라 사람 검토 대기라는 점을 오해하지 않아야 한다.
- 오류 상태가 나왔을 때 원인과 다음 행동을 찾을 수 있어야 한다.

## README 구성

1. 한 문장 소개와 중요한 제한사항
2. 처음 사용하는 사람을 위한 빠른 이해: 입력·처리·출력
3. 준비물과 설치
4. 폴더 만들기와 PDF/parser artifact 배치
5. `source-batch prepare`로 사전 점검
6. `source-batch ingest`로 검색 DB 만들기
7. 검색·계산·검토 Run의 순서와 결과 파일
8. 도면 PDF가 별도 확인 절차를 거치는 이유
9. 상태·오류별 해결 방법
10. 안전 원칙, 고급 문서, 개발자 검증 명령

## 표현 원칙

- 최초 설명에서는 전문 용어 대신 “원본 PDF”, “검색용 DB”, “사람 확인이 필요한 도면 값”처럼 역할 중심 표현을 사용한다.
- 실제 명령어·파일명·상태값은 정확성을 위해 원문을 유지하고 바로 옆에 쉬운 뜻을 설명한다.
- 예시는 Windows PowerShell을 기준으로 작성하되, 경로는 사용자가 바꿔야 한다는 점을 명시한다.
- 사람이 최종 판단한다는 경계와 원본 보존 원칙은 눈에 잘 띄게 유지한다.
- 릴리스 attestation, legacy migration, parser registry 내부 구현 등 고급 내용은 본문 흐름을 방해하지 않도록 후반부 링크로 둔다.

## 변경 범위

- 수정: `README.md`
- 추가: 이 설계 문서
- 기존 상세 문서와 CLI 동작은 변경하지 않는다.
- 명령 예시는 `src/ansim_review/cli_parser.py`에 등록된 실제 명령만 사용한다.

## 검증

- README의 Markdown 명령과 링크를 정적으로 검토한다.
- `evidence-review documentation validate`를 새 출력 경로로 실행한다.
- 문서 변경이므로 전체 테스트와 정적 검증은 저장소 지침에 따라 실행한다.
