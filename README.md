# Evidence Review System

Evidence Review System (ERS) is an **offline, evidence-first document review runtime** for turning user-provided PDFs into traceable local evidence and running every question through a formal review pipeline.

The project is designed for cases where a result must remain tied to the original document, page, coordinates, deterministic calculations/rules, and an explicit human decision rather than a free-form model answer.

## What it does

```text
PDF
→ immutable parser artifacts
→ source/hash binding
→ evidence.sqlite
→ external AI Question Planner
→ fail-closed QuestionPlan validation
→ deterministic retrieval
→ formal review request
→ Track A
→ independent Track B audit
→ immutable final-review-packet.json
→ Review Workspace
→ separate append-only human decision
```

The Question Planner decides **what evidence to look for**, not the answer. Project Python code does not call a model API; Codex or another external AI supplies a bounded QuestionPlan at a validated file handoff. Planner-inferred legal citations are search hypotheses only until retrieved evidence supports them.

The runtime does not make the final human decision. `READY_FOR_HUMAN_REVIEW` means that the evidence package is ready to inspect; it does **not** mean approved, compliant, or correct.

---

## 설치방법

아래 절차는 **Windows에서 Codex Desktop과 함께 ERS를 사용하는 일반 사용자 기준**입니다. 개발용 테스트 도구는 설치하지 않습니다.
이 깃허브 주소 복사해서 Codex에게 설치 해달라고 하면 알아서 설치해줍니다.

### 준비물

- Windows 10 또는 Windows 11
- **Python 3.13**
- Git 또는 GitHub의 **Download ZIP** 기능
- Codex Desktop
- PDF 파싱이 필요한 경우 지원되는 로컬 parser — 기본 지원 parser는 **OpenDataLoader PDF (`opendataloader-pdf`)**

> ERS의 공식 Python 지원 범위는 `>=3.13,<3.14`입니다. Python 3.11/3.12는 현재 지원 대상이 아닙니다.

### 1. Python 3.13이 설치되어 있는지 확인합니다

PowerShell을 열고 다음 명령을 실행합니다.

```powershell
py -3.13 --version
```

예시:

```text
Python 3.13.x
```

`Requested Python version (3.13) not installed` 또는 비슷한 오류가 나오면 Python 3.13을 먼저 설치해야 합니다.

### 2. ERS 파일을 받습니다

#### 방법 A — Git 사용

PowerShell에서 다음 명령을 실행합니다.

```powershell
git clone https://github.com/sage1993/evidence-review-system.git
Set-Location evidence-review-system
```

#### 방법 B — Git을 사용하지 않는 경우

1. GitHub 저장소 페이지에서 **Code → Download ZIP**을 선택합니다.
2. ZIP 파일의 압축을 풉니다.
3. 압축을 푼 `evidence-review-system` 폴더를 엽니다.
4. 해당 폴더에서 PowerShell을 엽니다.

### 3. 전용 Python 환경을 만들고 ERS를 설치합니다

