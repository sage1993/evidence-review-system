# Rule Activation Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace direct edits to the active rule manifest with hash-bound golden evidence, human approval artifacts, deterministic scoped activation, and explicit `ABSTAIN` or fail-closed `BLOCKED` runtime selection.

**Architecture:** Introduce strict versioned governance contracts, separate activation-time evidence verification from runtime authority verification, and make `rules/manifests/active.json` a derived version 2 index. Existing evaluator logic remains unchanged; a governed loader validates the entire manifest, selects exact-scope approved rules, and only then returns `RuleSpec` objects for evaluation.

**Tech Stack:** Python 3.11+, standard library only at runtime, dataclasses, `pathlib`, SHA-256, canonical JSON helpers, pytest, Ruff, strict mypy, GitHub Actions on Ubuntu and Windows.

## Global Constraints

- Base implementation branch: `agent/rule-activation-governance`, based on `main@cb2fbf0a009ebd335393e8c0100755e029e3657a`.
- Runtime dependencies remain standard-library only.
- Governance JSON uses UTF-8, LF newline, canonical key ordering, duplicate-key rejection, unknown-field rejection, and lowercase 64-character SHA-256.
- All artifact paths are repository-root-relative POSIX paths; reject absolute paths, `..`, path traversal, symlink escape, and case-fold collisions.
- Reviewer IDs and timezone-aware timestamps are recorded but are not cryptographic identity verification.
- Legacy active manifests are never auto-upgraded or used as runtime fallback.
- Existing ANSIM rules activate only with new passing golden reports and new approval artifacts whose explicit scope contains `document_family: ANSIM`.
- A valid empty manifest or valid scope mismatch produces `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`.
- Invalid or tampered governance artifacts produce `BLOCKED`; partial fallback to valid rules is forbidden.
- Activation verifies fixture, expected, and generated actual output bytes. Runtime verification does not depend on ignored `build/` actual outputs.
- Activator outputs are create-only. A blocked activation publishes only a create-only blocked report and no manifest.
- Every implementation task follows RED → GREEN → refactor and ends with an isolated commit.

---

## File Structure

### Production modules

- Create `src/ansim_review/rule_engine/governance_contract.py`: strict dataclasses, decoders, canonical serializers, enums, and payload builders for all governance formats.
- Create `src/ansim_review/rule_engine/governance_verify.py`: safe path resolution, hash verification, identity cross-checks, and activation/runtime verification modes.
- Create `src/ansim_review/rule_engine/golden.py`: deterministic execution of golden cases and generation of rule golden reports plus ignored actual outputs.
- Create `src/ansim_review/rule_engine/activation.py`: deterministic manifest construction, activation reports, and race-safe create-only publication.
- Create `src/ansim_review/rule_engine/selection.py`: exact scope matching and deterministic `SELECTED`, `ABSTAIN`, or `BLOCKED` results.
- Modify `src/ansim_review/rule_engine/manifest.py`: replace legacy tuple-only loading with governed v2 loading and explicit context.
- Modify `src/ansim_review/rule_engine/promotion.py`: remove direct active-manifest mutation and expose approved-copy creation only.
- Modify `src/ansim_review/contracts/formats.py`: register the five new format identifiers.
- Modify `src/ansim_review/cli.py`: add golden, activation, and selection commands; remove direct activation through promotion.

### Repository governance artifacts

- Replace `rules/manifests/active.json` with `evidence-review/active-rule-manifest` version 2.
- Create `rules/golden/fixtures/*.json`, `rules/golden/cases/**`, `rules/golden/expected/**`, and `rules/golden/reports/*.json` for the six existing ANSIM rules.
- Create `rules/activation/approvals/*.json` for the six existing ANSIM rules.
- Create `docs/acceptance/issue-48/README.md`, activation report, selection examples, and exact reproduction commands.

### Tests

- Create `tests/unit/rule_engine/test_governance_contract.py`.
- Create `tests/unit/rule_engine/test_governance_verify.py`.
- Create `tests/unit/rule_engine/test_golden.py`.
- Create `tests/unit/rule_engine/test_activation.py`.
- Create `tests/unit/rule_engine/test_selection.py`.
- Modify `tests/unit/rule_engine/test_promotion.py`.
- Create `tests/integration/rule_engine/test_governed_manifest.py`.
- Create `tests/integration/rule_engine/test_governance_cli.py`.
- Create `tests/integration/rule_engine/test_ansim_governance_acceptance.py`.
- Create `tests/unit/rule_engine/test_governance_documentation.py`.

