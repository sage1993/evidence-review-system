# Grist Desktop QA Artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict, hash-bound, fail-closed acceptance artifact and CLI validator for manual legacy Grist Desktop UI QA.

**Architecture:** A focused `legacy_grist_qa` module decodes the versioned JSON contract, derives PASS/FAIL/INCOMPLETE, and verifies all referenced workspace files and the Issue #37 inspection report. The existing `legacy` CLI namespace exposes validation without automating Grist Desktop or promoting legacy identity.

**Tech Stack:** Python 3.11+, dataclasses, standard-library JSON/hashlib/pathlib, existing canonical JSON and contract validation helpers, argparse, pytest.

## Global Constraints

- Scope is exactly `LEGACY_UI_QA`.
- Identity claim is exactly `LEGACY_NON_CANONICAL`.
- No canonical visual records are created or modified.
- No filename, path, prefix, row-order, or single-revision identity inference.
- Actual Grist Desktop UI observation remains manual.
- Every referenced file path is workspace-relative POSIX and contained below `--root`.
- All stored and calculated SHA-256 values are lowercase hexadecimal.
- Unknown JSON fields are rejected.
- Valid but incomplete/failed QA is distinct from invalid artifact syntax or tampering.

---

### Task 1: Lock the strict artifact contract with RED tests

**Files:**
- Create: `tests/unit/parsing/test_legacy_grist_qa.py`
- Create: `tests/golden/legacy_grist_qa/pass.json`
- Create: `src/ansim_review/parsing/legacy_grist_qa.py`

**Interfaces:**
- Produces: `decode_grist_qa(value: object) -> GristQaArtifact`
- Produces: `grist_qa_document(artifact: GristQaArtifact) -> dict[str, object]`
- Produces constants: `GRIST_QA_FORMAT`, `GRIST_QA_STATUS_FORMAT`, `REQUIRED_VIEW_IDS`, `REQUIRED_SAMPLE_KINDS`.

- [ ] **Step 1: Write failing strict decoder tests**

Cover exact format/version/scope/identity claim, timezone-bearing review timestamp, required environment fields, exact source bindings, evidence IDs, views, samples, and findings. Assert unknown fields and missing fields fail.

- [ ] **Step 2: Write failing duplicate and reference tests**

Assert duplicate evidence IDs, sample IDs, finding IDs, or view IDs fail. Assert unknown evidence references and unknown view references fail.

- [ ] **Step 3: Write failing view/finding consistency tests**

Assert every required view exists exactly once and every FAIL view has at least one OPEN finding tied to that view. Assert each finding has row ID or file path.

- [ ] **Step 4: Run RED**

```bash
pytest -q tests/unit/parsing/test_legacy_grist_qa.py
```

Expected: import failure because `legacy_grist_qa` does not exist.

- [ ] **Step 5: Implement minimal dataclasses and decoder**

Use existing helpers from `ansim_review.contracts.validation`. Parse timestamps with `datetime.fromisoformat`, reject timezone-less values, sort canonical collections by fixed required order or stable ID, and preserve nullable row/file fields explicitly.

- [ ] **Step 6: Implement canonical document projection**

Return deterministic field order and required view order. Preserve evidence/sample/finding order by sorted stable IDs.

- [ ] **Step 7: Run focused GREEN**

```bash
pytest -q tests/unit/parsing/test_legacy_grist_qa.py
ruff check src/ansim_review/parsing/legacy_grist_qa.py tests/unit/parsing/test_legacy_grist_qa.py
mypy src/ansim_review/parsing/legacy_grist_qa.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ansim_review/parsing/legacy_grist_qa.py tests/unit/parsing/test_legacy_grist_qa.py tests/golden/legacy_grist_qa/pass.json
git commit -m "feat: define legacy Grist QA artifact contract"
```

### Task 2: Derive fail-closed QA status

**Files:**
- Modify: `src/ansim_review/parsing/legacy_grist_qa.py`
- Test: `tests/unit/parsing/test_legacy_grist_qa.py`