저장소 폴더에서 다음 명령을 순서대로 실행합니다.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
```

이 방식은 PowerShell의 가상환경 활성화 정책과 관계없이 동작하도록 `.venv` 안의 Python을 직접 사용합니다.

설치가 완료되면 다음 명령으로 확인합니다.

```powershell
.\.venv\Scripts\python.exe -m evidence_review --version
.\.venv\Scripts\python.exe -m evidence_review --help
```

현재 버전에서는 `--version` 결과가 다음과 같이 표시되어야 합니다.

```text
0.2.0
```

### 4. PDF parser를 준비합니다

`$ERS_PDF`로 PDF를 새로 파싱하려면 ERS 외에 지원되는 로컬 parser가 필요합니다. 현재 기본 지원 parser는 **OpenDataLoader PDF (`opendataloader-pdf`)**입니다.

ERS 자체는 parser가 없는 상태를 정상 파싱 완료로 처리하지 않습니다. 이미 검증된 parser artifact를 사용하는 경우에는 해당 artifact와 원본 PDF의 source hash가 일치해야 합니다.

parser 설치 및 실행 환경은 ERS와 별개이므로, `$ERS_PDF` 실행 시 Codex가 parser를 찾지 못하면 먼저 parser 설치 상태를 해결해야 합니다.

### 5. Codex Desktop에서 저장소 폴더를 엽니다

Codex Desktop에서 방금 설치한 `evidence-review-system` 폴더를 작업 폴더로 엽니다.

이 저장소의 사용자용 Codex 진입점은 두 개입니다.

```text
$ERS_PDF 이 PDF 파싱해줘
$ERS_REVIEW <검토 질문>
```

먼저 PDF를 준비한 뒤 검토 질문을 실행합니다.

### 6. 설치 확인이 안 될 때

- **`py -3.13`을 찾지 못함** → Python 3.13 설치 여부를 확인합니다.
- **`git`을 찾지 못함** → Git을 설치하거나 GitHub의 **Download ZIP** 방식을 사용합니다.
- **`No module named evidence_review`** → 현재 폴더가 저장소 루트인지 확인한 뒤 `\.venv\Scripts\python.exe -m pip install .`을 다시 실행합니다.
- **`$ERS_PDF`에서 parser를 찾지 못함** → OpenDataLoader PDF 등 지원 parser 설치 상태를 확인합니다.
- **설치는 됐지만 Codex가 프로젝트를 찾지 못함** → Codex Desktop에서 `evidence-review-system` 저장소 폴더 자체를 작업 폴더로 열었는지 확인합니다.

개발·테스트 환경까지 구성하려는 경우 아래 [개발자용 설치 및 검증 환경](#개발자용-설치-및-검증-환경)을 참고합니다.

---

## 사용방법

일반 사용자는 QuestionPlan이나 Track A/B 중간 JSON을 직접 만들거나 수정할 필요가 없습니다. **Codex Desktop에서 PDF를 준비한 뒤 아래 두 단축어를 사용하는 것이 기본 흐름**입니다.

```text
$ERS_PDF 이 PDF 파싱해줘
$ERS_REVIEW <검토 질문>
```

### 1. PDF를 준비합니다

검토할 PDF를 Codex Desktop 대화에 첨부하거나 로컬 파일 경로를 알려준 뒤 다음처럼 요청합니다.

```text
$ERS_PDF 이 PDF 파싱해줘
```

ERS는 이 단계에서 다음 작업을 준비·검증합니다.

- 원본 PDF와 파일 해시 보존
- parser 결과와 원본 PDF의 연결 확인
- parser 경고 및 재현성 확인
- 검색 가능한 근거 DB(`evidence.sqlite`) 생성
- 근거 페이지를 바로 확인할 수 있는 검증된 page image 준비

**PDF 준비가 정상 완료되기 전에는 질문 검토 단계로 넘어가지 않습니다.** parser 결과가 없거나 원본과 parser 결과의 연결이 맞지 않으면 성공으로 처리하지 않습니다. 도면처럼 사람 확인이 필요한 자료도 확인 전에는 계산이나 규칙 판정의 확정 입력으로 사용하지 않습니다.

### 2. 검토할 내용을 질문합니다

PDF 준비가 끝나면 평소 질문하듯 `$ERS_REVIEW` 뒤에 검토 내용을 작성합니다.

```text
$ERS_REVIEW 이 사업의 주차 기준 충족 여부를 근거 페이지와 함께 검토해줘
```

```text
$ERS_REVIEW 이 문서에서 용적률 완화 조건과 예외사항을 검토해줘
```

```text
$ERS_REVIEW 3페이지와 17페이지의 기준이 서로 충돌하는지 검토해줘
```

모든 질문은 같은 **정식 검토 파이프라인**을 사용합니다. 간단한 질문이라고 해서 근거 확인을 생략하는 별도 빠른 답변 모드는 사용하지 않습니다.

```text
질문
→ AI Question Planner
→ QuestionPlan 검증
→ 로컬 근거 검색
→ Track A 근거 검토
→ Track B 독립 감사
→ 결과 검증
→ final-review-packet.json
→ Review Workspace
→ 사람 최종 확인
```

Question Planner는 질문의 사실·숫자·부정조건·예외를 보존하면서 검토 쟁점과 최소 검색 요청을 구조화합니다. 이 단계에서 답변, 적합성 판정, confidence를 만들 수 없습니다. 검증되지 않은 Plan은 retrieval 단계로 넘어가지 않습니다.

사용자는 `question-plan-output`, review request, Track A/B JSON, packet 같은 중간 파일을 손으로 작성하지 않습니다. Codex가 정해진 handoff를 따라 처리하고, ERS runtime이 단계별 결과를 검증합니다.

Planner 실패는 `PLANNER_FAILED`, 유효한 Plan으로 검색했지만 근거가 없는 경우는 `RETRIEVAL_NO_EVIDENCE`, 최종 검토에서 근거가 충분하지 않은 경우는 기존 `ABSTAIN`으로 서로 구분됩니다.

### 3. Review Workspace에서 결과를 확인합니다

정식 검토가 완료되면 Review Workspace에서 결과를 확인합니다. 기본 화면은 개발자 정보보다 실제 검토에 필요한 내용을 우선합니다.

1. **검토 결과** — 현재 상태와 간단한 결론
2. **판단 근거** — 인용 원문, 문서, 페이지, 위치(bbox), 검증된 PDF 페이지 이미지
3. **추가 확인** — 누락·충돌·예외·추가 자료가 필요한 경우에만 표시
4. **검토자 의견** — 사람이 최종 결정과 메모를 기록

여러 PDF를 함께 검토한 경우에는 문서와 근거 페이지를 전환하면서 확인할 수 있습니다. 내부 Run ID, hash, evidence ID, confidence 세부값 등은 기본 화면을 복잡하게 만들지 않도록 감사 정보 영역에 보존됩니다.

`READY_FOR_HUMAN_REVIEW`는 **사람이 검토할 자료가 준비되었다는 뜻**입니다. 자동 승인, 법적 적합 판정, 최종 의사결정을 의미하지 않습니다.

### 4. 근거 페이지를 직접 확인합니다

결론만 읽고 끝내지 말고 **판단 근거에 표시된 원문과 PDF 페이지를 함께 확인**하는 것을 기본 사용 방식으로 합니다.

특히 다음 경우에는 `추가 확인` 내용까지 확인해야 합니다.

- 필요한 근거가 부족한 경우
- 서로 다른 문서나 페이지의 내용이 충돌하는 경우
- 예외 조건이 있는 경우
- 계산 또는 Rule Engine 입력이 부족한 경우
- 시스템이 충분한 근거를 확보하지 못해 판단을 보류한 경우

### 5. 최종 결정과 의견을 기록합니다

보호된 localhost Review Workspace에서는 보통 아래 두 가지만 입력하면 됩니다.

- **결정**
- **검토 의견**

| 화면 표시 | 의미 |
|---|---|
| 내용 확인 완료 | 표시된 근거와 검토 내용을 확인함 |
| 내용에 오류 있음 | 결과 또는 근거에 오류가 있어 수정이 필요함 |
| 조건부 확인 | 조건 또는 전제가 충족되는 범위에서 확인함 |
| 추가 자료 필요 | 현재 자료만으로 결정하기 어려움 |

결정 기록은 machine review 결과와 분리된 **append-only 기록**으로 저장됩니다. 이미 기록된 결정을 덮어쓰지 않고, 필요한 경우 추가 결정을 새 기록으로 남깁니다.

### 6. `review.html`을 파일로 보관할 수 있습니다

각 검토 결과의 `review.html`은 독립적인 보관용 HTML입니다. 다른 사람에게 검토 근거 화면을 전달하거나 나중에 다시 확인하는 용도로 사용할 수 있습니다.

다만 `review.html`을 파일로 직접 열면 보호 서버와 연결되지 않으므로 **결정을 서버에 바로 저장할 수 없습니다.** 이 경우 화면의 **결정 JSON 다운로드** 기능을 사용한 뒤 승인된 import 경로로 기록할 수 있습니다.

비개발자 사용자는 일반적으로 Codex Desktop에서 보호된 Review Workspace를 열어 결정하는 방식을 권장합니다.

### 7. 잘 안 될 때 확인할 항목

- **PDF 파싱이 완료되지 않음** → 지원 parser 설치 여부와 parser 결과가 원본 PDF와 정상 연결되어 있는지 확인합니다.
- **Question Planner가 중단됨** → `PLANNER_FAILED` reason과 `QUESTION_PLANNER_INSTRUCTIONS.md` 계약을 확인합니다.
- **검색 결과가 없음** → 유효 Plan 이후 `RETRIEVAL_NO_EVIDENCE`인지 확인하고 임의의 광범위 검색어로 우회하지 않습니다.
- **질문을 시작할 수 없음** → `evidence.sqlite` 등 PDF 준비 단계가 완료되었는지 확인합니다.
- **도면이 근거로 사용되지 않음** → 사람 확인이 필요한 drawing evidence인지 확인합니다.
- **검토가 중간에서 멈춤** → 근거 부족, Track 검증 실패, 규칙/계산 입력 누락 등 화면 또는 Codex가 표시한 차단 사유를 확인합니다.
- **Review Workspace가 열리지 않음** → 검토 결과 생성 자체는 완료됐는지 확인한 뒤 Codex에 `Review Workspace 다시 열어줘`라고 요청합니다.
- **결정 저장이 안 됨** → 보호된 Review Workspace인지, 현재 packet과 reviewer session이 유효한지 확인합니다.

더 자세한 절차가 필요한 경우 [Question planning](docs/question-planning.md), [Codex workflow](docs/CODEX_WORKFLOW.md), [Reviewer workflow](docs/REVIEWER_WORKFLOW.md)를 참고합니다.

---

## Core design principles

- **Evidence first:** preserve the original source bytes, source hash, document/revision/page identity, and bbox/geometry provenance.
- **Validated question planning:** natural-language interpretation is preserved as an immutable, bounded, fail-closed QuestionPlan before retrieval; planner output itself is not evidence.
- **Deterministic authority:** parser records, retrieval, Math Engine results, and approved Rule Engine results are validated before review output is accepted.
- **Independent review tracks:** Track A explains the evidence; Track B audits the validated Track A claims.
- **Human final decision:** machine output remains immutable and human decisions are stored separately as append-only packet-bound records.
- **Fail closed:** missing planner/parser output, stale artifacts, unsafe paths, hash mismatches, invalid rule authority, or release-validation failures stop the workflow.
- **Offline runtime:** project/runtime code requires no remote model/API service. External AI reasoning occurs only at explicit handoffs; the protected Review Workspace uses loopback communication only.

## Requirements

- Python `>=3.13,<3.14`
- Windows is the primary acceptance platform for protected-browser and Review Workspace behavior.
- Codex Desktop is the intended assisted workflow for `$ERS_PDF` / `$ERS_REVIEW`, but the deterministic runtime and CLI are ordinary local Python code.
- A supported local parser such as OpenDataLoader PDF is required before parser-dependent evidence can be evaluated.

Runtime dependencies are declared in `pyproject.toml`.

## 개발자용 설치 및 검증 환경

```powershell
git clone https://github.com/sage1993/evidence-review-system.git
Set-Location evidence-review-system
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