---

### Task 1: Strict Governance Contracts

**Files:**
- Create: `src/ansim_review/rule_engine/governance_contract.py`
- Modify: `src/ansim_review/contracts/formats.py`
- Test: `tests/unit/rule_engine/test_governance_contract.py`

**Interfaces:**
- Produces `RuleScope`, `GoldenCaseRecord`, `RuleGoldenReport`, `RuleActivationApproval`, `ActiveRuleEntry`, `ActiveRuleManifest`, `ActivationFinding`, `ActivationReport`, `RuleSelectionContext`, `ExcludedRule`, `SelectedRule`, and `RuleSelectionResult`.
- Produces `load_rule_golden_report_bytes(data: bytes)`, `load_rule_activation_approval_bytes(data: bytes)`, `load_active_rule_manifest_bytes(data: bytes)`, and canonical `*_bytes(...)` serializers.
- Later tasks must not parse governance JSON directly with plain `json.loads`.

- [ ] **Step 1: Register exact format identifiers**

Add these constants to `src/ansim_review/contracts/formats.py` using the file's existing naming pattern:

```python
RULE_GOLDEN_REPORT_FORMAT = "evidence-review/rule-golden-report"
RULE_ACTIVATION_APPROVAL_FORMAT = "evidence-review/rule-activation-approval"
ACTIVE_RULE_MANIFEST_FORMAT = "evidence-review/active-rule-manifest"
RULE_ACTIVATION_REPORT_FORMAT = "evidence-review/rule-activation-report"
RULE_SELECTION_RESULT_FORMAT = "evidence-review/rule-selection-result"
```

- [ ] **Step 2: Write failing contract tests**

Cover exact keys, duplicate JSON keys, lowercase hash validation, timezone-aware timestamps, safe relative path syntax, scope key restrictions, unique case IDs, count consistency, duplicate active rule IDs, and canonical round trips.

```python
def test_active_manifest_rejects_legacy_shape() -> None:
    payload = b'{"rules":[]}'
    with pytest.raises(ValueError, match="legacy active rule manifest"):
        load_active_rule_manifest_bytes(payload)


def test_scope_requires_document_family() -> None:
    payload = valid_approval_payload()
    payload["scope"] = {"jurisdiction": "Seoul"}
    with pytest.raises(ValueError, match="document_family"):
        load_rule_activation_approval_bytes(canonical_bytes(payload))
```

- [ ] **Step 3: Run the RED tests**

Run:

```bash
pytest -v tests/unit/rule_engine/test_governance_contract.py
```

Expected: collection or import failure because `governance_contract.py` does not exist.

- [ ] **Step 4: Implement immutable contract types and strict parsing**

Use frozen, slotted dataclasses and reject duplicate JSON keys with an `object_pairs_hook`:

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

The active manifest decoder must require exact top-level values:

```python
if payload.get("format") != ACTIVE_RULE_MANIFEST_FORMAT:
    if set(payload) == {"rules"}:
        raise ValueError("legacy active rule manifest is not supported")
    raise ValueError("unsupported active rule manifest format")
if payload.get("version") != 2:
    raise ValueError("unsupported active rule manifest version")
```

- [ ] **Step 5: Run contract tests and static checks**

```bash
pytest -v tests/unit/rule_engine/test_governance_contract.py
ruff check src/ansim_review/rule_engine/governance_contract.py tests/unit/rule_engine/test_governance_contract.py
mypy src/ansim_review/rule_engine/governance_contract.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/contracts/formats.py src/ansim_review/rule_engine/governance_contract.py tests/unit/rule_engine/test_governance_contract.py
git commit -m "feat: define strict rule governance contracts"
```

---

### Task 2: Safe Artifact and Hash Verification

**Files:**
- Create: `src/ansim_review/rule_engine/governance_verify.py`
- Test: `tests/unit/rule_engine/test_governance_verify.py`

**Interfaces:**
- Consumes contract dataclasses from Task 1 and `load_rule` from `rule_engine.loader`.
- Produces `VerificationMode = Literal["ACTIVATION", "RUNTIME"]`.
- Produces `VerifiedApproval` containing the approval, loaded `RuleSpec`, normalized approval path, and all verified hashes.
- Produces `verify_approval(repository_root, approval_path, *, mode) -> VerifiedApproval`.
- Produces `verify_manifest_entry(repository_root, entry, *, mode="RUNTIME") -> VerifiedApproval`.

