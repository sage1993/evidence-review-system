# Rule Activation Governance Design

Issue: #48  
Parent: #27  
Base: `main@cb2fbf0a009ebd335393e8c0100755e029e3657a`

## 1. 목적

현재 `rules/manifests/active.json`은 approved rule 경로, candidate hash, approved rule hash, reviewer와 review date를 기록하지만 다음을 권위 있게 증명하지 못한다.

- 규칙의 적용 범위
- 규칙 승격에 사용된 golden fixture와 결과
- active manifest가 승인 기록에서 결정적으로 생성됐는지
- 적용 가능한 규칙이 없을 때의 명시적 `ABSTAIN` 근거
- 승인·rule·golden artifact가 손상됐을 때 평가가 차단되는지

Rule activation을 다음 파이프라인으로 제한한다.

```text
candidate rule
  -> approved rule
  -> golden test report
  -> human approval artifact
  -> deterministic activator
  -> derived active manifest v2
  -> scope-bound runtime selection
```

사람은 approval artifact를 검토하고 승인한다. 프로그램은 approval과 연결된 candidate, approved rule, golden evidence와 scope를 검증한 뒤에만 active manifest를 생성한다. Runtime은 valid active manifest에 포함된 approved rule만 선택한다.

## 2. 설계 원칙

1. **판정 권한과 실행 권한을 분리한다.** Rule authoring, golden execution, human approval, activation과 runtime selection은 별도 단계다.
2. **`active.json`은 파생 index다.** 사람이 직접 편집하는 승인 원장이 아니다.
3. **Scope를 추론하지 않는다.** 파일명, rule ID 접두어, 문서 제목과 경로는 scope authority가 아니다.
4. **증거가 없으면 활성화하지 않는다.** 기존 active rule도 실제 PASS golden evidence가 없으면 v2로 자동 승격하지 않는다.
5. **무규칙은 정상 결과다.** Valid manifest에서 적용 가능한 rule이 없으면 `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`이다.
6. **손상된 governance는 차단한다.** Manifest, approval, golden report, candidate 또는 approved rule hash가 잘못되면 `BLOCKED`이며 `ABSTAIN`으로 축소하지 않는다.
7. **결정론을 유지한다.** 동일 input bytes는 동일 active manifest bytes와 selection result를 생성한다.
8. **검토자 신원을 과장하지 않는다.** Reviewer ID와 timestamp는 기록하지만 전자서명이나 조직 계정 인증을 제공한다고 주장하지 않는다.

## 3. 범위

### 포함

- strict golden report contract
- strict activation approval contract
- derived active manifest v2 contract
- activation report contract
- runtime rule selection result contract
- exact SHA-256, path와 identity 검증
- deterministic create-only activator
- exact scope matcher
- 명시적 `ABSTAIN`과 exclusion evidence
- invalid governance artifact의 fail-closed `BLOCKED`
- 기존 ANSIM active rule의 scoped migration
- CLI, 문서, acceptance evidence, CI와 wheel 검증

### 제외

- 전자서명, PKI, 원격 승인 서버
- 규칙 내용의 법률적 타당성 재심사
- ANSIM 외 신규 rule authoring
- rule evaluator 전체 재작성
- fuzzy scope matching
- 파일명·제목·ID 접두어 기반 scope 추론
- 네트워크 의존성

## 4. 현재 상태와 전환 경계

현재 `rules/manifests/active.json`에는 6개의 ANSIM 규칙이 legacy 구조로 등록되어 있다. 각 entry는 candidate hash, approved rule hash, reviewer와 review date를 포함하지만 scope와 golden report binding이 없다.

전환 후 runtime authority는 exact `evidence-review/active-rule-manifest` version 2만 허용한다.

- Legacy manifest를 runtime에서 자동 해석하거나 v2로 암묵 승격하지 않는다.
- Legacy manifest는 `RULE_GOVERNANCE_LEGACY_MANIFEST`로 `BLOCKED`한다.
- 이 PR에서 checked-in `rules/manifests/active.json`을 v2로 교체한다.
- 기존 6개 rule은 각 rule에 재현 가능한 PASS golden report와 새 human approval artifact가 있을 때만 v2에 포함한다.
- Golden evidence를 생성할 수 없거나 FAIL인 rule은 v2에서 제외한다.
- 제외된 rule을 legacy fallback으로 실행하지 않는다.
- Empty v2 manifest는 valid하다. 모든 evaluation context에서 명시적 `ABSTAIN`을 반환한다.

