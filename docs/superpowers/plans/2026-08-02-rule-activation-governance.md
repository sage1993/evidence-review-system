# Rule Activation Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace direct active-manifest edits with hash-bound golden evidence, human approval artifacts, deterministic scoped activation, and explicit `ABSTAIN` or fail-closed `BLOCKED` selection.

**Architecture:** Add strict governance contracts and separate activation-time evidence verification from runtime authority verification. `rules/manifests/active.json` becomes a derived version 2 index; runtime validates the complete authority chain, selects exact-scope rules, and only then returns approved `RuleSpec` objects to the existing evaluator.

**Tech Stack:** Python 3.11+, standard-library runtime, dataclasses, `pathlib`, SHA-256, canonical JSON, pytest, Ruff, strict mypy, GitHub Actions on Ubuntu and Windows.

## Global Constraints

- Work on `agent/rule-activation-governance`, based on `main@cb2fbf0a009ebd335393e8c0100755e029e3657a`.
- Runtime dependencies remain standard-library only.
- Governance JSON is UTF-8 with LF, canonical key order, duplicate-key rejection, unknown-field rejection, and lowercase 64-character SHA-256.
- Artifact paths are repository-root-relative POSIX paths. Reject absolute paths, `..`, traversal, symlink escape, and case-fold collisions.
- Reviewer ID and timezone-aware timestamp are records, not cryptographic identity verification.
- Legacy active manifests are never auto-upgraded and never used as runtime fallback.
- Existing ANSIM rules activate only with new passing golden evidence and new approvals scoped to `document_family: ANSIM`.
- Valid empty manifests and valid scope mismatches produce `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`.
- Invalid or tampered governance produces `BLOCKED`; partial fallback is forbidden.
- Activation verifies fixture, expected, and generated actual bytes. Runtime does not depend on ignored generated actual files.
- Activator output is create-only. A blocked activation publishes only a blocked report and no manifest.
- Every task uses RED → GREEN → refactor and ends with an isolated commit.

## File Map

### Production

- Create `src/ansim_review/rule_engine/governance_contract.py` — strict formats, dataclasses, decoders, serializers.
- Create `src/ansim_review/rule_engine/governance_verify.py` — safe paths, hashes, cross-artifact identity checks.
- Create `src/ansim_review/rule_engine/golden.py` — deterministic golden execution and report generation.
- Create `src/ansim_review/rule_engine/activation.py` — deterministic manifest/report generation and create-only publication.
- Create `src/ansim_review/rule_engine/selection.py` — exact scope selection and result construction.
- Modify `src/ansim_review/rule_engine/manifest.py` — governed v2 loading with explicit context.
- Modify `src/ansim_review/rule_engine/promotion.py` — approved-copy creation only; no manifest mutation.
- Modify `src/ansim_review/contracts/formats.py` — governance format constants.
- Modify `src/ansim_review/cli.py` — golden, activation, and selection commands.

### Test support and tests

- Create `tests/helpers/rule_governance.py` — reusable valid governance tree and exact mutation helpers.
- Create `tests/unit/rule_engine/test_governance_contract.py`.
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

### Repository artifacts

- Replace `rules/manifests/active.json` with `evidence-review/active-rule-manifest` version 2.
- Create `rules/golden/fixtures/`, `rules/golden/cases/`, `rules/golden/expected/`, and `rules/golden/reports/` artifacts for six ANSIM rules.
- Create six files under `rules/activation/approvals/`.
- Create `docs/RULE_ACTIVATION_GOVERNANCE.md` and `docs/acceptance/issue-48/`.

---

## Task 1: Strict Governance Contracts

**Files**

- Create `src/ansim_review/rule_engine/governance_contract.py`.
- Modify `src/ansim_review/contracts/formats.py`.
- Create `tests/unit/rule_engine/test_governance_contract.py`.

**Interfaces**

```python
@dataclass(frozen=True, slots=True)
class RuleScope:
    document_family: str
    document_kind: str | None = None
    jurisdiction: str | None = None
    program: str | None = None

@dataclass(frozen=True, slots=True)
class ActiveRuleManifest:
    rules: tuple[ActiveRuleEntry, ...]
```

Provide strict loaders and canonical serializers for:

- `evidence-review/rule-golden-report` version 1
- `evidence-review/rule-activation-approval` version 1
- `evidence-review/active-rule-manifest` version 2
- `evidence-review/rule-activation-report` version 1
- `evidence-review/rule-selection-result` version 1

- [ ] Write failing tests for exact keys, duplicate JSON keys, lowercase hashes, timezone-aware timestamps, supported scope keys, safe relative path syntax, count consistency, unique case IDs, duplicate active rule IDs, and canonical round trips.

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