- [ ] **Step 1: Write failing safe-path and tamper tests**

Include traversal, absolute path, symlink escape, wrong candidate hash, wrong approved hash, wrong golden hash, identity mismatch, failing golden status, expected/actual mismatch during activation, and missing actual files tolerated only at runtime.

```python
def test_runtime_does_not_require_ignored_actual_output(tmp_path: Path) -> None:
    fixture = build_valid_governance_tree(tmp_path)
    fixture.actual_path.unlink()
    verified = verify_approval(tmp_path, fixture.approval_path, mode="RUNTIME")
    assert verified.rule.rule_id == "TEST-RULE"


def test_activation_requires_actual_output(tmp_path: Path) -> None:
    fixture = build_valid_governance_tree(tmp_path)
    fixture.actual_path.unlink()
    with pytest.raises(GovernanceVerificationError, match="GOLDEN_ACTUAL_MISSING"):
        verify_approval(tmp_path, fixture.approval_path, mode="ACTIVATION")
```

- [ ] **Step 2: Run the RED tests**

```bash
pytest -v tests/unit/rule_engine/test_governance_verify.py
```

Expected: import failure for `governance_verify`.

- [ ] **Step 3: Implement repository-contained path resolution**

```python
def resolve_governance_path(root: Path, relative: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    resolved_root = root.resolve(strict=True)
    resolved = candidate.resolve(strict=True)
    if resolved == resolved_root or resolved_root not in resolved.parents:
        raise GovernanceVerificationError("UNSAFE_ARTIFACT_PATH", relative)
    return resolved
```

Reject case-fold collisions by collecting normalized paths before opening files. Use `sha256_file` from `rule_engine.manifest` or move the helper without changing its behavior.

- [ ] **Step 4: Implement activation and runtime verification modes**

Activation mode verifies current bytes for candidate, approved rule, golden report, fixture manifest, every fixture, expected result, and generated actual result. Runtime mode verifies approval, candidate, approved rule, golden report, fixture manifest, fixtures, and expected files, but does not require `actual_path` to exist.

- [ ] **Step 5: Run tests and static checks**

```bash
pytest -v tests/unit/rule_engine/test_governance_verify.py
ruff check src/ansim_review/rule_engine/governance_verify.py tests/unit/rule_engine/test_governance_verify.py
mypy src/ansim_review/rule_engine/governance_verify.py
```

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/rule_engine/governance_verify.py tests/unit/rule_engine/test_governance_verify.py
git commit -m "feat: verify rule governance artifacts"
```

---

### Task 3: Deterministic Golden Runner

**Files:**
- Create: `src/ansim_review/rule_engine/golden.py`
- Test: `tests/unit/rule_engine/test_golden.py`

**Interfaces:**
- Consumes `evaluate_rule`, `load_rule`, canonical JSON helpers, and Task 1 contracts.
- Produces strict internal fixture manifest format `evidence-review/rule-golden-fixture` version 1.
- Produces `run_rule_golden(repository_root, fixture_manifest_path, actual_root, report_path, *, source_commit, command) -> RuleGoldenReport`.
- Actual output and report paths are create-only.

- [ ] **Step 1: Write failing runner tests**

Test one passing case, one expected mismatch, duplicate case IDs, missing evidence, invalid finalized calculation result, deterministic repeated bytes in different empty output roots, and create-only collisions.

```python
def test_golden_runner_writes_canonical_actual_and_pass_report(tmp_path: Path) -> None:
    paths = build_golden_fixture(tmp_path, expected_status="SATISFIED")
    report = run_rule_golden(
        tmp_path,
        paths.fixture_manifest,
        tmp_path / "build" / "actual",
        tmp_path / "build" / "report.json",
        source_commit="a" * 40,
        command="python -m ansim_review rules run-golden",
    )
    assert report.status == "PASS"
    assert report.failed_count == 0