For development and validation:

```powershell
python -m pip install -e ".[dev]"
```

Runtime dependencies are pinned to pypdf>=5,<6, pypdfium2>=5.12,<6, and Pillow>=12,<13.

Canonical entrypoints:

```text
evidence-review --help
python -m evidence_review --help
```

The legacy `ansim-review` name may remain temporarily as a compatibility entrypoint during the `v0.2.0` transition, but `evidence_review` is the canonical public namespace.

## Quick start

Codex Desktop users normally use two shortcuts:

```text
$ERS_PDF 이 PDF 파싱해줘
$ERS_REVIEW <검토 질문>
```

### 1. Prepare PDF evidence

`$ERS_PDF` preserves the source, validates parser/source binding, checks parser warnings/reproducibility, builds source-batch v2, creates searchable `evidence.sqlite`, and prepares verified revision page-image cache artifacts.

Source preparation is not considered successful while required parser output or drawing confirmation is missing.

### 2. Run a formal question

All questions use the formal review flow; there is no separate quick-answer mode.

```text
question
→ external AI Question Planner
→ validated QuestionPlan
→ local evidence retrieval
→ review request
→ Track A output + validation
→ Track B audit + validation
→ final review packet
→ Review Workspace
→ human decision
```

Lower-level CLI commands and the deterministic replay boundary are documented in [Question Planning](docs/question-planning.md), [Codex Workflow](docs/CODEX_WORKFLOW.md), and [Reviewer Workflow](docs/REVIEWER_WORKFLOW.md).

