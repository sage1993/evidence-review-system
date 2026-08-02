# Legacy Visual Identity Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed, read-only inspector that classifies the legacy Grist visual CSV as non-canonical without inventing document, revision, or page identity.

**Architecture:** A focused parser module reads the exact legacy CSV schema and returns a deterministic inspection document. A CLI command writes the report create-only. Canonical visual loading remains unchanged and no converter is emitted.

**Tech Stack:** Python 3.11+, standard-library `csv`, `hashlib`, `pathlib`, argparse, pytest, canonical JSON writer.

## Global Constraints

- Legacy visual CSV status is exactly `LEGACY_NON_CANONICAL`.
- `conversion_supported` is exactly `false`.
- No filename, folder, prefix, single-revision, or page-order inference.
- The inspector never creates `VisualRecord` or canonical visual manifest JSON.
- Output files are create-only.
- Runtime dependencies remain standard-library only.

---

### Task 1: Lock the read-only contract with RED tests

**Files:**
- Create: `tests/unit/parsing/test_legacy_visual_manifest.py`
- Create: `tests/golden/legacy_visual/inspection.json`
- Modify: `tests/unit/contracts/test_generic_artifact_namespace.py`

**Interfaces:**
- Consumes: future `inspect_legacy_visual_manifest(manifest_path: Path, root: Path | None = None) -> dict[str, object]`
- Produces: exact report schema and legacy-boundary expectations.

- [ ] **Step 1: Write failing tests for a valid BOM CSV**

Create a temporary CSV with the exact 17-column legacy header and one row. Assert report format/version/status, row count, document IDs, identity gaps, `conversion_supported is False`, sorted conversion requirements, and no canonical `records` field.

- [ ] **Step 2: Write failing tests for deterministic bytes**

Call the inspector twice, serialize with `dump_bytes`, and assert byte equality with the golden fixture.

- [ ] **Step 3: Write failing tests for duplicate IDs and invalid fields**

Assert exact issue codes:

```text
DUPLICATE_VISUAL_ID
DOCUMENT_ID_MISSING
PAGE_INVALID
SOURCE_PATH_INVALID
CROP_PATH_INVALID
SHA256_INVALID
```

- [ ] **Step 4: Write failing tests for asset verification**

With `root` provided, assert `ASSET_MISSING` and `ASSET_HASH_MISMATCH` use the selected `crop_path` only as a checked legacy field, not as identity authority.

- [ ] **Step 5: Extend generic artifact namespace test**

Require `LEGACY_VISUAL_MANIFEST_CSV` and `LEGACY_VISUAL_STATUS` in `contracts/legacy_formats.py`, and add the new inspector to the explicit legacy reader allowlist.

- [ ] **Step 6: Run RED**

Run:

```bash
pytest -q tests/unit/parsing/test_legacy_visual_manifest.py tests/unit/contracts/test_generic_artifact_namespace.py
```

