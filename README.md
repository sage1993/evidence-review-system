# Evidence Review System

**Evidence Review System(ERS)**은 사용자가 제공한 PDF 및 이미지를 **추적 가능한 로컬 근거자료(evidence)**로 변환하고, 정형화된 질문 기반 검토를 수행한 뒤, 그 결과를 **별도의 인간 의사결정(Human Decision)** 단계에 제공하기 위한 **오프라인·근거 우선(evidence-first) 검토 시스템**입니다.

## 개요

직접 질문을 검토하는 `review-question` 경로는 다음과 같습니다.

```text
PDF 또는 이미지
→ 원본/해시 바인딩 및 불변 Parser·Drawing Artifact 생성
→ Parser-ready 기준 근거자료를 evidence.sqlite에 저장
→ 활성 Review Workspace 바인딩
→ 외부 AI Question Planner
→ Fail-closed 방식의 QuestionPlan 검증
→ 결정론적 근거 검색 및 검토 준비
→ Track A 설명 및 검증
→ 독립적인 Track B 감사 및 검증
→ final-review-packet.json 및 review.html 생성
→ 보호된 Review Workspace
→ 별도의 Append-only Human Decision 기록
```

Python 런타임은 모델 API를 직접 호출하지 않습니다.

## ReviewMatter authority modes

ERS separates four authority-distinct modes. **Evidence Navigation** is
non-authoritative exploration of finalized evidence and does not require a
Planner or create a conclusion. The Workbench stores **mutable ReviewMatter
work state** such as selected evidence and drafts; that state is not evidence
or a decision. **Formalization** is the only promotion boundary from an exact
Matter revision and finalized snapshot into **Formal Review**. Formal Review
then retains the deterministic engines, Track A/Track B, immutable packet,
and packet-bound Human Decision boundaries below. The direct `review-question`
entrypoint requires a validated Question Planner handoff. `review-matter
formalize` instead consumes the explicit ReviewScope from promoted Matter
inputs and does not require that handoff.

Codex가 명시적인 파일 handoff를 통해 다음 결과를 제공합니다.

- Question Planner
- Track A
- Track B

ERS 런타임은 각 결과물을 검증한 후에만 다음 단계로 진행합니다.

Question Planner의 출력은 **근거 검색 구조를 설계하기 위한 정보**일 뿐, 그 자체가 근거자료는 아닙니다. 또한 Planner 결과만으로 법적 판단, 규정 준수 여부 또는 적격성 결론을 생성할 수 없습니다.

## 핵심 보장 사항

ERS는 다음 원칙을 보장하도록 설계되어 있습니다.

- 원본 파일 바이트, SHA-256, 문서·개정판·페이지 식별정보 및 bbox/geometry provenance를 근거자료와 계속 결합하여 유지합니다.
- Canonical filesystem trust와 verified regular-file 경계를 통해 보호된 artifact 경계에서 다음 항목을 거부합니다.
  - 안전하지 않은 경로
  - Symbolic link 및 Reparse point
  - 오래되거나 유효하지 않은 artifact
  - 소유권이 일치하지 않는 파일
- Parser record, 검색 결과, 계산 결과, 규칙 결과 및 외부 Track 출력은 검토 패킷에 포함되기 전에 검증됩니다.
- 다음과 같은 문제가 발생하면 워크플로는 **fail-closed** 방식으로 중단됩니다.
  - Planner 또는 Parser 출력 누락
  - 잘못된 출력 형식
  - Stale artifact
  - Hash 불일치
  - 승인된 Engine 입력 누락
  - 검증 실패
- 보호된 검토 화면과 페이지 이미지 제공에는 **tokenized loopback server**를 사용합니다.
- Human Decision은 해당 Review Packet에 바인딩된 **create-only / append-only 기록**으로 저장됩니다.
- Human Decision은 기존 Machine Packet 또는 Evidence를 변경하지 않습니다.

세부 계약 및 오프라인 실행 경계는 [문서 인덱스](docs/README.md)를 참고하십시오.

## 설치

Current source metadata version: `0.2.1`