이 설계는 기존 활성 상태를 관성적으로 유지하는 것보다 근거 없는 rule 실행을 제거하는 것을 우선한다.

## 5. 공통 JSON 규칙

모든 governance JSON은 다음을 따른다.

- UTF-8
- LF newline
- canonical key ordering
- lowercase 64-character SHA-256
- duplicate JSON key 차단
- unknown field 차단
- repository-root-relative safe path
- absolute path, `..`, path traversal와 symlink escape 차단
- logical identity 중복 차단
- timezone-aware ISO 8601 timestamp

Artifact path 비교는 `/` separator로 정규화하고 case-fold collision을 차단한다.

## 6. Artifact 계약

### 6.1 Rule golden report

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
- `candidate_path`
- `candidate_sha256`
- `approved_rule_path`
- `approved_rule_sha256`
- `runner_version`
- `source_commit`
- `command`
- `fixture_manifest_path`
- `fixture_manifest_sha256`
- `case_count`
- `passed_count`
- `failed_count`
- `status`: `PASS` 또는 `FAIL`
- `cases`

각 case:

- `case_id`
- `fixture_path`
- `fixture_sha256`
- `expected_path`
- `expected_sha256`
- `actual_path`
- `actual_sha256`
- `status`: `PASS` 또는 `FAIL`

승격 가능한 report 조건:

- `status == PASS`
- `case_count > 0`
- `passed_count == case_count`
- `failed_count == 0`
- case ID가 유일함
- 모든 case가 `PASS`
- candidate와 approved rule bytes가 기록 hash와 일치
- fixture manifest와 모든 fixture·expected·actual output bytes가 기록 hash와 일치
- expected hash와 actual hash가 일치

`source_commit`과 `command`는 재현 기록이다. Activator는 현재 Git HEAD가 `source_commit`과 같다고 요구하지 않으며 Git history를 runtime authority로 사용하지 않는다.

Golden report는 실행 결과를 기록할 뿐 human approval을 대신하지 않는다.

### 6.2 Rule activation approval

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

`reviewer_id`와 `reason`은 trim 후 non-empty다. `reviewed_at`은 timezone-aware ISO 8601이다.

Approval은 다음 artifact bytes를 하나의 사람 결정에 결속한다.

1. candidate rule
2. approved rule
3. PASS golden report
4. explicit scope

Approval artifact 자체가 존재해도 연결 bytes나 identity가 다르면 효력이 없다.

### 6.3 Scope

Scope는 case-sensitive exact-match dimensions만 사용한다.

필수:

- `document_family`

선택:

- `document_kind`
- `jurisdiction`
- `program`

각 값은 trim된 non-empty 문자열이다. Wildcard, regex, prefix match, list와 null-as-any는 지원하지 않는다.

Selection context는 같은 네 key만 허용하며 각 key는 선택 사항이다. Matching 규칙:

- Approval scope에 선언된 모든 dimension이 context에 존재하고 exact string으로 일치해야 한다.
- Context에 추가로 선언된 supported dimension은 matching에 영향을 주지 않는다.
- Scope가 요구한 key가 context에 없으면 `MISSING_SCOPE_VALUE`로 제외한다.
- 값이 다르면 `SCOPE_MISMATCH`로 제외한다.
- `document_family`가 context에 없으면 모든 정상 rule이 제외되고 최종 결과는 `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`이다.

Missing context는 governance artifact 손상이 아니므로 `BLOCKED`가 아니다.

기존 ANSIM rule approval은 최소 다음 scope를 명시한다.

```json
{
  "document_family": "ANSIM"
}
```

`ANSIM-` rule ID 접두어에서 scope를 추론하지 않는다.

### 6.4 Active rule manifest v2

Format:

```text
evidence-review/active-rule-manifest
version: 2
```

Top-level fields:

- `format`
- `version`
- `rules`

각 entry:

- `rule_id`
- `rule_version`
- `candidate_path`
- `candidate_sha256`
- `approved_rule_path`
- `approved_rule_sha256`
- `golden_report_path`
- `golden_report_sha256`
- `approval_path`
- `approval_sha256`
- `scope`
- `reviewer_id`
- `reviewed_at`
- `reason`

