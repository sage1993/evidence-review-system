# Rule Activation Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace direct active-manifest edits with hash-bound golden evidence, human approval artifacts, deterministic scoped activation, and explicit `ABSTAIN` or fail-closed `BLOCKED` rule selection.

**Architecture:** Introduce strict governance contracts and separate activation-time evidence verification from runtime authority verification. `rules/manifests/active.json` becomes a derived version 2 index; runtime validates its complete authority chain, selects exact-scope approved rules, and only then returns `RuleSpec` objects to the existing evaluator.

**Tech Stack:** Python 3.11+, standard-library runtime, dataclasses, `pathlib`, SHA-256, canonical JSON, pytest, Ruff, strict mypy, GitHub Actions on Ubuntu and Windows.

## Global Constraints

- Branch: `agent/rule-activation-governance`, based on `main@cb2fbf0a009ebd335393e8c0100755e029e3657a`.
- Runtime dependencies remain standard-library only.
- Governance JSON uses UTF-8, LF, canonical key order, duplicate-key rejection, unknown-field rejection, and lowercase 64-character SHA-256.
- Artifact paths are repository-root-relative POSIX paths. Absolute paths, parent traversal, symlink escape, and case-fold collisions are invalid.
- Reviewer identity and timezone-aware timestamp are recorded without claiming cryptographic verification.
- Legacy active manifests are never auto-upgraded and never used as fallback.
- Existing ANSIM rules activate only with new passing golden evidence and new approvals scoped to `document_family: ANSIM`.
- Valid empty manifests and valid scope mismatches return `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`.
- Invalid governance returns `BLOCKED`; partial fallback is forbidden.
- Activation verifies generated actual outputs. Runtime verifies committed authority artifacts and does not require ignored generated actual files.
- Activator publication is create-only. A blocked activation publishes a blocked report and no manifest.
- Every task follows RED → GREEN → refactor and ends with an isolated commit.

## File Map

### Production

- Create `src/ansim_review/rule_engine/governance_contract.py`.
- Create `src/ansim_review/rule_engine/governance_verify.py`.
- Create `src/ansim_review/rule_engine/golden.py`.
- Create `src/ansim_review/rule_engine/activation.py`.
- Create `src/ansim_review/rule_engine/selection.py`.
- Modify `src/ansim_review/rule_engine/manifest.py`.
- Modify `src/ansim_review/rule_engine/promotion.py`.
- Modify `src/ansim_review/contracts/formats.py`.
- Modify `src/ansim_review/cli.py`.

### Tests

- Create `tests/helpers/rule_governance.py`.
- Create `tests/unit/rule_engine/test_governance_contract.py`.
- Create `tests/unit/rule_engine/test_governance_test_helper.py`.
- Create `tests/unit/rule_engine/test_governance_verify.py`.
- Create `tests/unit/rule_engine/test_golden.py`.
- Create `tests/unit/rule_engine/test_activation.py`.
- Create `tests/unit/rule_engine/test_selection.py`.
- Modify `tests/unit/rule_engine/test_promotion.py`.
- Create `tests/integration/rule_engine/test_governed_manifest.py`.
- Create `tests/integration/rule_engine/test_governance_cli.py`.
- Create `tests/integration/rule_engine/test_ansim_governance_acceptance.py`.
- Create `tests/integration/rule_engine/test_governance_tamper_matrix.py`.
- Create `tests/unit/rule_engine/test_governance_documentation.py`.

### Governed artifacts

- Replace `rules/manifests/active.json` with `evidence-review/active-rule-manifest` version 2.
- Create six rule fixture manifests, case inputs, expected outputs, golden reports, and activation approvals.
- Create `docs/RULE_ACTIVATION_GOVERNANCE.md` and `docs/acceptance/issue-48/`.

---

## Task 1: Strict Governance Contracts

**Files:** `governance_contract.py`, `contracts/formats.py`, `test_governance_contract.py`

**Interfaces:**