Expected: import/constant failures because the inspector and legacy constants do not exist.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/parsing/test_legacy_visual_manifest.py tests/golden/legacy_visual/inspection.json tests/unit/contracts/test_generic_artifact_namespace.py
git commit -m "test: define legacy visual inspection contract"
```

### Task 2: Implement the legacy inspector

**Files:**
- Create: `src/ansim_review/parsing/legacy_visual_manifest.py`
- Modify: `src/ansim_review/contracts/legacy_formats.py`
- Test: `tests/unit/parsing/test_legacy_visual_manifest.py`

**Interfaces:**
- Produces: `inspect_legacy_visual_manifest(manifest_path: Path, root: Path | None = None) -> dict[str, object]`
- Produces constants: `LEGACY_VISUAL_MANIFEST_CSV = "04_visuals/manifests/visual_manifest.csv"`, `LEGACY_VISUAL_STATUS = "LEGACY_NON_CANONICAL"`.

- [ ] **Step 1: Add legacy constants**

Document that new writers must not emit the CSV and that the status is inspection-only.

- [ ] **Step 2: Implement exact header decoding**

Use `csv.DictReader` with `encoding="utf-8-sig"`. Require exactly:

```python
(
    "visual_id", "document_id", "clause_row_id", "clause_id", "page",
    "visual_type", "source_key", "related_table_row_id", "source_path",
    "crop_path", "bbox_left", "bbox_bottom", "bbox_right", "bbox_top",
    "pixel_width", "pixel_height", "sha256",
)
```

Raise `ValueError("LEGACY_VISUAL_HEADER_INVALID")` on mismatch.

- [ ] **Step 3: Implement row inspection**

Preserve original strings. Generate deterministic issues with `row_number` starting at 2. Validate positive integer page, safe POSIX paths, lowercase SHA-256, required document ID, and duplicate visual ID.

- [ ] **Step 4: Implement optional asset checks**

Resolve `crop_path` below `root`, reject escapes, report missing file or SHA mismatch, and never derive identity from the path.

- [ ] **Step 5: Build deterministic report**

Return sorted document IDs, issue counts, issues, exact conversion requirements, source SHA-256, and no canonical record list.

- [ ] **Step 6: Run focused tests**

```bash
pytest -q tests/unit/parsing/test_legacy_visual_manifest.py tests/unit/contracts/test_generic_artifact_namespace.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ansim_review/parsing/legacy_visual_manifest.py src/ansim_review/contracts/legacy_formats.py tests
git commit -m "feat: inspect legacy visual manifests read-only"
```

### Task 3: Add CLI and integration tests

**Files:**
- Modify: `src/ansim_review/cli.py`
- Create: `tests/integration/parsing/test_legacy_visual_manifest_cli.py`

**Interfaces:**
- Adds: `evidence-review legacy inspect-visual-manifest --manifest PATH [--root PATH] --output PATH`

- [ ] **Step 1: Write RED CLI tests**

Test help text, successful create-only output, existing output exit 1, malformed CSV exit 2, and stdout status document containing output path and `LEGACY_NON_CANONICAL`.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/integration/parsing/test_legacy_visual_manifest_cli.py
```

Expected: argparse rejects the `legacy` command.

- [ ] **Step 3: Add parser and dispatcher**

Add `legacy` / `inspect-visual-manifest` subparsers and `_legacy_visual_inspect`. Write report with `dump_bytes` through `xb`; do not overwrite.

- [ ] **Step 4: Run CLI tests**

```bash
pytest -q tests/integration/parsing/test_legacy_visual_manifest_cli.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ansim_review/cli.py tests/integration/parsing/test_legacy_visual_manifest_cli.py
git commit -m "feat: expose legacy visual inspection CLI"
```

### Task 4: Document compatibility and removal policy

**Files:**
- Create: `docs/LEGACY_VISUALS.md`
- Modify: `README.md`
- Create: `tests/unit/parsing/test_legacy_visual_documentation.py`

**Interfaces:**
- Documents exact policy tokens and the operational command.

- [ ] **Step 1: Write RED documentation test**

Require the combined docs to contain:

```text
LEGACY_NON_CANONICAL
conversion_supported
false
revision_id
page_id
파일명
추론하지
legacy reader 제거
```

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/unit/parsing/test_legacy_visual_documentation.py
```

Expected: FAIL because the dedicated policy document does not exist.

- [ ] **Step 3: Write docs**

Explain inspection versus conversion, no-inference rules, command usage, conversion prerequisites, and removal gates tied to Issue #38 acceptance evidence.

- [ ] **Step 4: Run documentation tests**

```bash
pytest -q tests/unit/parsing/test_legacy_visual_documentation.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/LEGACY_VISUALS.md README.md tests/unit/parsing/test_legacy_visual_documentation.py
git commit -m "docs: define legacy visual compatibility boundary"
```

### Task 5: Full verification and PR

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run complete verification**

```bash
pytest -q
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

Expected: all PASS.

- [ ] **Step 2: Verify wheels and platform jobs through GitHub Actions**

Require Python 3.11 and 3.13 wheel checks plus Windows and Ubuntu workspace validator jobs to pass.

- [ ] **Step 3: Create PR**

Open a PR against `main`, include RED/GREEN run IDs, state that no canonical converter is provided, and use `Closes #37`.