**Interfaces:**
- Produces: `derive_grist_qa_status(artifact: GristQaArtifact) -> Literal["PASS", "FAIL", "INCOMPLETE"]`
- Produces: `grist_qa_status_document(artifact: GristQaArtifact, artifact_sha256: str) -> dict[str, object]`.

- [ ] **Step 1: Write failing status tests**

Test these exact cases:

- all nine views PASS, four required sample kinds have PASS samples, no OPEN findings -> PASS
- any view FAIL -> FAIL
- any sample FAIL -> FAIL
- any OPEN finding -> FAIL
- no failures but one NOT_RUN view -> INCOMPLETE
- no failures but one required sample kind lacks a PASS sample -> INCOMPLETE

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/unit/parsing/test_legacy_grist_qa.py -k status
```

Expected: missing status function failures.

- [ ] **Step 3: Implement status derivation**

Use precedence FAIL, then INCOMPLETE, then PASS. Do not trust any input overall status field because the contract does not contain one.

- [ ] **Step 4: Implement deterministic status document**

Include format/version/status/accepted/artifact SHA/reviewer/timestamp, exact view counts, and open finding count.

- [ ] **Step 5: Run GREEN and deterministic bytes test**

```bash
pytest -q tests/unit/parsing/test_legacy_grist_qa.py
```

Expected: PASS and repeated `dump_bytes` output equality.

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/parsing/legacy_grist_qa.py tests/unit/parsing/test_legacy_grist_qa.py
git commit -m "feat: derive fail-closed Grist QA status"
```

### Task 3: Bind artifact to real files and legacy inspection report

**Files:**
- Modify: `src/ansim_review/parsing/legacy_grist_qa.py`
- Create: `tests/unit/parsing/test_legacy_grist_qa_files.py`

**Interfaces:**
- Produces: `validate_grist_qa_files(artifact: GristQaArtifact, root: Path) -> None`
- Produces: `load_and_validate_grist_qa(path: Path, root: Path) -> tuple[GristQaArtifact, str]` where the string is the artifact file SHA-256.

- [ ] **Step 1: Write failing safe-path tests**

Reject absolute, drive-letter, parent traversal, empty, trailing slash, and backslash paths for sources, evidence files, sample assets, and finding file paths.

- [ ] **Step 2: Write failing file/hash tests**

Create temporary `.grist`, CSV, inspection report, screenshot, and sample asset files. Assert missing files and any SHA mismatch fail with stable error codes.

- [ ] **Step 3: Write failing inspection binding tests**

Reject wrong inspection format/version/status, `conversion_supported: true`, and source SHA mismatch against the bound CSV.

- [ ] **Step 4: Run RED**

```bash
pytest -q tests/unit/parsing/test_legacy_grist_qa_files.py
```

Expected: missing file validation functions.

- [ ] **Step 5: Implement path containment and hash verification**

Resolve every path below `root`, reject symlinks that resolve outside root, require the Grist source path suffix `.grist`, and compare lowercase SHA-256 using the existing `sha256_file` helper.

- [ ] **Step 6: Implement inspection report semantic binding**

Read JSON and enforce the Issue #37 boundary exactly. Do not accept a clean screen result as canonical identity evidence.

- [ ] **Step 7: Implement artifact loader**

Read bytes once, calculate artifact SHA-256, decode UTF-8 JSON, validate files, and return artifact plus hash.

- [ ] **Step 8: Run focused GREEN**

```bash
pytest -q tests/unit/parsing/test_legacy_grist_qa.py tests/unit/parsing/test_legacy_grist_qa_files.py
ruff check src/ansim_review/parsing/legacy_grist_qa.py tests/unit/parsing/test_legacy_grist_qa*.py
mypy src/ansim_review/parsing/legacy_grist_qa.py
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/ansim_review/parsing/legacy_grist_qa.py tests/unit/parsing/test_legacy_grist_qa_files.py
git commit -m "feat: bind Grist QA evidence to workspace files"
```

### Task 4: Expose CLI validation