- `load_rule_golden_report_bytes(data: bytes) -> RuleGoldenReport`
- `load_rule_activation_approval_bytes(data: bytes) -> RuleActivationApproval`
- `load_active_rule_manifest_bytes(data: bytes) -> ActiveRuleManifest`
- `rule_golden_report_bytes(report: RuleGoldenReport) -> bytes`
- `rule_activation_approval_bytes(approval: RuleActivationApproval) -> bytes`
- `active_rule_manifest_bytes(manifest: ActiveRuleManifest) -> bytes`

Required dataclasses include `RuleScope`, `GoldenCaseRecord`, `RuleGoldenReport`, `RuleActivationApproval`, `ActiveRuleEntry`, `ActiveRuleManifest`, `ActivationFinding`, `ActivationReport`, `RuleSelectionContext`, `ExcludedRule`, `SelectedRule`, and `RuleSelectionResult`.

- [ ] Add these exact format constants:

```python
RULE_GOLDEN_REPORT_FORMAT = "evidence-review/rule-golden-report"
RULE_ACTIVATION_APPROVAL_FORMAT = "evidence-review/rule-activation-approval"
ACTIVE_RULE_MANIFEST_FORMAT = "evidence-review/active-rule-manifest"
RULE_ACTIVATION_REPORT_FORMAT = "evidence-review/rule-activation-report"
RULE_SELECTION_RESULT_FORMAT = "evidence-review/rule-selection-result"
```

- [ ] Write failing tests for exact keys, duplicate JSON keys, lowercase hashes, timezone-aware timestamps, supported scope keys, safe relative paths, count consistency, unique case IDs, duplicate active rule IDs, and canonical round trips.

```python
def test_active_manifest_rejects_legacy_shape() -> None:
    with pytest.raises(ValueError, match="legacy active rule manifest"):
        load_active_rule_manifest_bytes(b'{"rules":[]}')


def test_scope_requires_document_family() -> None:
    payload = valid_approval_payload()
    payload["scope"] = {"jurisdiction": "Seoul"}
    with pytest.raises(ValueError, match="document_family"):
        load_rule_activation_approval_bytes(canonical_bytes(payload))
```

- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_governance_contract.py
```

- [ ] Implement frozen slotted dataclasses, duplicate-key-safe JSON decoding, exact field validation, and canonical serializers.
- [ ] Run GREEN and static checks:

```bash
pytest -v tests/unit/rule_engine/test_governance_contract.py
ruff check src/ansim_review/rule_engine/governance_contract.py tests/unit/rule_engine/test_governance_contract.py
mypy src/ansim_review/rule_engine/governance_contract.py
```

- [ ] Commit:

```bash
git add src/ansim_review/contracts/formats.py src/ansim_review/rule_engine/governance_contract.py tests/unit/rule_engine/test_governance_contract.py
git commit -m "feat: define strict rule governance contracts"
```

---

## Task 2: Shared Governance Test Builder

**Files:** `tests/helpers/rule_governance.py`, `test_governance_test_helper.py`

**Interfaces:**

- `build_valid_governance_tree(root: Path, *, rule_count: int = 1) -> GovernanceTree`
- `apply_governance_mutation(tree: GovernanceTree, mutation: str) -> None`

`GovernanceTree` stores manifest, approval, report, candidate, approved-rule, fixture-manifest, fixture, expected, and actual paths. Supported mutation names are:

- `active_manifest_bytes`
- `approval_bytes`
- `golden_report_bytes`
- `candidate_bytes`
- `approved_rule_bytes`
- `fixture_manifest_bytes`
- `fixture_bytes`
- `expected_bytes`
- `path_traversal`
- `duplicate_rule_id`

- [ ] Write a failing test that builds two rules, asserts every path exists, applies each mutation to a fresh copied tree, and verifies only the intended artifact changes.
- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_governance_test_helper.py
```

- [ ] Implement deterministic valid rule, fixture, expected result, report, approval, and active-manifest generation. Implement each named mutation with an explicit dispatch dictionary.
- [ ] Run GREEN:

```bash
pytest -v tests/unit/rule_engine/test_governance_test_helper.py
ruff check tests/helpers/rule_governance.py tests/unit/rule_engine/test_governance_test_helper.py
```