```

- [ ] **Step 2: Run the RED tests**

```bash
pytest -v tests/unit/rule_engine/test_golden.py
```

- [ ] **Step 3: Implement exact fixture decoding and evaluation**

Each case input file contains exact keys:

```json
{
  "format": "evidence-review/rule-golden-case",
  "version": 1,
  "inputs": {},
  "calculations": [],
  "expected_formula_manifest_hash": null,
  "evidence_records": []
}
```

Serialize the complete `RuleResult` with its final `result_hash`; compare actual bytes with the committed expected bytes. The report status is `PASS` only if every expected hash equals its actual hash.

- [ ] **Step 4: Enforce deterministic create-only publication**

Write private files in the destination directory and publish with same-filesystem hard links so an existing or concurrently created output is never overwritten. Roll back only files published by the current invocation.

- [ ] **Step 5: Run runner tests and static checks**

```bash
pytest -v tests/unit/rule_engine/test_golden.py
ruff check src/ansim_review/rule_engine/golden.py tests/unit/rule_engine/test_golden.py
mypy src/ansim_review/rule_engine/golden.py
```

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/rule_engine/golden.py tests/unit/rule_engine/test_golden.py
git commit -m "feat: run deterministic rule golden cases"
```

---

### Task 4: Deterministic Scoped Activator

**Files:**
- Create: `src/ansim_review/rule_engine/activation.py`
- Test: `tests/unit/rule_engine/test_activation.py`

**Interfaces:**
- Consumes `verify_approval(..., mode="ACTIVATION")` and Task 1 serializers.
- Produces `build_active_manifest(repository_root, approval_paths, output_manifest, output_report) -> ActivationReport`.
- Success publishes manifest and report together. Validation failure publishes a blocked report only. Existing output returns `FileExistsError` before validation.

- [ ] **Step 1: Write failing activation tests**

Cover deterministic sorting, duplicate rule IDs across versions, duplicate approval paths, case-fold collision, one invalid approval blocking the entire set, empty approval list producing valid empty v2 manifest, report-only blocked publication, concurrent output creation, and no partial manifest.

```python
def test_one_invalid_approval_blocks_entire_activation(tmp_path: Path) -> None:
    valid, invalid = build_two_approvals(tmp_path)
    corrupt_file(invalid.golden_report_path)
    report = build_active_manifest(
        tmp_path,
        [valid.approval_path, invalid.approval_path],
        tmp_path / "out" / "active.json",
        tmp_path / "out" / "activation-report.json",
    )
    assert report.status == "BLOCKED"
    assert not (tmp_path / "out" / "active.json").exists()
```

- [ ] **Step 2: Run the RED tests**

```bash
pytest -v tests/unit/rule_engine/test_activation.py
```

- [ ] **Step 3: Implement all-or-nothing validation and canonical manifest creation**

Sort verified approvals by `(rule_id, semantic_version, approval_path)`. Reject more than one version of the same rule ID. Build each `ActiveRuleEntry` only from verified values, never by copying unchecked JSON mappings.

- [ ] **Step 4: Implement race-safe publication**

Use the golden runner's create-only publication pattern. On success, publish the manifest first and the report second, but if the second publication fails, remove only the manifest inode published by the current run. On validation failure, publish only the blocked report.

- [ ] **Step 5: Run activation tests and static checks**

```bash
pytest -v tests/unit/rule_engine/test_activation.py
ruff check src/ansim_review/rule_engine/activation.py tests/unit/rule_engine/test_activation.py
mypy src/ansim_review/rule_engine/activation.py
```

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/rule_engine/activation.py tests/unit/rule_engine/test_activation.py
git commit -m "feat: build scoped active rule manifests"
```

---

### Task 5: Runtime Authority Loading and Scope Selection

**Files:**
- Create: `src/ansim_review/rule_engine/selection.py`
- Modify: `src/ansim_review/rule_engine/manifest.py`
- Test: `tests/unit/rule_engine/test_selection.py`
- Test: `tests/integration/rule_engine/test_governed_manifest.py`

**Interfaces:**
- Produces `select_active_rules(entries, context, manifest_sha256) -> RuleSelectionResult`.
- Produces `GovernedRuleLoad(selection: RuleSelectionResult, rules: tuple[RuleSpec, ...])`.
- Replaces legacy `load_active_rules(project_root, manifest_path)` with `load_governed_active_rules(project_root, manifest_path, context) -> GovernedRuleLoad`.
- No API may return rules when selection status is `ABSTAIN` or `BLOCKED`.

- [ ] **Step 1: Write failing selector tests**

Cover exact case-sensitive matching, missing `document_family`, optional dimension mismatch, unsupported context key, multiple selected rules, deterministic exclusion order, empty manifest abstention, legacy manifest blocking, and tampered entry blocking all rules.

```python
def test_valid_empty_manifest_abstains() -> None:
    result = select_active_rules((), RuleSelectionContext(document_family="ANSIM"), "a" * 64)
    assert result.status == "ABSTAIN"
    assert result.reasons == ("NO_APPLICABLE_ACTIVE_RULE",)