Expected: import failure because the contract module does not exist.

- [ ] Implement frozen slotted dataclasses, duplicate-key-safe JSON decoding, exact field validation, canonical serialization, and the five format constants.
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

**Files**

- Create `tests/helpers/rule_governance.py`.
- Create `tests/unit/rule_engine/test_governance_test_helper.py`.

**Interfaces**

```python
@dataclass(frozen=True, slots=True)
class GovernanceTree:
    root: Path
    manifest_path: Path
    approval_paths: tuple[Path, ...]
    golden_report_paths: tuple[Path, ...]
    candidate_paths: tuple[Path, ...]
    approved_rule_paths: tuple[Path, ...]
    fixture_manifest_paths: tuple[Path, ...]
    fixture_paths: tuple[Path, ...]
    expected_paths: tuple[Path, ...]
    actual_paths: tuple[Path, ...]


def build_valid_governance_tree(root: Path, *, rule_count: int = 1) -> GovernanceTree:
    ...


def apply_governance_mutation(tree: GovernanceTree, mutation: str) -> None:
    ...
```

The two function bodies above must be fully implemented in this task. `apply_governance_mutation` supports these exact names:

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

- [ ] Write a failing test that builds two rules, validates all returned paths exist, applies each mutation in a copied tree, and verifies only the intended file or field changes.
- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_governance_test_helper.py
```

- [ ] Implement canonical candidate, approved rule, golden case, expected result, report, approval, and manifest generation using current production serializers where available and local deterministic helper serialization otherwise.
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

**Files**

- Create `src/ansim_review/rule_engine/governance_verify.py`.
- Create `tests/unit/rule_engine/test_governance_verify.py`.

**Interfaces**

```python
VerificationMode = Literal["ACTIVATION", "RUNTIME"]

@dataclass(frozen=True, slots=True)
class VerifiedApproval:
    approval_path: str
    approval: RuleActivationApproval
    rule: RuleSpec
    golden_report: RuleGoldenReport


def verify_approval(
    repository_root: Path,
    approval_path: Path,
    *,
    mode: VerificationMode,
) -> VerifiedApproval:
    ...
```

- [ ] Write failing tests for traversal, absolute path, symlink escape, case-fold collision, wrong candidate/approved/golden/fixture/expected hashes, identity mismatch, failing golden status, missing activation actual files, and runtime operation after actual files are removed.

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

- [ ] Implement repository-contained resolution with `PurePosixPath`, `Path.resolve(strict=True)`, parent containment, symlink rejection, case-fold path inventory, SHA-256 checks, and identity cross-checks.
- [ ] Activation mode verifies actual files and expected/actual equality. Runtime mode verifies committed authority files but does not require actual files.
- [ ] Run GREEN and static checks:

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

**Files**

- Create `src/ansim_review/rule_engine/golden.py`.
- Create `tests/unit/rule_engine/test_golden.py`.

**Interface**

```python
def run_rule_golden(
    repository_root: Path,
    fixture_manifest_path: Path,
    actual_root: Path,
    report_path: Path,
    *,
    source_commit: str,
    command: str,
) -> RuleGoldenReport:
    ...
```

The function body must be fully implemented. It decodes `evidence-review/rule-golden-fixture` version 1, evaluates every case using existing `evaluate_rule`, writes full finalized canonical `RuleResult` bytes, compares them to committed expected bytes, and publishes actuals and report create-only.

- [ ] Write failing tests for PASS, expected mismatch, duplicate case IDs, unresolved evidence, invalid calculation reference, deterministic output across separate empty roots, existing output, and concurrent output creation.
- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_golden.py
```

- [ ] Implement strict fixture and case decoding. Use same-directory private files and `os.link` for no-overwrite publication. Remove only files published by the current invocation on rollback.
- [ ] Run GREEN and static checks:

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

**Files**

- Create `src/ansim_review/rule_engine/activation.py`.
- Create `tests/unit/rule_engine/test_activation.py`.

**Interface**

```python
def build_active_manifest(
    repository_root: Path,
    approval_paths: Sequence[Path],
    output_manifest: Path,
    output_report: Path,
) -> ActivationReport:
    ...
```