- [ ] Commit:

```bash
git add tests/helpers/rule_governance.py tests/unit/rule_engine/test_governance_test_helper.py
git commit -m "test: add rule governance fixture builder"
```

---

## Task 3: Safe Artifact and Hash Verification

**Files:** `governance_verify.py`, `test_governance_verify.py`

**Interfaces:**

- `VerificationMode = Literal["ACTIVATION", "RUNTIME"]`
- `verify_approval(repository_root: Path, approval_path: Path, *, mode: VerificationMode) -> VerifiedApproval`
- `verify_manifest_entry(repository_root: Path, entry: ActiveRuleEntry, *, mode: VerificationMode) -> VerifiedApproval`

- [ ] Write failing tests for traversal, absolute paths, symlink escape, case-fold collisions, every linked hash, identity mismatch, non-passing golden status, missing activation actual files, and runtime verification after actual files are removed.

```python
def test_runtime_does_not_require_generated_actual_output(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.actual_paths[0].unlink()
    verified = verify_approval(tmp_path, tree.approval_paths[0], mode="RUNTIME")
    assert verified.rule.rule_id == "TEST-RULE-001"
```

- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_governance_verify.py
```

- [ ] Implement `PurePosixPath` normalization, strict root containment, symlink rejection, case-fold inventory, SHA-256 checks, and cross-artifact rule identity checks.
- [ ] In activation mode verify actual files and expected/actual equality. In runtime mode verify committed authority artifacts without opening generated actual paths.
- [ ] Run GREEN:

```bash
pytest -v tests/unit/rule_engine/test_governance_verify.py
ruff check src/ansim_review/rule_engine/governance_verify.py tests/unit/rule_engine/test_governance_verify.py
mypy src/ansim_review/rule_engine/governance_verify.py
```

- [ ] Commit:

```bash
git add src/ansim_review/rule_engine/governance_verify.py tests/unit/rule_engine/test_governance_verify.py
git commit -m "feat: verify rule governance artifacts"
```

---

## Task 4: Deterministic Golden Runner

**Files:** `golden.py`, `test_golden.py`

**Interface:**

- `run_rule_golden(repository_root: Path, fixture_manifest_path: Path, actual_root: Path, report_path: Path, *, source_commit: str, command: str) -> RuleGoldenReport`

- [ ] Write failing tests for PASS, expected mismatch, duplicate case IDs, unresolved evidence, invalid calculation reference, identical bytes across separate empty roots, existing output, and concurrent publication.
- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_golden.py
```

- [ ] Implement strict `evidence-review/rule-golden-fixture` version 1 decoding. Evaluate every case through existing `evaluate_rule`, finalize each `RuleResult`, serialize canonical bytes, compare expected bytes, and build the report.
- [ ] Publish actuals and report via same-directory private files and `os.link`. Roll back only inodes published by the current invocation.
- [ ] Run GREEN:

```bash
pytest -v tests/unit/rule_engine/test_golden.py
ruff check src/ansim_review/rule_engine/golden.py tests/unit/rule_engine/test_golden.py
mypy src/ansim_review/rule_engine/golden.py
```

- [ ] Commit:

```bash
git add src/ansim_review/rule_engine/golden.py tests/unit/rule_engine/test_golden.py
git commit -m "feat: run deterministic rule golden cases"
```

---

## Task 5: Deterministic Scoped Activator

**Files:** `activation.py`, `test_activation.py`

**Interface:**

- `build_active_manifest(repository_root: Path, approval_paths: Sequence[Path], output_manifest: Path, output_report: Path) -> ActivationReport`

