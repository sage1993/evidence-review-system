# Rule Activation Governance Design

Issue: #48  
Parent: #27  
Base: `main@cb2fbf0a009ebd335393e8c0100755e029e3657a`

## 1. 목적

현재 `rules/manifests/active.json`은 approved rule 경로, candidate hash, approved rule hash, reviewer와 review date를 기록하지만 다음을 권위 있게 증명하지 못한다.

- 규칙이 어떤 문서 범위에 적용되는지
- 어떤 golden fixture와 결과로 승인됐는지
- active manifest가 사람이 직접 편집된 것인지 검증된 승인 기록에서 생성된 것인지
- 적용 가능한 규칙이 없을 때 왜 `ABSTAIN`했는지
- 승인 기록 또는 rule/golden artifact가 변조됐을 때 평가가 차단되는지

이 설계는 rule activation을 다음 파이프라인으로 제한한다.

```text
candidate rule
  -> approved rule
  -> golden test report
  -> human approval artifact
  -> deterministic activator
  -> derived active manifest v2
  -> scope-bound runtime selection
```

사람은 승인 artifact를 검토하고 승인한다. 프로그램은 승인 artifact와 연결된 모든 hash·scope·golden evidence를 검증한 뒤에만 active manifest를 생성한다. Runtime은 active manifest에 포함된 승인된 규칙만 선택한다.

## 2. 설계 원칙

1. **판정 권한과 실행 권한을 분리한다.** Rule authoring, golden execution, human approval, active selection은 서로 다른 artifact와 단계다.
2. **`active.json`은 파생 index다.** 사람이 직접 편집하는 승인 원장이 아니다.
3. **적용 범위는 명시한다.** 파일명, rule ID 접두어, 문서 제목 또는 경로에서 scope를 추론하지 않는다.
4. **증거가 없으면 활성화하지 않는다.** 기존 active rule도 실제 PASS golden evidence가 없으면 v2 manifest로 자동 승격하지 않는다.
5. **무규칙은 오류가 아니다.** 유효한 manifest에서 적용 가능한 rule이 없으면 `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`이다.
6. **손상된 거버넌스는 오류다.** Manifest, approval, golden report 또는 rule hash가 잘못되면 `BLOCKED`이며 `ABSTAIN`으로 축소하지 않는다.
7. **결정론을 유지한다.** 동일 입력 artifact bytes에서는 동일 active manifest bytes와 동일 selection result를 생성한다.
8. **검토자 신원을 과장하지 않는다.** Reviewer ID와 timestamp는 기록하지만 전자서명이나 조직 계정 인증을 제공한다고 주장하지 않는다.

## 3. 범위

### 3.1 포함

- strict approval artifact 계약
- strict golden report 계약
- derived active manifest v2 계약
- runtime rule selection result 계약
- exact SHA-256 및 경로 검증
- deterministic active manifest builder
- exact scope matcher
- 명시적 `ABSTAIN` 및 exclusion reason
- invalid governance artifact의 fail-closed `BLOCKED`
- 기존 ANSIM active rule의 scoped migration
- CLI, 문서, acceptance evidence, CI와 wheel 검증

### 3.2 제외

- 전자서명, PKI, 원격 승인 서버
- 규칙 내용의 법률적 타당성 재심사
- 새로운 ANSIM 외 규칙 작성
- rule evaluator 전체 재작성
- fuzzy scope matching
- 파일명·제목·ID 접두어 기반 scope 추론
- 네트워크 의존성

## 4. 현재 상태와 전환 경계

현재 `rules/manifests/active.json`에는 6개의 ANSIM 규칙이 version 1 형태로 등록되어 있다. 각 entry는 candidate hash, approved rule hash, reviewer와 review date를 포함하지만 scope와 golden report binding이 없다.

전환 후 runtime 권위 manifest는 exact `evidence-review/active-rule-manifest` version 2만 허용한다.