The source version does not establish publication status. Check [GitHub
Releases](https://github.com/sage1993/evidence-review-system/releases) for the
current official release and published downloads.

지원 Python 버전: `>=3.13,<3.14`

Windows에서는 저장소 루트에서 Python 3.13 전용 가상환경을 생성합니다.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m evidence_review --version
```

설치본 검증은 같은 가상환경의 실행 파일로 수행합니다.

```powershell
.\.venv\Scripts\evidence-review.exe --runtime-mode installed doctor
```

Wheel acceptance는 별도의 깨끗한 Python 3.13 가상환경에서 candidate wheel을
설치하고 `PYTHONPATH` 없이 실행합니다. Editable install이나 저장소 `src`
주입은 설치본 검증이 아닙니다. 설치본과 개발 checkout의 구분, package digest,
workspace control directory는 [Runtime Authority](docs/runtime-authority.md)를
참고하십시오.

PDF를 처리하려면 지원되는 로컬 Parser가 필요합니다.

현재 기본 지원 Parser는 다음과 같습니다.

```text
OpenDataLoader PDF
(opendataloader-pdf)
```

단, 이미 검증된 Parser Artifact가 제공된 경우에는 새 Parser 실행이 필요하지 않을 수 있습니다.

주요 Runtime Dependency는 다음 범위로 제한됩니다.

```text
pypdf>=6.18.1,<7
pypdfium2>=5.12.1,<6
Pillow>=12.3,<13
```

## 빠른 시작

### PDF를 근거자료로 준비하기

법령, 기준, 보고서, 지침 등 **검색 가능한 기준 근거자료**로 사용할 PDF는 저장소 내부의 `$ERS_PDF` 워크플로를 사용합니다.

```text
$ERS_PDF 이 PDF를 검색 근거자료로 준비해줘
```

이 워크플로는 다음 작업을 수행합니다.

- 원본 Source 보존
- Parser와 Source 간 Binding 검증
- Parser 재현성 검증
- Source Batch v2 생성
- `evidence.sqlite` 생성
- 필요한 Revision Page Image Cache 검증
- 정확하게 준비된 Workspace 바인딩

도면을 시각적으로 검토하기 위해 제공된 PDF는 Reference Corpus로 처리하지 않습니다.

이 경우 `$ERS_REVIEW`의 **Case Visual 경로**를 사용합니다.

### 검토 실행

Reference Evidence 준비와 Workspace Binding이 완료된 이후에는 검토 결과·적합성·법적 판단을 묻는 모든 자연어 검토 질문을 `$ERS_REVIEW`를 통해 실행합니다. 명시적인 Evidence Navigation 또는 Workbench 작업 요청은 해당 작업 모드로 처리하며 Formal Review 질문으로 간주하지 않습니다.

예:

```text
$ERS_REVIEW 이 문서가 해당 기준을 충족하는지 근거 페이지와 함께 검토해줘
```

ERS에는 정식 검토 과정을 우회하는 **Quick Answer** 또는 **문장 전체 직접 검색 방식의 우회 경로**가 존재하지 않습니다.

위의 직접 질문 경로에서는 다음 순서가 적용됩니다.

1. 활성 Workspace 검증
2. 결론을 포함하지 않는 QuestionPlan 생성
3. 제한된 범위의 근거 검색
4. Track A 검증
5. 독립적인 Track B 감사
6. Final Review Packet 생성
7. Review HTML 생성

이미 ReviewMatter에서 작업한 경우에는 현재 revision과 명시적인 ReviewScope를
검증하는 `review-matter formalize`를 사용합니다. 이 경로는 불변 snapshot을
만든 후 같은 Formal Review core에 연결됩니다. 실행 예시는
[Codex Workflow](docs/CODEX_WORKFLOW.md)를 참고하십시오.

사용자는 다음 항목을 직접 작성하지 않습니다.

- QuestionPlan
- Query Bundle
- Review Request
- Track Handoff Metadata
- Packet Hash
- Timestamp

이 정보는 승인된 워크플로에 의해 생성되고 검증됩니다.

## Review Workspace

검토자가 사용하는 Review Workspace는 다음 정보의 우선순위를 기준으로 구성됩니다.

1. **검토 결과 상태와 간결한 결론**
2. **원본 근거자료**
   - 문서
   - 페이지
   - 인용문
   - Bounding Box
   - 검증된 Page Image
3. 다음과 같은 경우에만 표시되는 추가 검토 정보
   - 근거 누락
   - 근거 충돌
   - 예외사항
   - 판단 유보 또는 Abstention
4. **Human Decision 및 검토 메모**

보호된 Browser Route는 Token 기반으로 동작하며 **Loopback 통신만 허용**합니다.

새 RUN의 `review.html`은 이미지 바이트를 포함하지 않는 경량 진입 문서입니다. 파일로 열면 보호된 서버에서 검토하라는 안내가 표시됩니다. 실제 검토에는 `review-run serve`를 사용합니다.

기존 보관용 HTML에서 다운로드한 Decision Envelope는 승인된 Import 경로를 통해 Append-only Decision Record로 저장합니다. 기존 RUN 파일은 새 형식으로 덮어쓰지 않습니다.

다음과 같은 내부 감사 정보는 접힌 Audit Detail 영역에서 확인할 수 있습니다.

- 내부 ID
- Hash
- Confidence Detail
- Raw Audit Data

## `READY_FOR_HUMAN_REVIEW`의 의미

`READY_FOR_HUMAN_REVIEW` 상태는 **Machine Review Packet이 사람이 검토할 준비가 완료되었다는 의미**입니다.

다음 의미로 해석해서는 안 됩니다.

- 승인 완료
- 규정 준수 확정
- 법적 적합성 확정
- 최종 의사결정 완료

Machine Packet 내부의 `human_decision`은 별도로 분리되어 있으며 초기 상태는 `null`입니다.

검토자의 유효한 결정은 기존 패킷을 수정하는 것이 아니라 **해당 Packet에 바인딩된 새로운 Decision Record**로 저장됩니다.

## 현재 제한사항

### 오프라인 실행

ERS Runtime은 보호된 Loopback 통신을 제외하면 오프라인으로 동작합니다.

외부 AI 작업은 명시적인 파일 Handoff에서만 수행됩니다.

### Reference Document 검토 조건

Reference Document를 이용한 검토는 다음 요소가 모두 유효해야 진행할 수 있습니다.

- Active Workspace
- Parser-ready Evidence
- 필요한 Verified Page Image Cache

도면 또는 Supporting Image 검토의 경우에는 다음 검증이 완료될 때까지 검토가 차단될 수 있습니다.

- Visual Analysis
- Source Identity Verification

### 계산 및 규칙 결과

계산 및 Rule Outcome은 승인된 **Deterministic Engine Artifact**에서 생성되어야 합니다.

ERS Runtime은 다음 입력으로부터 계산 결과나 규칙 판정을 임의 추론하지 않습니다.

- 자연어 문장
- 이미지

### Acceptance Gate

다음 항목은 각각 별도의 Acceptance Gate입니다.

- Browser QA
- Release Artifact Validation
- Human Process Attestation

실행하지 않은 Gate는 PASS로 간주하지 않습니다.

반드시 다음과 같이 기록합니다.

```text
NOT_RUN
```

## Release Authority

현재 Release Acceptance의 기준 문서는 다음과 같습니다.

[docs/MANUAL_ACCEPTANCE_POLICY.md](docs/MANUAL_ACCEPTANCE_POLICY.md)

Release Validation 및 Build는 다음 명령을 사용합니다.

```powershell
py -3.13 scripts/validate_release.py $WORKSPACE --run-id <RUN-ID>
py -3.13 scripts/build_release.py $WORKSPACE <output> --run-id <RUN-ID>
```

폐기되었거나 Legacy 상태인 Validator Boundary는 [문서 인덱스](docs/README.md)에 기록되어 있습니다.

해당 Validator는 현재 Release Path에 포함되지 않습니다.

## 개발자 검증

정확한 HEAD의 Clean Checkout 환경에서 Python 3.13을 사용하여 다음 검증을 실행합니다.

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output tmp\documentation-integrity.json
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
```

Documentation Integrity 검증은 다음 항목을 검사합니다.

- 현재 유효한 문서 링크
- Heading
- Document Classification
- 문서에 기록된 CLI 경로
- 문서에 기록된 Script 경로

이 검증은 문서에 기술된 명령 자체를 실행하지 않습니다.

전체 Acceptance에는 필요에 따라 다음 검증도 포함됩니다.

- Focused Review Suite
- Protected Browser Path
- Archival Decision Path
- Release Smoke Check
- Manual Viewport QA
- Accessibility QA

실행하지 않은 Gate는 반드시 `NOT_RUN`으로 기록해야 합니다.

## Public repository governance and local acceptance

이 공개 저장소는 GitHub를 source, issue, Pull Request 및 release 관리에만
사용하며 GitHub Actions는 정책상 사용하지 않습니다.

```text
GITHUB_ACTIONS = NOT_USED_BY_POLICY
LOCAL_EXACT_SHA_VERIFICATION = AUTHORITATIVE_ACCEPTANCE
MAIN_INTEGRATION = PULL_REQUEST_ONLY
REQUIRED_STATUS_CHECKS = NONE
```

PR 생성 자체는 acceptance가 아닙니다. 정확한 candidate commit에서 다음
원클릭 verifier를 실행하면 repository gate, clean worktree, branch ancestry,
remote branch SHA 및 PR HEAD SHA를 함께 확인합니다.

```powershell
py -3.13 scripts/repository_gate.py --issue <N> --json-report "$env:TEMP\ers-repository-gate-<N>.json"
```

검증기는 실패·미실행 gate, dirty worktree, candidate 변경, 알 수 없는
ancestry 또는 SHA 불일치에서 `MERGE_READINESS = HOLD`로 종료합니다.
원격/PR 정보를 조회할 수 없을 때도 임의로 PASS하지 않습니다. 과거
acceptance report의 `ACTIONS_NOT_RUN` 기록은 역사적 사실이므로 수정하지
않습니다.

`<N>`은 실제 GitHub Issue 번호이며, 검증기는 issue-scoped branch, candidate
범위의 모든 contributor commit subject, PR head branch 및 PR 본문의
`Closes/Fixes/Resolves #N`를 함께 확인합니다.

명시적인 여러 이슈의 통합 후보에는 `--issue` 대신 다음 모드를 사용합니다.

```powershell
py -3.13 scripts/repository_gate.py --integration-manifest <absolute-manifest.json> --json-report "$env:TEMP\ers-integration-gate.json"
```

외부 manifest는 origin/base/candidate/branch, 이슈 번호와 전체 commit 목록을
결속합니다. PR 본문에는 manifest SHA-256과 각 이슈의 closing reference가
필요합니다. 이 모드는 단일 이슈 검증이나 로컬 gate를 우회하지 않습니다.
정확한 형식은 [Commit, Push, and Pull Request Policy](docs/COMMIT_PUSH_POLICY.md)를
참고하십시오.

`--json-report`는 repository 밖의 절대 경로만 허용하며,
runtime/package 변경에는 exact candidate SHA에 결합된 외부 `--package-evidence`
JSON이 필요합니다. Wheel build, isolated install, `pip check`, runtime
smoke 중 하나라도 없거나 실패하면 `PACKAGE_ACCEPTANCE`는 PASS가 아닙니다.

## 문서

ERS 문서의 시작점은 다음 파일입니다.

[docs/README.md](docs/README.md)

해당 문서에서는 다음 항목을 분류하여 안내합니다.

- 현재 Authority
- Architecture 및 Contract
- 운영 절차
- Migration Compatibility
- Acceptance Record
- 과거 Implementation Plan

현재 사용되는 Codex Instruction은 다음 위치에 있습니다.

[.agents/skills/README.md](.agents/skills/README.md)

## 보안 및 데이터 처리

다음 자료를 Git 저장소에 Commit해서는 안 됩니다.

- 독점 또는 고객 소유 PDF
- 제한된 문서에서 파생된 Parser Output
- Evidence Database
- Page Image Cache
- Human Decision Record
- Credential
- Token
- Private URL
- Private Key

상세한 실행 및 보안 경계는 다음 문서를 참고하십시오.

- [Offline Execution Boundary](docs/OFFLINE_EXECUTION.md)
- [SECURITY.md](SECURITY.md)

## 라이선스

Evidence Review System은 [Apache License 2.0](LICENSE)에 따라 배포됩니다.