- [ ] Write failing tests for sorting, duplicate rule IDs across versions, duplicate approval paths, case-fold collisions, one bad approval blocking all, valid empty manifest, blocked report-only publication, output collisions, concurrent publication, and no partial manifest.
- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_activation.py
```

- [ ] Verify every approval in activation mode before constructing entries. Sort by rule ID, semantic version, and approval path. Reject more than one active version per rule ID.
- [ ] Publish manifest and report create-only. If report publication fails after manifest publication, remove only the manifest created by that invocation. Validation failure publishes only a blocked report.
- [ ] Run GREEN:

```bash
pytest -v tests/unit/rule_engine/test_activation.py
ruff check src/ansim_review/rule_engine/activation.py tests/unit/rule_engine/test_activation.py
mypy src/ansim_review/rule_engine/activation.py
```

- [ ] Commit:

```bash
git add src/ansim_review/rule_engine/activation.py tests/unit/rule_engine/test_activation.py
git commit -m "feat: build scoped active rule manifests"
```

---

## Task 6: Runtime Authority Loading and Scope Selection

**Files:** `selection.py`, `manifest.py`, `test_selection.py`, `test_governed_manifest.py`

**Interfaces:**

- `select_active_rules(entries: Sequence[ActiveRuleEntry], context: RuleSelectionContext, manifest_sha256: str) -> RuleSelectionResult`
- `load_governed_active_rules(project_root: Path, manifest_path: Path, context: RuleSelectionContext) -> GovernedRuleLoad`

- [ ] Write failing tests for case-sensitive matching, missing family, optional-dimension mismatch, unsupported context keys, multiple selected rules, deterministic exclusions, empty-manifest abstention, legacy-manifest blocking, and one tampered entry blocking every rule.
- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_selection.py tests/integration/rule_engine/test_governed_manifest.py
```

- [ ] Implement pure selection with `MISSING_SCOPE_VALUE` and `SCOPE_MISMATCH`. Zero matches returns `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`.
- [ ] Replace legacy loading: hash and strict-decode v2, runtime-verify all entries before selection, return no rules for abstention or blocking, and load only selected approved files.
- [ ] Remove or fail closed the old no-context loader.
- [ ] Run GREEN and evaluator regressions:

```bash
pytest -v tests/unit/rule_engine/test_selection.py tests/integration/rule_engine/test_governed_manifest.py tests/integration/rule_engine/test_rule_source_gate.py
ruff check src/ansim_review/rule_engine/selection.py src/ansim_review/rule_engine/manifest.py
mypy src/ansim_review/rule_engine/selection.py src/ansim_review/rule_engine/manifest.py
```

- [ ] Commit:

```bash
git add src/ansim_review/rule_engine/selection.py src/ansim_review/rule_engine/manifest.py tests/unit/rule_engine/test_selection.py tests/integration/rule_engine/test_governed_manifest.py
git commit -m "feat: select active rules by explicit scope"
```

---

## Task 7: Disable Direct Activation and Add CLI

**Files:** `promotion.py`, `cli.py`, `test_promotion.py`, `test_governance_cli.py`

**Interfaces and commands:**

- `approve_candidate(candidate_path: Path, approved_dir: Path, *, reviewer_id: str, review_date: str) -> Path`
- `evidence-review rules run-golden`
- `evidence-review rules build-active-manifest`
- `evidence-review rules select`

Exit codes:

- `0`: golden PASS, activation ACTIVE, selection SELECTED or ABSTAIN.
- `1`: create-only output collision.
- `2`: invalid input, golden FAIL, activation BLOCKED, or selection BLOCKED.