- [ ] Write failing tests for deterministic sort, duplicate rule ID across versions, duplicate approval path, case-fold collision, one bad approval blocking all entries, valid empty manifest, blocked report-only publication, existing outputs, concurrent output creation, and no partial manifest.
- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_activation.py
```

- [ ] Implement all-approval validation with `mode="ACTIVATION"`. Construct entries only from verified dataclasses, sort by rule ID/version/approval path, and reject multiple active versions for one rule ID.
- [ ] Publish manifest and report with hard-link no-overwrite semantics. If report publication fails after manifest publication, unlink only the manifest inode created by the current run. Validation failure writes only a blocked report.
- [ ] Run GREEN and static checks:

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

**Files**

- Create `src/ansim_review/rule_engine/selection.py`.
- Modify `src/ansim_review/rule_engine/manifest.py`.
- Create `tests/unit/rule_engine/test_selection.py`.
- Create `tests/integration/rule_engine/test_governed_manifest.py`.

**Interfaces**

```python
@dataclass(frozen=True, slots=True)
class GovernedRuleLoad:
    selection: RuleSelectionResult
    rules: tuple[RuleSpec, ...]


def select_active_rules(
    entries: Sequence[ActiveRuleEntry],
    context: RuleSelectionContext,
    manifest_sha256: str,
) -> RuleSelectionResult:
    ...


def load_governed_active_rules(
    project_root: Path,
    manifest_path: Path,
    context: RuleSelectionContext,
) -> GovernedRuleLoad:
    ...
```

- [ ] Write failing tests for exact case-sensitive scope matching, missing family, optional dimension mismatch, unsupported context keys, multiple selected rules, deterministic exclusions, empty manifest abstention, legacy manifest blocking, and one tampered entry blocking all rules.
- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_selection.py tests/integration/rule_engine/test_governed_manifest.py
```

- [ ] Implement pure scope selection with `MISSING_SCOPE_VALUE` and `SCOPE_MISMATCH` exclusions. Zero selected rules yields `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`.
- [ ] Replace legacy loading. Read and hash v2 manifest, runtime-verify every entry before selecting, return no rules for `ABSTAIN` or `BLOCKED`, and load only selected approved files.
- [ ] Remove or fail closed the old no-context loader so callers cannot bypass scope selection.
- [ ] Run GREEN and regressions:

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

**Files**

- Modify `src/ansim_review/rule_engine/promotion.py`.
- Modify `src/ansim_review/cli.py`.
- Modify `tests/unit/rule_engine/test_promotion.py`.
- Create `tests/integration/rule_engine/test_governance_cli.py`.

**Interfaces**

```python
def approve_candidate(
    candidate_path: Path,
    approved_dir: Path,
    *,
    reviewer_id: str,
    review_date: str,
) -> Path:
    ...
```

Commands:

- `evidence-review rules run-golden`
- `evidence-review rules build-active-manifest`
- `evidence-review rules select`

Exit codes:

- `0`: golden PASS, activation ACTIVE, selection SELECTED or ABSTAIN.
- `1`: create-only output collision.
- `2`: invalid input, golden FAIL, activation BLOCKED, or selection BLOCKED.