def test_scope_is_case_sensitive() -> None:
    result = select_active_rules(
        (entry(scope=RuleScope(document_family="ANSIM")),),
        RuleSelectionContext(document_family="ansim"),
        "a" * 64,
    )
    assert result.status == "ABSTAIN"
    assert result.excluded_rules[0].reason == "SCOPE_MISMATCH"
```

- [ ] **Step 2: Run the RED tests**

```bash
pytest -v tests/unit/rule_engine/test_selection.py tests/integration/rule_engine/test_governed_manifest.py
```

- [ ] **Step 3: Implement pure deterministic selection**

The selector performs no file I/O. It evaluates all verified entries and returns selected and excluded evidence sorted by rule ID and version.

- [ ] **Step 4: Replace the legacy manifest loader**

`load_governed_active_rules` must:

1. Read manifest bytes and calculate `manifest_sha256`.
2. Strictly decode exact v2.
3. Runtime-verify every entry before scope selection.
4. Return `BLOCKED` with no rules if any entry fails.
5. Return `ABSTAIN` with no rules when no scope matches.
6. Load only the approved rule files named in selected verified entries.

Delete or fail closed the old no-context loader so callers cannot bypass scope selection.

- [ ] **Step 5: Run selection, manifest, evaluator, and source-gate regressions**

```bash
pytest -v tests/unit/rule_engine/test_selection.py tests/integration/rule_engine/test_governed_manifest.py tests/integration/rule_engine/test_rule_source_gate.py
ruff check src/ansim_review/rule_engine/selection.py src/ansim_review/rule_engine/manifest.py
mypy src/ansim_review/rule_engine/selection.py src/ansim_review/rule_engine/manifest.py
```

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/rule_engine/selection.py src/ansim_review/rule_engine/manifest.py tests/unit/rule_engine/test_selection.py tests/integration/rule_engine/test_governed_manifest.py
git commit -m "feat: select active rules by explicit scope"
```

---

### Task 6: Disable Direct Activation and Add CLI Commands

**Files:**
- Modify: `src/ansim_review/rule_engine/promotion.py`
- Modify: `src/ansim_review/cli.py`
- Modify: `tests/unit/rule_engine/test_promotion.py`
- Create: `tests/integration/rule_engine/test_governance_cli.py`

**Interfaces:**
- Produces `approve_candidate(candidate_path, approved_dir, *, reviewer_id, review_date) -> Path`, which creates only an immutable approved rule copy.
- Existing `promote_candidate(...)` raises a clear error directing callers to `approve_candidate` plus `rules build-active-manifest`.
- Adds commands:
  - `evidence-review rules run-golden`
  - `evidence-review rules build-active-manifest`
  - `evidence-review rules select`

- [ ] **Step 1: Write failing promotion and CLI tests**

```python
def test_legacy_promotion_cannot_update_active_manifest(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="direct active promotion is disabled"):
        promote_candidate(
            candidate_path(tmp_path),
            tmp_path / "rules" / "approved",
            tmp_path / "rules" / "manifests" / "active.json",
            reviewer_id="reviewer",
            review_date="2026-08-02",
        )
```

CLI exit codes:

- `0`: golden PASS, activation ACTIVE, selection SELECTED or ABSTAIN.
- `1`: create-only output collision.
- `2`: invalid input, golden FAIL, activation BLOCKED, or selection BLOCKED.

- [ ] **Step 2: Run the RED tests**

```bash
pytest -v tests/unit/rule_engine/test_promotion.py tests/integration/rule_engine/test_governance_cli.py
```

- [ ] **Step 3: Split approval copy from activation**

Keep approved rule payload compatibility, including embedded historical approval metadata, but do not write or modify `rules/manifests/active.json` from `promotion.py`.

- [ ] **Step 4: Add CLI parsers and canonical stdout**

Example selection invocation:

```powershell
evidence-review rules select `
  --repository-root . `
  --manifest rules/manifests/active.json `
  --document-family ANSIM `
  --output build/rules/selection.json
```

Every command writes one canonical status JSON to stdout. `rules select` may write an optional create-only result file.