- [ ] Write failing tests proving legacy promotion cannot update `active.json`, approved-copy creation preserves candidate bytes, and each CLI prints one canonical status object.
- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_promotion.py tests/integration/rule_engine/test_governance_cli.py
```

- [ ] Implement approved-copy creation only. Keep `promote_candidate` as a compatibility function that raises `ValueError("direct active promotion is disabled")`.
- [ ] Add parsers, dispatch, canonical stdout, and exit-code mapping.
- [ ] Run GREEN and help checks:

```bash
pytest -v tests/unit/rule_engine/test_promotion.py tests/integration/rule_engine/test_governance_cli.py
python -m ansim_review rules --help
python -m ansim_review rules run-golden --help
python -m ansim_review rules build-active-manifest --help
python -m ansim_review rules select --help
```

- [ ] Commit:

```bash
git add src/ansim_review/rule_engine/promotion.py src/ansim_review/cli.py tests/unit/rule_engine/test_promotion.py tests/integration/rule_engine/test_governance_cli.py
git commit -m "feat: expose governed rule activation CLI"
```

---

## Task 8: Migrate Six Existing ANSIM Rules

**Exact fixture filenames:**

- `ANSIM-ARTERIAL-FRONTAGE-ONE-EIGHTH@1.0.0.json`
- `ANSIM-MINIMUM-SITE-AREA-1500@1.0.0.json`
- `ANSIM-TWO-ROAD-SIDES-6M@1.0.0.json`
- `ANSIM-ZONING-CHANGE-FAR-MAX-400@1.0.0.json`
- `ANSIM-ZONING-CHANGE-PUBLIC-CONTRIBUTION-MIN-15@1.0.0.json`
- `ANSIM-ZONING-CHANGE-RESIDENTIAL-RATIO-MIN-85@1.0.0.json`

- [ ] Write a failing repository acceptance test requiring exactly six IDs, at least two cases per rule, PASS reports, exact ANSIM scope, current hashes, and six v2 entries.
- [ ] Run RED:

```bash
pytest -v tests/integration/rule_engine/test_ansim_governance_acceptance.py
```

- [ ] Create satisfied and not-satisfied cases for every rule. Add an invalid-calculation-reference case for the frontage calculation rule. Preserve legal rule content.
- [ ] Generate golden outputs using this exact PowerShell loop:

```powershell
$sourceCommit = "cb4d387b17ae4232bee175866d3e2eed86016321"
$fixtures = Get-ChildItem -LiteralPath "rules/golden/fixtures" -Filter "*.json" | Sort-Object Name
foreach ($fixture in $fixtures) {
  $name = [System.IO.Path]::GetFileNameWithoutExtension($fixture.Name)
  $actualRoot = Join-Path "build/rules/golden/actual" $name
  $reportPath = Join-Path "build/rules/golden/reports" ($name + ".json")
  python -m ansim_review rules run-golden --repository-root . --fixture-manifest $fixture.FullName --actual-root $actualRoot --report $reportPath --source-commit $sourceCommit --command "python -m ansim_review rules run-golden"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

- [ ] Copy only PASS reports to `rules/golden/reports/`; do not commit generated actual files.
- [ ] Create six approvals from current bytes with exact scope `{ "document_family": "ANSIM" }`, reviewer ID, timezone-aware timestamp, `APPROVED`, and non-empty reason.
- [ ] Generate and compare two manifests:

```powershell
python -m ansim_review rules build-active-manifest --repository-root . --approvals rules/activation/approvals --output build/rules/a/active.json --report build/rules/a/report.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m ansim_review rules build-active-manifest --repository-root . --approvals rules/activation/approvals --output build/rules/b/active.json --report build/rules/b/report.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$hashA = (Get-FileHash build/rules/a/active.json -Algorithm SHA256).Hash
$hashB = (Get-FileHash build/rules/b/active.json -Algorithm SHA256).Hash
if ($hashA -ne $hashB) { throw "active manifest is not deterministic" }
Copy-Item build/rules/a/active.json rules/manifests/active.json -Force
```

- [ ] Run GREEN:

```bash
pytest -v tests/integration/rule_engine/test_ansim_governance_acceptance.py tests/integration/rule_engine
```

- [ ] Commit:

```bash
git add rules/golden rules/activation rules/manifests/active.json tests/integration/rule_engine/test_ansim_governance_acceptance.py
git commit -m "feat: govern active ansim rules with golden evidence"
```

---

## Task 9: Tamper and Abstention Matrix

**Files:** `test_governance_tamper_matrix.py`, `test_governed_manifest.py`, `test_governance_cli.py`

- [ ] Add this concrete test:

```python
@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("active_manifest_bytes", "ACTIVE_MANIFEST_INVALID"),
        ("approval_bytes", "APPROVAL_HASH_MISMATCH"),
        ("golden_report_bytes", "GOLDEN_REPORT_HASH_MISMATCH"),
        ("candidate_bytes", "CANDIDATE_HASH_MISMATCH"),
        ("approved_rule_bytes", "ACTIVE_RULE_HASH_MISMATCH"),
        ("fixture_manifest_bytes", "GOLDEN_FIXTURE_MANIFEST_HASH_MISMATCH"),
        ("fixture_bytes", "GOLDEN_FIXTURE_HASH_MISMATCH"),
        ("expected_bytes", "GOLDEN_EXPECTED_HASH_MISMATCH"),
        ("path_traversal", "UNSAFE_ARTIFACT_PATH"),
        ("duplicate_rule_id", "DUPLICATE_ACTIVE_RULE_ID"),
    ],
)
def test_tamper_blocks_all_rules(
    mutation: str,
    expected_reason: str,
    tmp_path: Path,
) -> None:
    tree = build_valid_governance_tree(tmp_path, rule_count=2)
    apply_governance_mutation(tree, mutation)
    loaded = load_governed_active_rules(
        tmp_path,
        tree.manifest_path,
        RuleSelectionContext(document_family="ANSIM"),
    )
    assert loaded.rules == ()
    assert loaded.selection.status == "BLOCKED"
    assert expected_reason in loaded.selection.reasons
```

- [ ] Add normal abstention tests for empty v2, missing family, `document_family=OTHER`, and optional program/jurisdiction mismatches. Require exit code `0`, `ABSTAIN`, and deterministic exclusions.
- [ ] Add no-bypass tests proving candidates are never scanned, unmanifested approved rules are never loaded, direct promotion cannot mutate the manifest, and one corrupted entry prevents all execution.
- [ ] Run:

```bash
pytest -v tests/unit/rule_engine tests/integration/rule_engine
```

- [ ] Commit:

```bash
git add tests/integration/rule_engine/test_governance_tamper_matrix.py tests/integration/rule_engine/test_governed_manifest.py tests/integration/rule_engine/test_governance_cli.py
git commit -m "test: enforce fail-closed rule governance"
```

---

## Task 10: Documentation, Acceptance, and Full Verification

**Files:** `docs/RULE_ACTIVATION_GOVERNANCE.md`, `docs/acceptance/issue-48/`, `README.md`, `test_governance_documentation.py`

- [ ] Write failing documentation tests requiring real CLI parsers, strict-decodable acceptance JSON, existing referenced paths, exact reproduction commands, and the reviewer-identity limitation.
- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_governance_documentation.py
```

- [ ] Document candidate authoring, approved-copy creation, golden execution, human approval, create-only activation, PR replacement of the derived manifest, runtime selection, and `ABSTAIN` versus `BLOCKED`.
- [ ] Generate `activation-report.json`, `ansim-selection.json`, and `non-ansim-abstention.json` from real repository artifacts. ANSIM selection must contain six rules. Non-ANSIM selection must be `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`.
- [ ] Run documentation tests and commit:

```bash
pytest -v tests/unit/rule_engine/test_governance_documentation.py
git add docs/RULE_ACTIVATION_GOVERNANCE.md docs/acceptance/issue-48 README.md tests/unit/rule_engine/test_governance_documentation.py
git commit -m "docs: record governed rule activation acceptance"
```

- [ ] Run full validation:

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
python -m build --wheel
```

- [ ] Install the wheel in isolated Python 3.11 and 3.13 environments. Run `evidence-review --help`, `evidence-review rules --help`, and a non-ANSIM selection. Require canonical abstention without source-checkout imports.
- [ ] Self-review for plain-JSON bypass, direct manifest writes, directory scans, unsafe paths, partial fallback, generated-actual runtime dependency, missing reviewer limitation, and stale hashes.
- [ ] Push and require GitHub Actions success for pytest, Ruff, strict mypy, compileall, Python 3.11/3.13 wheel, Ubuntu validator, and Windows validator.
- [ ] Update Issue #48 and parent #27 with PR URL, exact HEAD, Actions run, test counts, manifest hash, six IDs, selection evidence, acceptance path, and final-human-judgment boundary.
- [ ] Leave Issue #48 open until merge and acceptance artifacts are present on `main`.
