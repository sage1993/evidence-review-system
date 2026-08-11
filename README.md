# Evidence Review System

Codex Desktop에 PDF와 질문을 주면, PDF 근거를 찾아 검토용 HTML 화면까지 만들어 주는 오프라인 문서 검토 도구입니다.

사용자는 복잡한 JSON이나 명령어를 직접 작성하지 않습니다. 아래 두 단축어만 기억하면 됩니다.

## 1. 준비물과 설치

필요한 것은 다음 네 가지입니다.

- Codex Desktop
- Evidence Review System 폴더(소스 코드 또는 배포 ZIP)
- 검토할 PDF 파일
- PDF를 읽을 수 있는 로컬 parser 도구(OpenDataLoader PDF)

배포 ZIP을 받았다면 압축을 풀고 그 폴더를 Codex Desktop에서 엽니다. 소스 코드로 설치하는 경우에는 PowerShell에서 다음을 한 번 실행합니다.

```powershell
git clone https://github.com/sage1993/evidence-review-system.git
Set-Location evidence-review-system
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### Python 의존성과 오프라인 실행

- 런타임 Python 패키지로 `pypdf>=5,<6`를 사용합니다. PDF 페이지 수와 페이지 geometry를 원본 PDF에서 검증하는 데 사용됩니다.
- `.[dev]`에는 런타임 의존성에 더해 `pytest`, `mypy`, `ruff` 같은 개발·검증 도구가 포함됩니다. 일반 실행에 개발 도구는 필요하지 않습니다.
- 여기서 **오프라인 실행**은 프로그램 실행 중 인터넷 검색이나 외부 API 호출이 필요하지 않다는 의미입니다. 제3자 Python 패키지가 전혀 필요 없다는 의미는 아닙니다.
- 인터넷이 차단된 환경에 새로 설치할 때는 `pypdf`를 포함한 필요한 wheel 또는 패키지를 미리 준비해야 합니다.

PDF와 생성된 근거 자료는 사용자의 컴퓨터 안에서 처리됩니다.

## 2. PDF 파싱하는 방법

Codex Desktop에서 PDF를 첨부하거나 파일 경로를 알려 주고 다음처럼 말합니다.

```plaintext
$ERS_PDF 이 PDF 파일 파싱해줘
```

그러면 Codex가 자동으로 다음 작업을 진행합니다.

- 원본 PDF를 보존하고 파일 정보와 SHA-256 해시를 기록합니다.
- PDF의 글자·표·페이지 위치·이미지를 parser로 읽습니다.
- parser 결과와 PDF가 제대로 연결됐는지 확인합니다.
- 검색 가능한 근거 데이터베이스를 만듭니다.

원본 PDF나 parser 결과를 덮어쓰지 않으며, parser 결과가 없거나 PDF와 맞지 않으면 성공한 것처럼 넘어가지 않고 필요한 조치를 알려 줍니다. 도면처럼 사람의 확인이 필요한 자료는 자동으로 확정하지 않고 확인 대기 상태로 남깁니다.

파싱이 끝나면 Codex가 “다음 질문을 해도 되는지”를 알려 줍니다. 준비가 되지 않은 경우에는 먼저 부족한 파일이나 확인 사항을 안내합니다.

## 3. 질문하는 방법

파싱 완료 메시지를 확인한 뒤, 검토하려는 내용을 자연어로 물어봅니다.

```plaintext
$ERS_REVIEW 이 사업이 해당 기준을 충족하는지 검토해줘
```

질문은 구체적으로 쓸수록 좋습니다.

```plaintext
$ERS_REVIEW 이 사업의 주차 기준 충족 여부를 근거 페이지와 함께 검토해줘
```

Codex는 파싱된 PDF 근거를 검색하고, 필요한 경우 승인된 계산식과 규칙을 실행한 뒤, 검토 답변과 HTML 화면을 함께 준비합니다. 계산값을 대화 중에 임의로 계산하거나 근거가 없는 내용을 채우지 않습니다.

파싱이 먼저 끝나지 않았거나 필요한 근거가 없으면 답변을 억지로 만들지 않고 `$ERS_PDF`를 먼저 실행하거나 추가 자료가 필요한 이유를 알려 줍니다.

## 4. 결과 확인

질문 처리가 끝나면 Codex가 로컬 검토용 `review.html`을 기본 브라우저로 엽니다. 브라우저가 자동으로 열리지 않으면 Codex가 표시한 로컬 주소를 클릭하면 됩니다.

HTML 화면에서는 보통 다음을 확인할 수 있습니다.

- **검토 요약:** 기준 충족, 미충족, 보류 또는 추가 확인 필요 상태
- **근거:** 어떤 PDF의 몇 페이지에서 나온 내용인지와 원문 인용
- **계산·규칙:** 사용한 입력값, 공식, 규칙 버전과 결과
- **주의사항:** 누락 자료, 충돌하는 근거, 사람 확인이 필요한 항목

근거 항목을 따라가 원본 PDF의 해당 페이지를 직접 확인하고, 계산에 사용된 입력값과 예외 사항을 검토합니다. 필요하면 HTML 화면을 검토 회의나 내부 확인 자료로 공유할 수 있습니다.

`READY_FOR_HUMAN_REVIEW`는 “사람이 확인할 준비가 됨”이라는 뜻이지 자동 승인이라는 뜻이 아닙니다. 최종 승인·적합·부적합 판단은 HTML과 원본 PDF를 확인한 사람이 별도로 기록합니다.

## 잘 안 될 때

- **parser 결과가 없다고 나올 때:** OpenDataLoader PDF parser를 설치·실행할 수 있는지 확인한 뒤 `$ERS_PDF`를 다시 실행합니다.
- **도면 확인이 필요하다고 나올 때:** 도면의 숫자나 위치를 사람이 원본에서 확인해야 합니다. 확인 전에는 계산에 사용되지 않습니다.
- **근거가 부족하다고 나올 때:** 질문을 더 구체적으로 쓰거나 기준 PDF와 검토 대상 PDF를 모두 첨부합니다.
- **HTML이 열리지 않을 때:** Codex가 보여 준 `127.0.0.1` 로컬 주소를 브라우저에서 열고, `review.html`이 생성되었는지 확인합니다.

## 개발자용 문서

내부 파서·manifest·SQLite·규칙 엔진을 직접 다뤄야 할 때만 다음 문서를 참고하세요.

- [Source Batch v2 및 Parser Registry](docs/SOURCE_BATCH_V2.md)
- [검토자 작업 절차](docs/REVIEWER_WORKFLOW.md)
- [Codex 작업 절차](docs/CODEX_WORKFLOW.md)
- [오프라인 실행 경계](docs/OFFLINE_EXECUTION.md)
- [PDF 단계별 스킬](skills/README.md)
- [Legacy document lineage migration](docs/LEGACY_LINEAGE_MIGRATION.md)

레거시 DB의 lineage를 별도 파일로 마이그레이션해야 할 때만 다음 명령을 사용합니다. 일반 사용자는 실행할 필요가 없습니다.

```powershell
evidence-review evidence migrate-lineage `
  --source 01_database/evidence.sqlite `
  --manifest migration/legacy-lineage-manifest.json `
  --output migrated/evidence.sqlite
```