## Review Workspace

The default reviewer surface prioritizes non-developer information:

1. **검토 결과** — status and concise conclusion
2. **판단 근거** — source text/page/bbox and verified page image
3. **추가 확인** — only when missing/conflicting/exception items exist
4. **검토자 의견** — decision and notes

Internal IDs, hashes, confidence factors, and other audit details are retained but should not dominate the default UI.

`review.html` is the standalone archival presentation. Protected localhost mode additionally allows packet-bound append-only human decision persistence.

## Trust and security boundaries

ERS separates:

- external Question Planner authority from evidence authority;
- application-level offline guard;
- optional OS-level network isolation;
- source/evidence integrity;
- protected loopback browser security;
- human review decisions;
- release process attestation and release-output validation.

Passing one boundary does not imply another. For example, a planner-inferred legal anchor is not authority until supported by retrieved evidence, and a human release attestation cannot override a failed release ZIP/hash validation.

See [Question Planning](docs/question-planning.md), [Offline Execution Boundary](docs/OFFLINE_EXECUTION.md), and [Security Policy](SECURITY.md).

## Repository structure

The active tree is intended to contain only current runtime/product/developer material or clearly scoped deterministic fixtures.

```text
src/                         Python runtime
web_runtime/                 installation-free web runtime bootstrap
schemas/                     machine-readable contracts
tests/                       unit/integration/golden fixtures
tests/fixtures/ansim/rules/  ANSIM-specific governed Rule Engine test data
skills/                      current ERS Codex workflow skills
docs/                        current architecture/workflow/governance docs
scripts/                     current operational/developer scripts only
```

