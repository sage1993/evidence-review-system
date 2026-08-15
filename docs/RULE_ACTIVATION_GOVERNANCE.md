# Rule Activation Governance

이 문서는 Rule Engine의 후보 규칙이 실제 런타임 권위가 되는 과정을 정의한다. 규칙 내용의 법률적 타당성과 최종 적합·부적합 판단은 사람이 담당한다. 시스템은 승인 artifact의 형식·hash·scope·golden evidence를 검증하고, 실행 가능한 규칙 집합을 결정적으로 선택할 뿐이다.

## 권위 사슬

```text
candidate rule
→ byte-preserving approved copy
→ deterministic golden cases / expected outputs
→ create-only golden report
→ named reviewer activation approval
→ derived active-rule manifest v2
→ exact scope selection
→ Rule Engine result
→ human review
```

런타임은 `rules/manifests/active.json`에 직접 적힌 경로만 읽는다. `rules/candidates/` 또는 manifest에 없는 `rules/approved/` 파일을 검색하거나 fallback하지 않는다. 한 entry의 approval, candidate, approved rule, golden report, fixture manifest, fixture 또는 expected hash가 손상되면 전체 active set은 `BLOCKED`가 된다.

## 1. Candidate 작성

Candidate는 constrained JSON rule이며 Python 코드나 임의 실행식을 포함할 수 없다. `rule_id`, semantic `version`, input schema, source citation, `human_decision_required=true`, expression을 명시한다.

Candidate 작성 자체는 활성화가 아니다. Candidate 디렉터리의 파일은 런타임에서 스캔하지 않는다.

## 2. Approved copy 생성

`approve_candidate()`는 named reviewer와 ISO 날짜를 요구하고 candidate bytes를 `rules/approved/<rule_id>@<version>.json`으로 create-only 복사한다. 이 작업은 `active.json`을 수정하지 않는다.

기존 `promote_candidate()` 경로는 `direct active promotion is disabled`로 거부된다. Approved copy도 아직 런타임 권위가 아니다.

## 3. Golden 실행

각 rule의 fixture manifest를 대상으로 실행한다.

```powershell
evidence-review rules run-golden `
  --repository-root . `
  --fixture-manifest rules/golden/fixtures/<RULE_ID>@<VERSION>.json `
  --actual-root build/rules/golden/actual `
  --report rules/golden/reports/<RULE_ID>@<VERSION>.json `
  --source-commit <40-character-commit-sha> `
  --command "python -m ansim_review rules run-golden"
```

Runner는 approved rule을 기존 `evaluate_rule()`로 실행한다. fixture, expected, generated actual, rule identity와 hash를 canonical JSON으로 결속한다. Actual과 report는 create-only로 게시하며 기존 파일을 덮어쓰지 않는다.

`rules/golden/reports/*.json`의 `status=PASS`는 기계 golden 비교 결과다. 법률 검토 승인이나 사람의 최종 판정이 아니다.

## 4. Human activation approval

Golden PASS 이후 named reviewer가 `rules/activation/approvals/<RULE_ID>@<VERSION>.json`을 만든다. Approval에는 다음이 포함된다.

- exact candidate path와 SHA-256
- exact approved-rule path와 SHA-256
- exact golden-report path와 SHA-256
- case-sensitive scope
- reviewer ID와 timezone 포함 검토 시각
- 활성화 이유

현재 모델은 내부 `PROCESS_ATTESTATION` 수준이다. JSON의 `reviewer_id`는 공개키 서명, 인증서 또는 GitHub 계정 세션으로 검증되지 않으므로 reviewer identity의 암호학적 증명이 아니다.

## 5. Active manifest 파생

Approval 디렉터리 전체를 검증한 후 v2 manifest를 파생한다.

```powershell
evidence-review rules build-active-manifest `
  --repository-root . `
  --approvals rules/activation/approvals `
  --output rules/manifests/active.json `
  --report build/rules/activation/activation-report.json
```

모든 approval이 유효한 경우에만 manifest를 게시한다. 하나라도 실패하면 active manifest를 만들지 않고 `BLOCKED` report만 create-only로 기록한다. 정상 변경은 기존 manifest를 명령으로 덮어쓰는 방식이 아니라 새 작업공간에서 파생한 파일을 PR로 교체하는 방식으로 검토한다.

## 6. Runtime selection

Selection context는 명시적 JSON object다.

```json
{
  "document_family": "ANSIM",
  "document_kind": null,
  "jurisdiction": null,
  "program": null
}
```

```powershell
evidence-review rules select `
  --repository-root . `
  --manifest rules/manifests/active.json `
  --context <workspace>/review-context.json
```

Scope 비교는 case-sensitive exact match다. Manifest 전체 권위 사슬을 먼저 검증한 뒤 일치하는 모든 규칙을 선택한다.

| 결과 | 의미 |
|---|---|
| `SELECTED` | 전체 governance 검증이 통과했고 하나 이상의 scope가 일치 |
| `ABSTAIN` | governance는 유효하지만 적용 가능한 active rule이 없음 |
| `BLOCKED` | manifest 또는 결속 artifact가 누락·손상·비정상 |

`ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`은 정상적인 비적용 결과다. `BLOCKED`를 `ABSTAIN`으로 낮추거나 일부 정상 entry만 실행하는 fallback은 허용하지 않는다.

## 7. 최종 판단 경계

Rule result의 `SATISFIED`와 `NOT_SATISFIED`는 constrained expression 결과다. 이는 사람의 법률적 최종 결정이 아니다. Machine packet의 `human_decision`은 항상 `null`로 유지하며, 사람 결정은 별도 append-only 기록에 남긴다.

## 8. Current verification

Use a sanitized workspace or the deterministic ANSIM compatibility fixtures under
`tests/fixtures/ansim/rules/` when exercising governance tests. Runtime rule
paths are always resolved from the supplied workspace; the repository does not
ship a user workspace as a runtime default.

```powershell
py -3.13 -m pytest tests/unit/rule_engine tests/integration/rule_engine -v
py -3.13 -m evidence_review documentation validate --repository-root .
```

Manual or external acceptance evidence is not stored in issue-number folders and
is never treated as GitHub Actions PASS unless the workflow actually ran.