Active manifest에는 `generated_at`을 넣지 않는다. 동일 approval set은 실행 시각이나 enumeration order와 관계없이 동일 bytes를 생성해야 한다.

정렬 순서:

1. `rule_id`
2. canonical semantic version
3. `approval_path`

제약:

- 동일 `rule_id`는 active manifest에 한 version만 존재할 수 있다.
- 동일 approval path 또는 approval hash는 한 번만 사용한다.
- 서로 다른 rule은 같은 scope를 가질 수 있다.
- 같은 scope에 여러 rule이 적용되면 모두 selected된다.
- Rule priority나 상호 배제는 도입하지 않는다.
- `rules: []`은 valid하다.

### 6.5 Activation report

Format:

```text
evidence-review/rule-activation-report
version: 1
```

필드:

- `format`
- `version`
- `status`: `ACTIVATED` 또는 `BLOCKED`
- `approval_count`
- `activated_rule_count`
- `approval_files`
- `findings`
- `active_manifest_sha256`: 성공 시 SHA, 실패 시 null

Findings는 `artifact_path`, `rule_id`, `code`, `message`를 포함하며 deterministic ordering을 사용한다.

Validation 실패 시 activator는 **BLOCKED report만 create-only로 게시**하고 active manifest는 만들지 않는다. 성공 시 report와 manifest를 둘 다 create-only로 게시한다.

### 6.6 Rule selection result

Format:

```text
evidence-review/rule-selection-result
version: 1
```

Status:

- `SELECTED`
- `ABSTAIN`
- `BLOCKED`

공통 fields:

- `format`
- `version`
- `status`
- `context`
- `manifest_sha256`
- `selected_rules`
- `excluded_rules`
- `reasons`

`selected_rules`에는 rule ID, version, approved rule path/hash와 scope가 포함된다.

`excluded_rules`에는 rule ID, version과 다음 code 중 하나가 포함된다.

- `MISSING_SCOPE_VALUE`
- `SCOPE_MISMATCH`

Valid manifest에서 selected rule이 0개면:

```text
status = ABSTAIN
reasons = [NO_APPLICABLE_ACTIVE_RULE]
```

Manifest 또는 committed authority artifact가 손상되면:

```text
status = BLOCKED
```

대표 blocking reason:

- `RULE_GOVERNANCE_LEGACY_MANIFEST`
- `ACTIVE_MANIFEST_INVALID`
- `ACTIVE_RULE_HASH_MISMATCH`
- `APPROVAL_HASH_MISMATCH`
- `GOLDEN_REPORT_HASH_MISMATCH`
- `GOLDEN_REPORT_NOT_PASSING`
- `CANDIDATE_HASH_MISMATCH`
- `DUPLICATE_ACTIVE_RULE_ID`
- `UNSAFE_ARTIFACT_PATH`

`BLOCKED`에서 일부 valid rule만 선택하는 partial fallback은 금지한다.

## 7. Components

### 7.1 Contract module

책임:

- 다섯 versioned JSON contract의 strict decode/encode
- exact key, SHA, timestamp, path, enum, count와 uniqueness 검증
- canonical serialization

Contract module은 file system을 읽지 않는다.

### 7.2 Activation-time artifact verifier

책임:

- repository root 아래 safe relative path 해석
- symlink, traversal와 case-fold collision 차단
- candidate, approved rule, golden report와 approval bytes 검증
- fixture manifest, fixture, expected와 actual output bytes 검증
- rule identity/version 교차 검증

Golden `actual_path`는 activation 시점에 존재해야 한다. 이 output은 ignored `build/` 아래에 있을 수 있으며 runtime package에 포함될 필요는 없다.

### 7.3 Deterministic activator

입력:

- repository root
- explicit approval file 목록 또는 approval directory
- create-only output manifest path
- create-only activation report path

처리:

1. Approval files를 normalized path 순서로 수집한다.
2. 각 approval을 strict decode한다.
3. 연결 candidate, approved rule와 golden report를 검증한다.
4. Golden report의 PASS status, counts와 case bytes를 검증한다.
5. Duplicate rule ID, version, path와 hash 충돌을 검사한다.
6. 모든 approval이 valid하면 v2 manifest를 canonical JSON으로 생성한다.
7. Success report와 manifest를 create-only로 게시한다.
8. Invalid approval이 하나라도 있으면 BLOCKED report만 게시한다.