- v1 manifest를 runtime에서 자동 해석하거나 암묵적으로 v2로 승격하지 않는다.
- v1을 읽으면 `RULE_GOVERNANCE_LEGACY_MANIFEST`로 `BLOCKED`한다.
- PR 안에서 repository의 checked-in `active.json`을 v2로 교체한다.
- 기존 6개 rule은 각 rule에 대해 재현 가능한 PASS golden report와 human approval artifact가 생성된 경우에만 v2에 포함한다.
- golden evidence를 생성할 수 없는 rule은 active v2에서 제외한다. 해당 scope 평가 결과는 적용 가능한 다른 rule이 없다면 `ABSTAIN`이다.

이 설계는 기존 active 상태를 보존하는 것보다 근거 없는 활성화를 제거하는 것을 우선한다.

## 5. Artifact 계약

모든 JSON artifact는 UTF-8, canonical key ordering, LF newline과 lowercase SHA-256을 사용한다. Decoder는 unknown field, duplicate logical identity, 잘못된 timestamp와 unsafe relative path를 거부한다.

### 5.1 Golden report

Format:

```text
evidence-review/rule-golden-report
version: 1
```

필수 필드:

- `format`
- `version`
- `rule_id`
- `rule_version`
- `approved_rule_path`
- `approved_rule_sha256`
- `candidate_path`
- `candidate_sha256`
- `runner_version`
- `source_commit`
- `command`
- `fixture_manifest_sha256`
- `case_count`
- `passed_count`
- `failed_count`
- `status`: `PASS` 또는 `FAIL`
- `cases`

각 case는 다음을 포함한다.

- `case_id`
- `fixture_path`
- `fixture_sha256`
- `expected_path`
- `expected_sha256`
- `actual_sha256`
- `status`

승격 가능한 golden report 조건:

- `status == PASS`
- `case_count > 0`
- `passed_count == case_count`
- `failed_count == 0`
- 모든 case가 `PASS`
- fixture, expected, candidate와 approved rule의 현재 bytes가 기록된 hash와 일치

Golden report는 실행 결과를 기록한다. Human approval을 대신하지 않는다.

### 5.2 Activation approval

Format:

```text
evidence-review/rule-activation-approval
version: 1
```

필수 필드:

- `format`
- `version`
- `rule_id`
- `rule_version`
- `candidate_path`
- `candidate_sha256`
- `approved_rule_path`
- `approved_rule_sha256`
- `golden_report_path`
- `golden_report_sha256`
- `scope`
- `reviewer_id`
- `reviewed_at`
- `decision`: exact `APPROVED`
- `reason`

`reviewed_at`은 timezone-aware ISO 8601이다. `reason`은 공백이 아닌 설명이어야 한다.

Approval은 다음 세 artifact를 하나의 승인 결정에 결속한다.

1. candidate bytes
2. approved rule bytes
3. PASS golden report bytes

Approval artifact 자체가 존재해도 연결된 bytes가 다르면 효력이 없다.

### 5.3 Scope

Scope는 exact-match dimensions만 사용한다.

필수:

- `document_family`

선택:

- `document_kind`
- `jurisdiction`
- `program`

각 값은 trim된 non-empty 문자열이다. Wildcard, regex, prefix match와 null-as-any 의미는 지원하지 않는다.

Rule selection context도 같은 네 dimension을 사용한다.

Matching 규칙:

- Approval scope에 선언된 모든 dimension이 context에 존재하고 exact string으로 일치해야 한다.
- Context에 추가 dimension이 있어도 무방하다.
- 필수 context 값이 없으면 해당 rule은 `MISSING_SCOPE_VALUE`로 제외한다.
- 값이 다르면 `SCOPE_MISMATCH`로 제외한다.
- `document_family` 자체가 context에 없으면 모든 정상 rule이 제외되고 최종 결과는 `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`이다.

Missing context는 governance artifact 손상이 아니므로 `BLOCKED`가 아니다.

기존 ANSIM rule의 scope는 최소 다음과 같다.

```json
{
  "document_family": "ANSIM"
}
```

Rule ID의 `ANSIM-` 접두어에서 이 값을 추론하지 않는다. Migration approval에 사람이 명시한다.

### 5.4 Active manifest v2

Format:

```text
evidence-review/active-rule-manifest
version: 2
```

Top-level:

- `format`
- `version`
- `rules`

각 rule entry:

- `rule_id`
- `rule_version`
- `approved_rule_path`
- `approved_rule_sha256`
- `candidate_path`
- `candidate_sha256`
- `golden_report_path`
- `golden_report_sha256`
- `approval_path`
- `approval_sha256`
- `scope`
- `reviewer_id`
- `reviewed_at`
- `reason`

Active manifest에는 `generated_at`을 넣지 않는다. 동일한 approval set은 시간과 실행 환경에 관계없이 동일 bytes를 생성해야 한다.

정렬 순서:

1. `rule_id`
2. semantic version canonical string
3. approval path

제약:

- 동일 `rule_id`는 active manifest에 한 version만 존재할 수 있다.
- 동일 approval path/hash는 한 번만 사용한다.
- 서로 다른 rule은 같은 scope를 가질 수 있다.
- 같은 scope에 여러 rule이 적용되면 모두 selected된다. 이 기능은 rule priority나 상호 배제를 도입하지 않는다.

### 5.5 Selection result

Format:

```text
evidence-review/rule-selection-result
version: 1
```

Status:

- `SELECTED`
- `ABSTAIN`
- `BLOCKED`

공통 필드:

- `format`
- `version`
- `status`
- `context`
- `manifest_sha256`
- `selected_rules`
- `excluded_rules`
- `reasons`

`selected_rules`에는 rule ID, version, path, hash와 scope가 포함된다.

`excluded_rules`에는 rule ID, version과 다음 exclusion code 중 하나가 포함된다.

- `MISSING_SCOPE_VALUE`
- `SCOPE_MISMATCH`

정상 manifest에서 selected rule이 0개면:

```text
status = ABSTAIN
reasons = [NO_APPLICABLE_ACTIVE_RULE]
```

Manifest 또는 연결 artifact가 손상되면:

```text
status = BLOCKED
```

대표 blocking reason:

- `ACTIVE_MANIFEST_INVALID`
- `ACTIVE_RULE_HASH_MISMATCH`
- `APPROVAL_HASH_MISMATCH`
- `GOLDEN_REPORT_HASH_MISMATCH`
- `GOLDEN_REPORT_NOT_PASSING`
- `CANDIDATE_HASH_MISMATCH`
- `DUPLICATE_ACTIVE_RULE_ID`
- `UNSAFE_ARTIFACT_PATH`

`BLOCKED` 결과에서 일부 valid rule만 선택하는 partial fallback은 금지한다.

## 6. Components

### 6.1 Contract decoder

책임:

- 네 versioned JSON 계약의 strict decode/encode
- exact key validation
- SHA, timestamp, path, enum, count와 uniqueness 검증
- canonical serialization

이 모듈은 파일 시스템을 읽지 않는다.

### 6.2 Artifact verifier

책임:

- repository root 아래 safe relative path 해석
- symlink/path traversal 차단
- candidate, approved rule, golden report, approval bytes hash 검증
- golden case fixture/expected bytes 검증
- rule identity/version 교차 검증

검증 중 하나라도 실패하면 structured blocking finding을 반환한다.

### 6.3 Deterministic activator

입력:

- repository root
- 명시적 approval file 목록 또는 approval directory
- create-only output manifest path
- create-only activation report path

처리:

1. Approval 목록을 byte-stable 순서로 수집한다.
2. 각 approval을 strict decode한다.
3. 연결 candidate, approved rule와 golden report를 검증한다.
4. Golden report가 실제 PASS이고 case evidence가 유효한지 확인한다.
5. Duplicate rule ID/version/path와 충돌을 검사한다.
6. 모든 approval이 valid일 때만 v2 manifest를 canonical JSON으로 생성한다.
7. Activation report와 active manifest를 create-only로 함께 게시한다.

하나라도 invalid하면 active manifest를 생성하지 않고 report status를 `BLOCKED`로 기록한다. Existing output은 덮어쓰지 않는다.

### 6.4 Active manifest loader

책임:

- v2 manifest strict decode
- manifest entry가 참조하는 approval, golden report, approved rule와 candidate hash 재검증
- runtime selection 전에 전체 manifest authority 검증

Activator 때 검증했더라도 runtime load 때 다시 검증한다. Checked-in artifact가 activation 이후 변경될 수 있기 때문이다.

### 6.5 Scope selector

책임:

- 검증 완료된 active entries와 explicit context를 입력받는다.
- exact dimension match를 수행한다.
- deterministic selected/excluded 목록을 만든다.
- 0개 selected 시 명시적 `ABSTAIN`을 반환한다.

Selector는 파일명, document title, rule ID나 경로를 보지 않는다.

### 6.6 Evaluator integration boundary

기존 evaluator는 직접 `rules/approved`, `rules/candidates` 또는 v1 active manifest를 탐색해서는 안 된다.

새 integration은 다음 순서를 강제한다.

1. Active manifest authority validation
2. Scope selection
3. `BLOCKED`면 평가 중단
4. `ABSTAIN`이면 규칙 평가 없이 결과와 이유 출력
5. `SELECTED`면 선택된 approved rule bytes만 evaluator에 전달

Evaluator 내부의 수학·논리 실행은 이 이슈에서 재작성하지 않는다.

## 7. CLI

### 7.1 Active manifest 생성

```powershell
evidence-review rules build-active-manifest `
  --repository-root . `
  --approvals rules/activation/approvals `
  --output rules/manifests/active.json `
  --report build/rules/activation-report.json
```

Exit codes:

- `0`: 모든 approval 검증 및 두 output 게시 성공
- `1`: output 또는 temporary path가 이미 존재
- `2`: contract, hash, golden, scope 또는 I/O 검증 실패

### 7.2 Active manifest 검증 및 선택

```powershell
evidence-review rules select `
  --repository-root . `
  --manifest rules/manifests/active.json `
  --context context.json