- [ ] **Step 5: Run CLI and help tests**

```bash
pytest -v tests/unit/rule_engine/test_promotion.py tests/integration/rule_engine/test_governance_cli.py
python -m ansim_review rules --help
python -m ansim_review rules run-golden --help
python -m ansim_review rules build-active-manifest --help
python -m ansim_review rules select --help
```

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/rule_engine/promotion.py src/ansim_review/cli.py tests/unit/rule_engine/test_promotion.py tests/integration/rule_engine/test_governance_cli.py
git commit -m "feat: expose governed rule activation CLI"
```

---

### Task 7: Migrate the Six Existing ANSIM Rules

**Files:**
- Create: `rules/golden/fixtures/ANSIM-ARTERIAL-FRONTAGE-ONE-EIGHTH@1.0.0.json`
- Create: `rules/golden/fixtures/ANSIM-MINIMUM-SITE-AREA-1500@1.0.0.json`
- Create: `rules/golden/fixtures/ANSIM-TWO-ROAD-SIDES-6M@1.0.0.json`
- Create: `rules/golden/fixtures/ANSIM-ZONING-CHANGE-FAR-MAX-400@1.0.0.json`
- Create: `rules/golden/fixtures/ANSIM-ZONING-CHANGE-PUBLIC-CONTRIBUTION-MIN-15@1.0.0.json`
- Create: `rules/golden/fixtures/ANSIM-ZONING-CHANGE-RESIDENTIAL-RATIO-MIN-85@1.0.0.json`
- Create: case and expected files below `rules/golden/cases/<rule-id>/` and `rules/golden/expected/<rule-id>/`.
- Create: six reports below `rules/golden/reports/`.
- Create: six approvals below `rules/activation/approvals/`.
- Modify: `rules/manifests/active.json`.
- Test: `tests/integration/rule_engine/test_ansim_governance_acceptance.py`

**Interfaces:**
- Each rule gets at least one satisfied and one not-satisfied golden case.
- The calculation-backed frontage rule additionally gets an invalid-calculation case whose expected result is `ENGINE_ERROR / INVALID_CALCULATION_REFERENCE`.
- Every approval uses exact scope `{ "document_family": "ANSIM" }` and a timezone-aware reviewed timestamp.

- [ ] **Step 1: Write the failing repository acceptance test**

The test enumerates these exact rule IDs and asserts that each has one fixture manifest, one passing golden report, one approval, one active v2 entry, correct current hashes, and at least two cases.

```python
EXPECTED_RULE_IDS = {
    "ANSIM-ARTERIAL-FRONTAGE-ONE-EIGHTH",
    "ANSIM-MINIMUM-SITE-AREA-1500",
    "ANSIM-TWO-ROAD-SIDES-6M",
    "ANSIM-ZONING-CHANGE-FAR-MAX-400",
    "ANSIM-ZONING-CHANGE-PUBLIC-CONTRIBUTION-MIN-15",
    "ANSIM-ZONING-CHANGE-RESIDENTIAL-RATIO-MIN-85",
}
```

- [ ] **Step 2: Run the RED acceptance test**

```bash
pytest -v tests/integration/rule_engine/test_ansim_governance_acceptance.py
```

Expected: missing golden and approval artifacts.

- [ ] **Step 3: Create canonical case and expected files**

Use real current approved rule identities and source citations. Do not alter the legal content of the six rules. Expected files must contain the full canonical finalized `RuleResult`, including `result_hash`.

- [ ] **Step 4: Run golden cases into an empty build directory**

For each fixture manifest:

```powershell
python -m ansim_review rules run-golden `
  --repository-root . `
  --fixture-manifest rules/golden/fixtures/<exact-file-name>.json `
  --actual-root build/rules/golden/actual `
  --report build/rules/golden/reports/<exact-file-name>.json `
  --source-commit cb4d387b17ae4232bee175866d3e2eed86016321 `
  --command "python -m ansim_review rules run-golden"
```

Copy only verified PASS report JSON into `rules/golden/reports/`; do not commit `build/rules/golden/actual`.

- [ ] **Step 5: Create six human approval artifacts**

Each approval binds the candidate, approved rule, committed PASS report, explicit ANSIM scope, reviewer ID, timezone-aware reviewed timestamp, decision `APPROVED`, and a non-empty reason. Recompute all hashes from current bytes; never copy stale hashes from the legacy manifest.

- [ ] **Step 6: Build a candidate active manifest and compare bytes**

```powershell
python -m ansim_review rules build-active-manifest `
  --repository-root . `
  --approvals rules/activation/approvals `
  --output build/rules/active.json `
  --report build/rules/activation-report.json