Approval directory가 비어 있으면 valid empty manifest와 `ACTIVATED` report를 생성한다.

### 7.4 Runtime authority verifier

Runtime은 activation-time ignored output에 의존하지 않는다. 다음 committed authority만 다시 검증한다.

- active manifest bytes
- approval artifact bytes
- golden report bytes와 internal PASS/count consistency
- candidate rule bytes
- approved rule bytes
- 모든 identity, path와 hash binding

Runtime은 golden case의 ignored `actual_path` 존재를 요구하지 않는다. Actual output 재검증은 activation/acceptance 책임이다.

Checked-in artifact가 activation 이후 변경될 수 있으므로 runtime load 때 authority verification을 반복한다.

### 7.5 Scope selector

책임:

- 검증 완료된 active entries와 explicit context를 입력받는다.
- case-sensitive exact dimension match를 수행한다.
- deterministic selected/excluded 목록을 생성한다.
- 0개 selected 시 명시적 `ABSTAIN`을 반환한다.

Selector는 filename, document title, rule ID와 path를 보지 않는다.

### 7.6 Evaluator integration boundary

기존 evaluator는 `rules/approved`, `rules/candidates` 또는 legacy active manifest를 직접 탐색해서는 안 된다.

새 integration 순서:

1. Runtime authority verification
2. Scope selection
3. `BLOCKED`면 evaluation 중단
4. `ABSTAIN`이면 rule evaluation 없이 이유와 exclusion evidence 출력
5. `SELECTED`면 선택된 approved rule bytes만 evaluator에 전달

Evaluator 내부의 수학·논리 실행은 재작성하지 않는다.

## 8. CLI

### 8.1 Active manifest build

Activator는 checked-in manifest를 직접 덮어쓰지 않는다.

```powershell
evidence-review rules build-active-manifest `
  --repository-root . `
  --approvals rules/activation/approvals `
  --output build/rules/active.json `
  --report build/rules/activation-report.json
```

Exit codes:

- `0`: valid empty 또는 non-empty manifest 생성 성공
- `1`: final 또는 temporary output path가 이미 존재
- `2`: contract, hash, golden, scope 또는 I/O validation failure

Exit code 2에서도 가능한 경우 create-only BLOCKED report를 남긴다.

Checked-in update 절차:

1. Empty build path에 v2 manifest 생성
2. Runtime validator로 build output 재검증
3. 기존 checked-in manifest와 diff 검토
4. 명시적 repository change로 `rules/manifests/active.json` 교체

### 8.2 Active manifest validate and select

```powershell
evidence-review rules select `
  --repository-root . `
  --manifest rules/manifests/active.json `
  --context context.json
