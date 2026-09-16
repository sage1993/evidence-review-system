# Evidence Review System 기여 가이드

Evidence Review System은 **근거 우선(evidence-first)** 방식으로 동작하는 오프라인 검토 런타임입니다. 기여는 환영하지만, 모든 변경은 **결정론적 provenance**, **fail-closed 검증**, 그리고 **Machine Review 출력과 최종 Human Decision의 분리**를 유지해야 합니다.

## 지원 개발 환경

- Python `>=3.13,<3.14`
- Browser 및 Review Workspace 동작에 대한 주요 Acceptance Platform은 Windows입니다.
- Runtime 동작에 Remote API, CDN, Telemetry Service 또는 Model Dependency를 추가해서는 안 됩니다.

독립된 개발 환경을 생성하고 개발용 Dependency를 설치합니다.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## 코드 변경 전 확인사항

1. 기존 Issue 및 Pull Request를 먼저 검색합니다.
2. 동작을 변경하는 경우 테스트를 먼저 추가하거나 수정합니다.
3. Source PDF, Parser Output, Evidence Database, Page Image Cache, Customer Data 및 Human Decision Record는 저장소 외부에 보관합니다.
4. 테스트를 통과시키기 위해 Source Hash, Rule, Page Image, Manifest, Release 또는 Packet Validation을 약화해서는 안 됩니다.
5. 공개 Canonical Namespace와 CLI는 `evidence_review` / `evidence-review` 아래에 유지합니다.

## 개발 워크플로

하나의 목적에 집중된 Branch를 사용하고 Commit이 검토 가능한 단위로 유지되도록 합니다.

Issue별 Branch/Worktree, Commit 범위와 메시지, 정확한 SHA 검증, Push, PR, Review 및
Merge 절차는 [Commit, Push, and Pull Request Policy](docs/COMMIT_PUSH_POLICY.md)를
따릅니다. 이 문서는 GitHub `main` 보호 설정과 로컬 Acceptance 절차의 역할도 구분합니다.

Pull Request에는 다음 내용을 설명해야 합니다.

- 해결하려는 문제
- 관련 Issue
- Security 및 Provenance에 미치는 영향
- 추가하거나 변경한 테스트
- 실제로 실행한 정확한 Validation Command
- UI 동작이 변경된 경우 Manual Browser Validation 결과

실행하지 않은 Validation을 PASS로 보고해서는 안 됩니다.

실행하지 않은 검증은 사유와 함께 다음과 같이 기록합니다.

```text
NOT_RUN
```

## 검증

정확한 Candidate HEAD의 Clean Checkout에서 다음 명령을 실행합니다.

```powershell
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output tmp\documentation-integrity.json
```

Packaging 또는 Release 동작을 변경한 경우 Wheel과 Web Runtime Bundle을 Build하고 Smoke Test까지 수행해야 합니다.

Review Workspace를 변경한 경우 Static Test뿐 아니라 **실제 Browser Verification**도 수행해야 합니다.

GitHub Actions는 이 저장소의 검증 경로가 아닙니다. 정책상 항상 다음과
같이 기록합니다.

```text
GITHUB_ACTIONS = NOT_USED_BY_POLICY
LOCAL_EXACT_SHA_VERIFICATION = AUTHORITATIVE_ACCEPTANCE
MAIN_INTEGRATION = PULL_REQUEST_ONLY
```

PR 생성은 acceptance가 아닙니다. 정확한 candidate commit에서 원클릭
verifier를 실행하고, push 및 PR 생성 후에도 SHA parity를 다시 확인해야
합니다. GitHub API 또는 PR 정보를 조회할 수 없으면 PASS로 추정하지 않고
`NOT_VERIFIED`와 `MERGE_READINESS = HOLD`를 기록합니다.

```powershell
py -3.13 scripts/repository_gate.py --issue <N> --json-report "$env:TEMP\ers-repository-gate-<N>.json"
```

실행하지 않은 gate는 사유와 함께 `NOT_RUN`으로 기록합니다. 과거
acceptance report의 `ACTIONS_NOT_RUN`은 역사적 기록이므로 수정하지
않습니다.

검증 report는 repository 밖의 절대 경로에만 기록할 수 있습니다. Package
변경은 exact candidate SHA를 포함한 외부 package acceptance evidence와
wheel SHA-256, wheel build, isolated install, `pip check`, runtime smoke
결과를 함께 요구합니다. Issue 번호가 없거나 branch/commit/PR closing
reference가 일치하지 않으면 local gate는 `HOLD`입니다.

Acceptance evidence에는 다음 정보를 포함합니다.

- 정확한 HEAD
- Python Version
- OS
- 실행 명령
- 실행 결과

## 테스트 데이터

테스트에는 **결정론적이며 재배포 가능한 Fixture**만 사용해야 합니다.

다음 자료는 절대 Commit하지 않습니다.

- 독점 또는 고객 소유 PDF
- 제한된 Source Material에서 파생된 Parser Output
- 사용자 Evidence Database
- 제한된 문서에서 추출한 Page Image
- Credential, Token, Private URL 또는 Private Key
- 실제 Human Decision Record

Fixture가 반드시 필요한 경우에는 최소한의 범위로 축소하고, 해당 데이터를 재배포할 수 있는 이유를 문서화해야 합니다.

## Review Architecture 제약

모든 기여는 다음 Architecture Boundary를 유지해야 합니다.

1. 보존된 Source Byte 및 Hash가 Authoritative Source입니다.
2. Parser 및 Evidence Record는 결정론적이어야 합니다.
3. Retrieval, Math Engine 및 Rule Engine의 출력은 Review에 사용되는 결정론적 입력이어야 합니다.
4. Track A와 Track B는 검증된 Handoff이며, 새로운 Evidence를 임의로 만들어내는 Authority가 아닙니다.
5. `final-review-packet.json`은 변경 불가능한 Machine Output입니다.
6. Human Decision은 별도의 Append-only Record로 저장됩니다.

`READY_FOR_HUMAN_REVIEW`는 승인 완료 또는 규정 준수 확정을 의미하지 않습니다.

## Pull Request

가능한 경우 하나의 PR에는 하나의 논리적 변경만 포함합니다.

Public Readiness를 위한 `v0.2.0` 작업은 Repository Cleanup, Namespace Migration, Packaging 및 Release Contract가 서로 연관되어 있어 의도적으로 통합되었습니다. 이는 서로 관련 없는 변경을 하나의 대규모 PR로 묶어도 된다는 선례가 아닙니다.

Reviewer는 Merge 전에 다음 사항을 요구할 수 있습니다.

- 보다 집중된 Commit 분리
- 추가 Regression Test
- Security Hardening
- 정확한 HEAD에서의 재검증

## 라이선스

Evidence Review System은 Apache License 2.0에 따라 배포됩니다.

별도의 서면 계약이 없는 한 모든 Contribution은 `LICENSE`에 명시된 조건에 따라 제출되고 수락됩니다.