**Files:**
- Modify: `src/ansim_review/cli.py`
- Create: `tests/integration/parsing/test_legacy_grist_qa_cli.py`

**Interfaces:**
- Adds: `evidence-review legacy validate-grist-qa --artifact PATH --root PATH`.

- [ ] **Step 1: Write failing CLI tests**

Test help, PASS exit 0, FAIL exit 1, INCOMPLETE exit 1, malformed/tampered artifact exit 2, and deterministic canonical stdout.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/integration/parsing/test_legacy_grist_qa_cli.py
```

Expected: argparse rejects `validate-grist-qa`.

- [ ] **Step 3: Add parser and dispatcher**

Add required `--artifact` and `--root` arguments below the existing `legacy` namespace.

- [ ] **Step 4: Add `_legacy_grist_qa_validate`**

Call `load_and_validate_grist_qa`, build the status document, write it to stdout with `dump_bytes`, return 0 for PASS, 1 for valid FAIL/INCOMPLETE, and 2 for file/JSON/contract errors.

- [ ] **Step 5: Run CLI GREEN**

```bash
pytest -q tests/integration/parsing/test_legacy_grist_qa_cli.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/cli.py tests/integration/parsing/test_legacy_grist_qa_cli.py
git commit -m "feat: validate Grist Desktop QA artifacts from CLI"
```

### Task 5: Document the Windows manual QA procedure

**Files:**
- Create: `docs/GRIST_DESKTOP_QA.md`
- Create: `docs/examples/grist-desktop-qa.example.json`
- Create: `tests/unit/parsing/test_legacy_grist_qa_documentation.py`
- Modify: `docs/LEGACY_VISUALS.md`

**Interfaces:**
- Documents exact artifact fields, required screens, evidence capture, validator command, exit codes, and closure boundary.

- [ ] **Step 1: Write RED documentation test**

Require docs to contain all nine required view IDs, all four sample kinds, `LEGACY_UI_QA`, `LEGACY_NON_CANONICAL`, `PASS`, `FAIL`, `INCOMPLETE`, the CLI command, and an explicit statement that CI cannot perform actual Grist Desktop screen review.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/unit/parsing/test_legacy_grist_qa_documentation.py
```

Expected: dedicated procedure document missing.

- [ ] **Step 3: Write the manual procedure**

Provide Windows steps: run visual inspection preflight, calculate/capture hashes, open exact `.grist`, record Grist Desktop version/OS, inspect Attachments/Visuals/Reference and four content kinds, record findings, save screenshots if useful, run validator, and retain stdout plus artifact.

- [ ] **Step 4: Add a structurally complete example**

Use safe relative paths and syntactically valid lowercase example hashes. Mark view statuses `NOT_RUN` so the example is not mistaken for completed acceptance evidence.

- [ ] **Step 5: Link from legacy policy**

Clarify that Issue #38 closure requires an actual Windows artifact whose validator result is PASS.

- [ ] **Step 6: Run documentation GREEN**

```bash
pytest -q tests/unit/parsing/test_legacy_grist_qa_documentation.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add docs/GRIST_DESKTOP_QA.md docs/examples/grist-desktop-qa.example.json docs/LEGACY_VISUALS.md tests/unit/parsing/test_legacy_grist_qa_documentation.py
git commit -m "docs: define Grist Desktop QA evidence procedure"
```

### Task 6: Full verification and PR

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run full verification**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
python -m build --wheel
```

Expected: all commands exit 0.

- [ ] **Step 2: Confirm scope**

Compare against `main` and verify no Grist UI automation, canonical conversion, evidence DB mutation, or legacy asset relocation was introduced.

- [ ] **Step 3: Open draft PR**

Use title `feat: add Grist Desktop QA acceptance artifact` and include RED/GREEN run IDs. Use `Refs #38`, not `Closes #38`, because manual Windows UI execution remains outstanding.

- [ ] **Step 4: Record issue handoff**

Comment on Issue #38 with the PR, validator command, and exact remaining manual steps. Keep Issue #38 open until a real PASS artifact is submitted.