```

Stdout은 canonical rule-selection-result JSON이다.

Exit codes:

- `0`: `SELECTED` 또는 정상 `ABSTAIN`
- `2`: `BLOCKED`

`ABSTAIN`은 설명 가능한 정상 결과이므로 nonzero exit code를 사용하지 않는다.

## 9. Publication and error handling

- Input artifact는 read-only다.
- Output manifest와 report는 create-only다.
- Temporary file은 final output과 같은 directory에 생성한다.
- Existing user file을 덮어쓰거나 삭제하지 않는다.
- Success publication 중 하나만 게시되면 현재 실행이 게시한 output만 rollback한다.
- Concurrent creator가 만든 file은 제거하지 않는다.
- Validation failure는 report-only publication이므로 manifest rollback 대상이 없다.
- Finding order는 artifact path, rule ID, reason code 순이다.

## 10. Existing ANSIM rule migration

기존 6개 active entry 각각에 대해 다음을 수행한다.

1. Current candidate와 approved rule hash 재계산
2. Existing fixture와 expected output 확인
3. Deterministic golden runner 실행
4. Actual output과 PASS golden report 생성
5. Scope `{ "document_family": "ANSIM" }`을 포함한 새 human approval artifact 생성
6. Approval에서 candidate, approved rule와 golden report hash 결속
7. Valid approvals로 v2 manifest 생성

안전 경계:

- Existing reviewer/date를 새 approval에 기계적으로 복사하지 않는다.
- 새 approval은 실제 reviewer와 새 timezone-aware timestamp를 기록한다.
- 기존 pytest가 존재한다는 사실만으로 golden PASS를 선언하지 않는다.
- Rule별 golden report가 없거나 FAIL이면 해당 rule을 v2에서 제외한다.
- Excluded rule을 legacy fallback으로 실행하지 않는다.

Committed acceptance evidence:

- approvals
- golden reports
- activation report
- active manifest v2 copy
- hashes와 reproduction README

Ignored execution output:

- generated actual case outputs
- temporary active manifest build directory
- transient logs

Acceptance evidence는 `docs/acceptance/issue-48/`에 보존한다.

## 11. Security and trust boundaries

- 모든 committed artifact path는 repository root 내부 regular file이어야 한다.
- Absolute path, `..`, traversal, symlink escape와 case-fold collision을 차단한다.
- SHA-256은 artifact integrity binding이며 reviewer identity 인증이 아니다.
- Approval reason과 reviewer ID는 audit record지만 법률적 승인 자체를 자동 증명하지 않는다.
- Candidate와 approved rule hash는 달라도 된다. Approval과 golden report가 두 hash를 정확히 결속해야 한다.
- Runtime은 network, Git history, filename inference 또는 environment variable을 approval authority로 사용하지 않는다.

## 12. Testing strategy

### Contract tests

- canonical round-trip
- unknown/missing field
- duplicate JSON key
- uppercase/invalid SHA
- naive timestamp
- empty reviewer/reason
- unsafe path와 case-fold collision
- invalid counts/status
- duplicate rule identity
- legacy manifest rejection

### Golden verifier tests

- all-pass valid report
- zero-case rejection
- count mismatch
- fixture manifest tamper
- fixture/expected/actual output tamper
- candidate/approved rule tamper
- report `FAIL`
- identity/version mismatch
- source commit과 command presence

### Activator tests

- deterministic bytes independent of input enumeration order
- valid empty approval directory
- duplicate rule ID with multiple versions blocked
- same scope with different rule IDs allowed
- one invalid approval blocks entire manifest
- BLOCKED report-only publication
- output create-only
- concurrent output preservation
- success partial-publication rollback
- no generated timestamp

### Scope selector tests

- exact case-sensitive match
- optional dimensions
- missing required scope dimension in context
- mismatch exclusion
- multiple selected rules in canonical order
- no selected rule -> `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`
- invalid authority -> `BLOCKED`, never abstain

### Integration tests

- evaluator receives selected approved rules only
- candidate and unapproved rule are never executed
- legacy manifest does not silently run
- ANSIM context selects only migrated valid ANSIM rules
- non-ANSIM context never executes ANSIM rules
- missing context produces explicit abstention evidence
- tampered committed approval/golden/rule blocks runtime
- runtime does not require ignored actual outputs

### CI and packaging

- full pytest
- Ruff
- strict mypy
- compileall
- Python 3.11 wheel build/install/resource/entrypoint
- Python 3.13 wheel build/install/resource/entrypoint
- Windows workspace validator
- Ubuntu workspace validator

## 13. Documentation and acceptance evidence

Add or update:

- `docs/RULE_ACTIVATION_GOVERNANCE.md`
- CLI section in `README.md` or `VALIDATE.md`
- `docs/acceptance/issue-48/README.md`
- acceptance approvals
- golden reports
- activation report
- v2 active manifest copy and hashes

Acceptance README records:

- source commit
- activation command
- approval and activated rule count
- included and excluded rule IDs
- candidate, approved rule, golden, approval, report와 manifest hashes
- scope values
- ANSIM selection example
- non-ANSIM and missing-context `ABSTAIN` examples
- final CI run and job conclusions

## 14. Completion criteria

Issue #48 is complete only when all conditions hold.

1. Runtime consumes only valid active manifest v2.
2. Active v2 is deterministically derived from valid approval artifacts.
3. Every active entry is bound to candidate, approved rule, PASS golden report, reviewer, timestamp, reason and explicit scope.
4. Existing ANSIM rules execute only under explicit ANSIM scope.
5. Nonmatching or missing scope produces `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE` with exclusion evidence.
6. Invalid or tampered governance artifact produces `BLOCKED` without partial fallback.
7. Candidate, unapproved rule and legacy manifest cannot enter the normal evaluator path.
8. Runtime validation does not depend on ignored golden actual outputs.
9. Acceptance artifacts and reproduction procedure are committed.
10. Full test, lint, type, compile, wheel and Windows/Ubuntu validation passes.
11. No claim of cryptographically verified reviewer identity is made.