```

Require status `ACTIVE`, six entries, and deterministic identical bytes across a second run into a different empty directory. Replace checked-in `rules/manifests/active.json` with the verified generated bytes.

- [ ] **Step 7: Run acceptance and ANSIM behavior tests**

```bash
pytest -v tests/integration/rule_engine/test_ansim_governance_acceptance.py tests/integration/rule_engine
```

- [ ] **Step 8: Commit**

```bash
git add rules/golden rules/activation rules/manifests/active.json tests/integration/rule_engine/test_ansim_governance_acceptance.py
git commit -m "feat: govern active ansim rules with golden evidence"
```

---

### Task 8: End-to-End Fail-Closed and Tamper Matrix

**Files:**
- Create: `tests/integration/rule_engine/test_governance_tamper_matrix.py`
- Modify: `tests/integration/rule_engine/test_governed_manifest.py`
- Modify: `tests/integration/rule_engine/test_governance_cli.py`

**Interfaces:**
- Tests the public CLI and `load_governed_active_rules` rather than private helpers.
- Requires no network, Git credentials, or mutable external state.

- [ ] **Step 1: Add parameterized tamper cases**

Include mutations for active manifest, approval, golden report, candidate, approved rule, fixture manifest, fixture, expected file, path traversal, symlink escape, duplicate rule ID, and case-fold collision. Every mutation must yield `BLOCKED` and zero loaded rules.

```python
@pytest.mark.parametrize(
    "mutation, expected_reason",
    [
        ("approved_rule_bytes", "ACTIVE_RULE_HASH_MISMATCH"),
        ("approval_bytes", "APPROVAL_HASH_MISMATCH"),
        ("golden_report_bytes", "GOLDEN_REPORT_HASH_MISMATCH"),
        ("candidate_bytes", "CANDIDATE_HASH_MISMATCH"),
        ("expected_bytes", "GOLDEN_EXPECTED_HASH_MISMATCH"),
    ],
)
def test_tamper_blocks_all_rules(mutation: str, expected_reason: str, tmp_path: Path) -> None:
    ...
```

Replace the ellipsis during implementation with the shared fixture builder invocation and exact mutation dispatch; do not commit placeholder code.

- [ ] **Step 2: Add normal abstention cases**

Demonstrate that these are not blocking errors:

- valid empty v2 manifest;
- context without `document_family`;
- `document_family=OTHER` against ANSIM entries;
- mismatch in optional `program` or `jurisdiction`.

All return exit code `0`, status `ABSTAIN`, reason `NO_APPLICABLE_ACTIVE_RULE`, and deterministic exclusion records.

- [ ] **Step 3: Add no-bypass regressions**

Assert that:

- files under `rules/candidates` are never scanned by runtime selection;
- unmanifested approved rules are never loaded;
- legacy `promote_candidate` cannot modify active manifest;
- a single valid entry is not executed when another manifest entry is corrupted.

- [ ] **Step 4: Run focused and complete rule-engine tests**

```bash
pytest -v tests/unit/rule_engine tests/integration/rule_engine
```

- [ ] **Step 5: Commit**

```bash
git add tests/integration/rule_engine/test_governance_tamper_matrix.py tests/integration/rule_engine/test_governed_manifest.py tests/integration/rule_engine/test_governance_cli.py
git commit -m "test: enforce fail-closed rule governance"
```

---

### Task 9: Documentation and Issue #48 Acceptance Evidence

**Files:**
- Create: `docs/RULE_ACTIVATION_GOVERNANCE.md`
- Create: `docs/acceptance/issue-48/README.md`
- Create: `docs/acceptance/issue-48/activation-report.json`
- Create: `docs/acceptance/issue-48/ansim-selection.json`
- Create: `docs/acceptance/issue-48/non-ansim-abstention.json`
- Modify: `README.md`
- Test: `tests/unit/rule_engine/test_governance_documentation.py`

**Interfaces:**
- Documentation distinguishes human approval record, deterministic activation, runtime selection, and final human review.
- Acceptance README records exact source commit, commands, manifest hash, approval hashes, golden report hashes, CI run, and reviewer limitations.

- [ ] **Step 1: Write failing documentation tests**

Assert that every documented command maps to a real CLI parser, every acceptance JSON decodes with strict contracts, all referenced paths exist, and README explicitly states that reviewer identity is not cryptographically verified.

- [ ] **Step 2: Run the RED documentation test**

```bash
pytest -v tests/unit/rule_engine/test_governance_documentation.py
```

- [ ] **Step 3: Write operational documentation**

Document this exact workflow:

1. author candidate;
2. create immutable approved copy;
3. create case and expected evidence;
4. run golden cases;
5. review and create approval artifact;
6. build create-only active manifest candidate;
7. review generated manifest/report;
8. replace checked-in derived manifest in the PR;
9. run scoped selection;
10. treat `ABSTAIN` separately from `BLOCKED`.

- [ ] **Step 4: Preserve acceptance outputs**

Generate acceptance files from the repository's real v2 artifacts. `ansim-selection.json` must be `SELECTED` with six rules. `non-ansim-abstention.json` must be `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE`. Do not hand-edit generated hashes.

- [ ] **Step 5: Run documentation tests**

```bash
pytest -v tests/unit/rule_engine/test_governance_documentation.py
```

- [ ] **Step 6: Commit**

```bash
git add docs/RULE_ACTIVATION_GOVERNANCE.md docs/acceptance/issue-48 README.md tests/unit/rule_engine/test_governance_documentation.py
git commit -m "docs: record governed rule activation acceptance"
```

---

### Task 10: Full Verification, Self-Review, and PR Readiness

**Files:**
- Review all files changed since `cb2fbf0a009ebd335393e8c0100755e029e3657a`.
- Update the Issue #48 and parent Issue #27 comments with final evidence.

**Interfaces:**
- No new production interface is introduced in this task.
- The exact PR head SHA and Actions run ID become the final acceptance reference.

- [ ] **Step 1: Run the full local validation matrix**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
python -m build --wheel
```