Runtime workspaces can still contain their own governed `rules/` tree. The repository itself does not publish ANSIM-specific rule authority as a current product default; those deterministic artifacts are retained only as explicit test fixtures.

Historical issue-specific acceptance output does not need to remain in the active tree because Git history and GitHub Issue/PR history already preserve it.

## Development

Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.

Minimum exact-HEAD validation for the current Python 3.13 support policy:

```powershell
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output <fresh-output>
```

Question Planner changes additionally require the planned-question integration matrix and staged CLI flow tests. Packaging/release changes require wheel/runtime smoke tests and confirmation that the planner instruction template is included in package data. Review Workspace changes require real-browser acceptance; static tests are not a substitute for UI/interaction validation.

If a validation step was not executed, report it as `NOT_RUN` rather than inferring PASS. GitHub Actions availability is tracked separately from reproducible local/manual validation.

## Documentation

- [Question planning](docs/question-planning.md)
- [Codex workflow](docs/CODEX_WORKFLOW.md)
- [Reviewer workflow](docs/REVIEWER_WORKFLOW.md)
- [Offline execution boundary](docs/OFFLINE_EXECUTION.md)
- [Manual acceptance policy](docs/MANUAL_ACCEPTANCE_POLICY.md)
- [Source Batch v2](docs/SOURCE_BATCH_V2.md)
- [Rule activation governance](docs/RULE_ACTIVATION_GOVERNANCE.md)
- [Parser reproducibility](docs/PARSER_REPRODUCIBILITY.md)
- [ERS skills](skills/README.md)
- [Changelog](CHANGELOG.md)

## Contributing and security

- Contributions: [CONTRIBUTING.md](CONTRIBUTING.md)
- Vulnerability reporting: [SECURITY.md](SECURITY.md)

Do not commit proprietary/customer PDFs, parser output derived from restricted documents, user evidence databases, page-image caches, human-decision records, credentials, tokens, private URLs, or private keys.

## Releases

`v0.1.0` is the historical sanitized source-only release. The current public-readiness work targets `v0.2.0`, including repository cleanup, Python 3.13-only support, namespace/CLI consolidation, Review Workspace fixes, runtime-manifest hardening, and reproducible release artifacts.

Release assets should be produced from an accepted exact HEAD and published with SHA-256 values. Generated user workspaces and historical acceptance artifacts are not release assets.

## License

Evidence Review System is licensed under the [Apache License 2.0](LICENSE). Third-party notices remain subject to their own applicable licenses.