```

Stdout은 canonical `rule-selection-result` JSON이다.

Exit codes:

- `0`: `SELECTED` 또는 정상 `ABSTAIN`
- `2`: `BLOCKED`

`ABSTAIN`은 정상적이고 설명 가능한 결과이므로 nonzero exit code를 사용하지 않는다.

## 8. Error handling and publication

- 입력 artifact는 read-only로 취급한다.
- Output manifest와 report는 create-only다.
- Temporary file은 final output과 같은 directory에 생성한다.
- Final publication은 기존 파일을 덮어쓰지 않는 방식으로 수행한다.
- 둘 중 하나만 publish된 경우 현재 실행이 만든 output만 rollback한다.
- Concurrent creator가 만든 파일은 삭제하지 않는다.
- Error와 finding ordering은 artifact path, rule ID, reason code 순으로 deterministic하다.

Checked-in `rules/manifests/active.json` 갱신은 다음 절차로 수행한다.

1. 빈 build path에 v2 manifest 생성
2. validator로 재검증
3. 기존 checked-in manifest와 diff 검토
4. 명시적 repository change로 교체

Activator 자체는 기존 checked-in manifest를 직접 덮어쓰지 않는다.

## 9. Migration of current ANSIM rules

기존 6개 active entry 각각에 대해 다음을 수행한다.

1. Current candidate와 approved rule bytes hash 재계산
2. Existing golden fixtures와 expected outputs 확인
3. Deterministic golden runner 실행
4. PASS golden report 생성
5. Scope `{ "document_family": "ANSIM" }`을 포함한 human approval artifact 생성
6. Approval에서 candidate/rule/golden hash 결속
7. 모든 valid approval로 v2 manifest 생성

중요:

- Existing reviewer/date를 새 approval에 기계적으로 복사하지 않는다.
- 새 v2 approval은 실제 검토자와 새 timezone-aware 검토시각을 기록한다.
- 기존 테스트가 존재한다는 사실만으로 golden PASS를 선언하지 않는다.
- Rule별 golden report가 생성되지 않거나 FAIL하면 해당 rule은 v2 active manifest에서 제외한다.
- Excluded rule을 임시로 v1 fallback에서 실행하지 않는다.

실제 approval artifact와 v2 manifest, golden report hash, activation report는 `docs/acceptance/issue-48/`에 보존한다. 대용량 임시 execution output은 `build/`에 남기고 커밋하지 않는다.

## 10. Security and trust boundaries

- 모든 artifact path는 repository root 내부의 regular file이어야 한다.
- Absolute path, `..`, path traversal, case-fold collision과 symlink escape를 차단한다.
- JSON duplicate key는 decoder 단계에서 차단한다.
- SHA-256은 artifact integrity binding이며 reviewer identity 인증이 아니다.
- Approval reason과 reviewer ID는 감사 기록이지만 법률적 승인 자체를 자동 증명하지 않는다.
- Candidate와 approved rule이 동일 hash일 필요는 없다. 다만 approval과 golden report가 각각 정확한 candidate/approved hashes를 명시해야 한다.
- Runtime은 network, Git history 또는 environment variable을 승인 권위로 사용하지 않는다.

## 11. Testing strategy

### 11.1 Contract tests

- round-trip canonical JSON
- unknown/missing field
- uppercase/invalid SHA
- naive timestamp
- empty reviewer/reason
- unsafe path
- invalid counts/status
- duplicate rule identity
- v1 active manifest rejection

### 11.2 Golden verifier tests

- all-pass valid report
- zero-case report rejection
- count mismatch
- fixture/expected/rule/candidate tamper
- report `FAIL`
- identity/version mismatch
- source commit and command presence

### 11.3 Activator tests

- deterministic bytes independent of input enumeration order
- duplicate rule ID with multiple versions blocked
- same scope with different rule IDs allowed
- one invalid approval blocks entire output
- output create-only
- concurrent output preservation
- partial publication rollback
- no generated timestamp

### 11.4 Scope selector tests

- exact match
- optional dimensions
- missing required context dimension
- mismatch exclusion
- multiple selected rules in canonical order
- no selected rule -> `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`
- invalid manifest -> `BLOCKED`, never abstain

### 11.5 Integration tests

- evaluator receives selected approved rules only
- candidate and unapproved rule are never executed
- v1 manifest does not silently run
- ANSIM context selects migrated ANSIM rules
- non-ANSIM context does not execute ANSIM rules
- missing context produces explicit abstention evidence
- tampered checked-in artifact blocks runtime

### 11.6 CI and packaging

- full pytest
- Ruff
- strict mypy
- compileall
- Python 3.11 wheel build/install/resource/entrypoint
- Python 3.13 wheel build/install/resource/entrypoint
- Windows workspace validator
- Ubuntu workspace validator

## 12. Documentation and acceptance evidence

Add or update:

- `docs/RULE_ACTIVATION_GOVERNANCE.md`
- CLI sections in `README.md` or `VALIDATE.md`
- `docs/acceptance/issue-48/README.md`
- acceptance approval artifacts
- golden report artifacts
- activation report
- v2 active manifest copy and hashes

Acceptance README records:

- source commit
- activation command
- rule count
- included and excluded rule IDs
- candidate, approved rule, golden report, approval and manifest hashes
- scope values
- selection examples for ANSIM and non-ANSIM contexts
- expected `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`
- final CI run and job conclusions

## 13. Completion criteria

Issue #48 is complete only when all conditions hold.

1. Repository runtime consumes only valid active manifest v2.
2. Active v2 is deterministically derived from valid approval artifacts.
3. Every active entry is bound to candidate, approved rule, PASS golden report, reviewer, timestamp, reason and explicit scope.
4. Existing ANSIM rules execute only under explicit ANSIM scope.
5. Nonmatching or missing scope produces explicit `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE` with exclusion evidence.
6. Invalid/tampered governance artifact produces `BLOCKED` without partial fallback.
7. Candidate, unapproved rule and legacy v1 manifest cannot enter the normal evaluator path.
8. Acceptance artifacts and reproduction procedure are committed.
9. Full test, lint, type, compile, wheel and Windows/Ubuntu validation passes.
10. No claim of cryptographically verified reviewer identity is made.