Expected: all pass with no skipped governance acceptance tests.

- [ ] **Step 2: Verify installed-wheel behavior**

Create isolated Python 3.11 and 3.13 environments, install the built wheel, and run:

```bash
evidence-review --help
evidence-review rules --help
evidence-review rules select --repository-root . --manifest rules/manifests/active.json --document-family OTHER
```

Expected: help succeeds and the selection command prints canonical `ABSTAIN / NO_APPLICABLE_ACTIVE_RULE` without importing from the source checkout.

- [ ] **Step 3: Reproduce governed ANSIM activation from empty build directories**

Run all six golden manifests, build the active manifest candidate twice in separate empty directories, and compare:

```bash
python -c "from pathlib import Path; assert Path('build/a/active.json').read_bytes() == Path('build/b/active.json').read_bytes()"
```

Also assert the generated bytes equal checked-in `rules/manifests/active.json`.

- [ ] **Step 4: Perform implementation self-review**

Check specifically:

- no plain `json.loads` bypass for governance artifacts;
- no direct active manifest write from `promotion.py`;
- no runtime scan of candidates or approved directories;
- all path resolution is root-contained and symlink-safe;
- blocked activation cannot leave a manifest;
- blocked runtime selection cannot return partial rules;
- runtime does not require ignored actual outputs;
- reviewer identity limitations are documented;
- all six ANSIM entries have current hash-bound evidence.

- [ ] **Step 5: Push and verify GitHub Actions**

Require success for:

- full pytest;
- Ruff;
- strict mypy;
- compileall;
- Python 3.11 wheel install and entrypoints;
- Python 3.13 wheel install and resources;
- Ubuntu workspace validator;
- Windows workspace validator.

- [ ] **Step 6: Update GitHub records**

Post to Issue #48:

- PR URL;
- exact HEAD SHA;
- Actions run ID;
- test counts;
- active manifest SHA-256;
- six approved rule IDs;
- ANSIM `SELECTED` result;
- non-ANSIM `ABSTAIN` result;
- acceptance artifact path;
- statement that final human legal judgment remains outside the rule activation process.

Post a concise progress update to parent Issue #27 and leave Issue #48 open until the PR is merged and acceptance artifacts are present on `main`.

- [ ] **Step 7: Final commit for any review-only corrections**

If self-review changes are required, commit them separately:

```bash
git add -A
git commit -m "fix: close rule governance review gaps"
```

Do not create an empty commit when no corrections are needed.
