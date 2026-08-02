# Issue #48 Acceptance Evidence

상태: **CI_BLOCKED**

이 디렉터리는 scoped rule activation의 파생 acceptance artifact를 기록한다.

- `activation-report.json`: 6개 approval에서 파생된 v2 active manifest 요약
- `ansim-selection.json`: `document_family=ANSIM`에서 6개 규칙이 선택되는 예상 canonical 결과
- `non-ansim-abstention.json`: `document_family=OTHER`에서 `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`이 되는 예상 canonical 결과
- `ansim-context.json`, `non-ansim-context.json`: 재현용 explicit selection context

Manifest SHA-256:

```text
c4d41a402d39fea712a7ba6d80568595ef7be6fc1acc9cb63416b8c75020af76
```

## 재현 명령

각 `rules/golden/fixtures/*.json`에 대해:

```powershell
evidence-review rules run-golden `
  --repository-root . `
  --fixture-manifest <fixture-path> `
  --actual-root build/rules/golden/actual `
  --report <new-report-path> `
  --source-commit <40-character-commit-sha> `
  --command "python -m ansim_review rules run-golden"
```

새 작업공간에서 activation:

```powershell
evidence-review rules build-active-manifest `
  --repository-root . `
  --approvals rules/activation/approvals `
  --output rules/manifests/active.json `
  --report build/rules/activation/activation-report.json
```

Selection:

```powershell
evidence-review rules select `
  --repository-root . `
  --manifest rules/manifests/active.json `
  --context docs/acceptance/issue-48/ansim-context.json

evidence-review rules select `
  --repository-root . `
  --manifest rules/manifests/active.json `
  --context docs/acceptance/issue-48/non-ansim-context.json
```

## 제한

2026-08-02 현재 GitHub Actions run은 모든 job이 step 시작 전에 `steps=null`로 종료되고 있다. 따라서 이 파일들은 governance graph와 deterministic expected 결과를 기록하지만, 정상 CI에서 재실행·재현된 최종 acceptance가 아니다.

Approval의 `reviewer_id`는 내부 절차 기록이다. 공개키·인증서·계정 세션을 확인하지 않으므로 reviewer identity의 암호학적 증명이 아니다. 또한 기계 규칙 결과는 사람의 최종 법률 판단이 아니며 machine packet의 `human_decision`은 `null`로 유지된다.