- [ ] Write failing tests proving `promote_candidate` cannot update `active.json`, approved-copy creation preserves candidate bytes, and each CLI prints one canonical status JSON.
- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_promotion.py tests/integration/rule_engine/test_governance_cli.py
```

- [ ] Implement `approve_candidate` as immutable copy creation only. Keep `promote_candidate` as a fail-closed compatibility function raising `ValueError("direct active promotion is disabled")`.
- [ ] Add argument parsers, command dispatch, canonical stdout, and exit-code mapping.
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

## Task 8: Migrate the Six Existing ANSIM Rules

**Files**

Create fixture manifests with these exact filenames:

- `ANSIM-ARTERIAL-FRONTAGE-ONE-EIGHTH@1.0.0.json`
- `ANSIM-MINIMUM-SITE-AREA-1500@1.0.0.json`
- `ANSIM-TWO-ROAD-SIDES-6M@1.0.0.json`
- `ANSIM-ZONING-CHANGE-FAR-MAX-400@1.0.0.json`
- `ANSIM-ZONING-CHANGE-PUBLIC-CONTRIBUTION-MIN-15@1.0.0.json`
- `ANSIM-ZONING-CHANGE-RESIDENTIAL-RATIO-MIN-85@1.0.0.json`

Create matching directories under `rules/golden/cases/` and `rules/golden/expected/`, matching reports under `rules/golden/reports/`, and matching approvals under `rules/activation/approvals/`. Modify `rules/manifests/active.json`. Create `tests/integration/rule_engine/test_ansim_governance_acceptance.py`.

- [ ] Write a failing repository acceptance test requiring exactly the six rule IDs, at least two cases per rule, PASS reports, approvals scoped to exact `ANSIM`, current hashes, and six v2 active entries.
- [ ] Run RED:

```bash
pytest -v tests/integration/rule_engine/test_ansim_governance_acceptance.py
```

- [ ] Create at least one satisfied and one not-satisfied case for each rule. Add an invalid-calculation-reference case for the calculation-backed frontage rule. Do not change rule legal content.
- [ ] Generate all golden outputs with this exact PowerShell loop:

```powershell
$sourceCommit = "cb4d387b17ae4232bee175866d3e2eed86016321"
$fixtures = Get-ChildItem -LiteralPath "rules/golden/fixtures" -Filter "*.json" | Sort-Object Name
foreach ($fixture in $fixtures) {
  $name = [System.IO.Path]::GetFileNameWithoutExtension($fixture.Name)
  $actualRoot = Join-Path "build/rules/golden/actual" $name
  $reportPath = Join-Path "build/rules/golden/reports" ($name + ".json")
  python -m ansim_review rules run-golden `
    --repository-root . `
    --fixture-manifest $fixture.FullName `
    --actual-root $actualRoot `
    --report $reportPath `
    --source-commit $sourceCommit `
    --command "python -m ansim_review rules run-golden"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

- [ ] Copy only PASS report JSON into `rules/golden/reports/`; never commit `build/rules/golden/actual/`.
- [ ] Create six approvals from current candidate, approved, and report bytes with exact scope `{ "document_family": "ANSIM" }`, reviewer ID, timezone-aware timestamp, `APPROVED`, and non-empty reason.
- [ ] Generate the candidate active manifest twice in separate empty directories:

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

## Task 9: End-to-End Tamper and Abstention Matrix

**Files**

- Create `tests/integration/rule_engine/test_governance_tamper_matrix.py`.
- Modify `tests/integration/rule_engine/test_governed_manifest.py`.
- Modify `tests/integration/rule_engine/test_governance_cli.py`.

- [ ] Add this concrete parameterized test using Task 2 helpers:

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

- [ ] Add normal non-blocking tests for empty v2 manifest, missing family, `document_family=OTHER`, and optional program/jurisdiction mismatches. Require exit code `0`, `ABSTAIN`, `NO_APPLICABLE_ACTIVE_RULE`, and deterministic exclusions.
- [ ] Add no-bypass regressions proving candidates are never scanned, unmanifested approved rules are never loaded, direct promotion cannot mutate the manifest, and one corrupted entry prevents all rule execution.
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

**Files**

- Create `docs/RULE_ACTIVATION_GOVERNANCE.md`.
- Create `docs/acceptance/issue-48/README.md`.
- Create `docs/acceptance/issue-48/activation-report.json`.
- Create `docs/acceptance/issue-48/ansim-selection.json`.
- Create `docs/acceptance/issue-48/non-ansim-abstention.json`.
- Modify `README.md`.
- Create `tests/unit/rule_engine/test_governance_documentation.py`.

- [ ] Write failing documentation tests requiring real CLI parsers, strict-decodable acceptance JSON, existing referenced paths, exact reproduction commands, and the reviewer-identity limitation.
- [ ] Run RED:

```bash
pytest -v tests/unit/rule_engine/test_governance_documentation.py
```

- [ ] Document candidate authoring, approved-copy creation, golden case execution, human approval, create-only activation, PR replacement of the derived manifest, runtime selection, and `ABSTAIN` versus `BLOCKED`.
- [ ] Generate acceptance outputs from real repository artifacts. `ansim-selection.json` must select six rules; `non-ansim-abstention.json` must contain `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`.
- [ ] Run documentation tests and commit:

```bash
pytest -v tests/unit/rule_engine/test_governance_documentation.py
git add docs/RULE_ACTIVATION_GOVERNANCE.md docs/acceptance/issue-48 README.md tests/unit/rule_engine/test_governance_documentation.py
git commit -m "docs: record governed rule activation acceptance"
```

- [ ] Run the full validation matrix:

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
python -m build --wheel
```

- [ ] Install the wheel in isolated Python 3.11 and 3.13 environments and run:

```bash
evidence-review --help
evidence-review rules --help
evidence-review rules select --repository-root . --manifest rules/manifests/active.json --document-family OTHER
```

Expected: help succeeds and selection returns canonical `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE` without source-checkout imports.

- [ ] Self-review the branch for plain-JSON governance bypass, direct manifest writes, candidate/approved directory scans, unsafe path handling, partial fallback, runtime actual-output dependency, missing reviewer limitation, and stale ANSIM hashes.
- [ ] Push and require GitHub Actions success for full pytest, Ruff, strict mypy, compileall, Python 3.11/3.13 wheel, Ubuntu validator, and Windows validator.
- [ ] Post Issue #48 and parent #27 updates with PR URL, exact HEAD, Actions run, test counts, manifest SHA-256, six rule IDs, selected and abstained results, acceptance path, and final-human-judgment boundary.
- [ ] Leave Issue #48 open until the PR is merged and acceptance artifacts are present on `main`.
