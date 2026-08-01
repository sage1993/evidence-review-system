# Generic PDF and Trust-Boundary Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept arbitrary user-provided PDFs through a generic manifest while removing sample filename assumptions and fixing the rule and run-identity trust-boundary defects.

**Architecture:** Add a strict `source-batch` contract and importer that derive identity from source bytes or explicit safe IDs. Keep the current Python import namespace as a temporary compatibility detail, expose `evidence-review` as the product identifier, and isolate old numbered-folder behavior in a legacy adapter. Apply validation at rule-load and path-construction boundaries and compute Run IDs from the complete normalized request.

**Tech Stack:** Python 3.11 standard library, dataclasses, pathlib, hashlib, canonical JSON, SQLite, pytest, Ruff, strict mypy.

## Global Constraints

- Runtime dependencies remain empty.
- Project code does not call model or external search APIs.
- New artifacts use the `evidence-review/` format prefix.
- Source and parser paths must be safe relative paths below a caller-provided batch root.
- Display titles and filenames never control document identity.
- Same deterministic input produces byte-equivalent canonical JSON.
- Existing `ansim/*` input is accepted only through explicitly named legacy adapters.
- No implementation task in this plan changes the evidence DB page schema or release acceptance signature model.

---

## File Map

### New files

- `schemas/source-batch.schema.json`: external source-batch JSON schema.
- `src/ansim_review/contracts/source_batch.py`: strict source-batch decoder and canonical document writer.
- `src/ansim_review/parsing/source_batch_importer.py`: generic PDF/parser ingestion orchestration.
- `src/ansim_review/contracts/identifiers.py`: shared safe ID and version validation.
- `tests/unit/contracts/test_source_batch.py`: source-batch contract tests.
- `tests/unit/parsing/test_source_batch_importer.py`: generic identity, dedupe, and pending-parser tests.
- `tests/unit/contracts/test_identifiers.py`: safe identifier tests.

### Modified files

- `src/ansim_review/parsing/_ansim_sources.py`: remove LAW1/LAW2 special IDs and expose legacy discovery only.
- `src/ansim_review/parsing/_ansim_csv.py`: require explicit visual document IDs.
- `src/ansim_review/parsing/ansim_workspace_adapter.py`: convert legacy folder discovery to generic source-batch input.
- `src/ansim_review/rule_engine/loader.py`: validate input references.
- `src/ansim_review/rule_engine/evaluator.py`: validate referenced calculations only.
- `src/ansim_review/rule_engine/promotion.py`: safe direct-child output path.
- `src/ansim_review/contracts/run_context.py`: hash the complete normalized request.
- `src/ansim_review/review_run.py`: call the new Run ID interface.
- `src/ansim_review/cli.py`: product name and source-batch import command.
- `pyproject.toml`: `evidence-review` command, legacy CLI alias retained.
- `README.md`: generic workflow and neutral paths.

---

### Task 1: Shared safe identifiers

**Files:**
- Create: `src/ansim_review/contracts/identifiers.py`
- Create: `tests/unit/contracts/test_identifiers.py`

**Interfaces:**
- Produces: `validate_identifier(value: object, field: str) -> str`
- Produces: `validate_version(value: object, field: str) -> str`
- Produces: `safe_direct_child(root: Path, filename: str, field: str) -> Path`

- [ ] **Step 1: Write failing tests**

```python
import pytest

from ansim_review.contracts.identifiers import (
    safe_direct_child,
    validate_identifier,
    validate_version,
)


def test_identifier_accepts_stable_machine_id() -> None:
    assert validate_identifier("BUILDING-HEIGHT.001", "rule_id") == "BUILDING-HEIGHT.001"


@pytest.mark.parametrize("value", ["../RULE", "/tmp/RULE", "C:\\tmp\\RULE", "RULE/CHILD", ""])
def test_identifier_rejects_path_syntax(value: str) -> None:
    with pytest.raises(ValueError):
        validate_identifier(value, "rule_id")


def test_safe_direct_child_stays_below_root(tmp_path) -> None:
    assert safe_direct_child(tmp_path, "RULE@1.0.0.json", "approved_path").parent == tmp_path.resolve()


def test_version_requires_numeric_semver() -> None:
    assert validate_version("1.2.3", "version") == "1.2.3"
    with pytest.raises(ValueError):
        validate_version("../1", "version")
```

- [ ] **Step 2: Run focused tests and confirm import failure**

Run: `pytest tests/unit/contracts/test_identifiers.py -v`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement strict validators**

Use `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` for generic identifiers and `^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$` for versions. Resolve the candidate path and require `candidate.parent == root.resolve()` before returning it.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/unit/contracts/test_identifiers.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ansim_review/contracts/identifiers.py tests/unit/contracts/test_identifiers.py
git commit -m "feat: add safe machine identifier contracts"
```

### Task 2: Secure rule promotion

**Files:**
- Modify: `src/ansim_review/rule_engine/loader.py`
- Modify: `src/ansim_review/rule_engine/promotion.py`
- Test: existing rule loader and promotion test modules

**Interfaces:**
- Consumes: `validate_identifier`, `validate_version`, `safe_direct_child`

- [ ] **Step 1: Add failing promotion tests**

Add parameterized candidate rules using `../RULE`, `/tmp/RULE`, `C:\\tmp\\RULE`, and `RULE/CHILD`. Assert `promote_candidate()` raises before creating any file outside `approved_dir`.

- [ ] **Step 2: Confirm tests fail**

Run the focused rule-promotion test module.

- [ ] **Step 3: Validate IDs during `load_rule()`**

Replace raw `_string()` decoding for `rule_id` and `version` with the shared validators.

- [ ] **Step 4: Construct the approval path through `safe_direct_child()`**

```python
approved_path = safe_direct_child(
    approved_dir,
    f"{rule.rule_id}@{rule.version}.json",
    "approved_rule_path",
)
```

Perform this check before `mkdir()` or any write.

- [ ] **Step 5: Run focused and full rule tests**

Run: `pytest tests/unit/rule_engine -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/rule_engine tests/unit/rule_engine
git commit -m "fix: contain promoted rule paths"
```

### Task 3: Validate rule references and actual calculation dependencies

**Files:**
- Modify: `src/ansim_review/rule_engine/loader.py`
- Modify: `src/ansim_review/rule_engine/evaluator.py`
- Test: existing loader and evaluator test modules

**Interfaces:**
- Produces internal helpers `_input_references(expression) -> frozenset[str]`
- Produces internal helpers `_calculation_references(expression) -> frozenset[str]`

- [ ] **Step 1: Write failing loader test**

Create a rule whose expression references `road_width_m` while `input_schema` declares only `site_area_m2`. Assert `load_rule()` raises `ValueError` containing `undeclared input reference`.

- [ ] **Step 2: Write failing evaluator test**

Pass one referenced successful calculation and one unrelated failed calculation. Assert the rule evaluates from the referenced result and ignores the unrelated result.

- [ ] **Step 3: Run tests and confirm both failures**

- [ ] **Step 4: Collect and validate references in the loader**

After `_validate_node()`, recursively collect input names and reject `references - input_schema.keys()`.

- [ ] **Step 5: Restrict calculation validation in the evaluator**

Build `referenced_ids` from the expression, reject duplicate supplied IDs, and validate only `calculation_map[id]` for IDs in `referenced_ids`. Missing referenced IDs remain `INVALID_CALCULATION_REFERENCE`.

- [ ] **Step 6: Run rule tests**

Run: `pytest tests/unit/rule_engine -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ansim_review/rule_engine tests/unit/rule_engine
git commit -m "fix: validate rule dependency references"
```

### Task 4: Complete deterministic Run identity

**Files:**
- Modify: `src/ansim_review/contracts/run_context.py`
- Modify: `src/ansim_review/review_run.py`
- Test: existing run-context and review-run test modules

**Interfaces:**
- Produces: `compute_run_id(request_document: Mapping[str, Any]) -> str`

- [ ] **Step 1: Add failing tests**

Create identical normalized requests and vary only:

- one approved rule result ID;
- one confidence factor value;
- one confidence factor source.

Assert each change creates a different Run ID. Reorder mapping keys and assert the ID remains the same.

- [ ] **Step 2: Confirm current collisions**

Run focused tests and verify the changed approvals/confidence cases fail.

- [ ] **Step 3: Replace the fragmented signature**

```python
def compute_run_id(request_document: Mapping[str, Any]) -> str:
    digest = sha256_json(dict(request_document))
    return f"RUN-{digest[:20].upper()}"
```

The caller must supply the already-normalized request document.

- [ ] **Step 4: Update `prepare_review_run()`**

Call `compute_run_id(normalized_request)` after all lists and mappings have been sorted or canonically constructed.

- [ ] **Step 5: Run focused tests**

Run review-run and run-context tests.

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/contracts/run_context.py src/ansim_review/review_run.py tests
git commit -m "fix: bind run identity to complete request"
```

### Task 5: Define generic source-batch contract

**Files:**
- Create: `schemas/source-batch.schema.json`
- Create: `src/ansim_review/contracts/source_batch.py`
- Create: `tests/unit/contracts/test_source_batch.py`
- Modify: `tests/unit/contracts/test_schema_documents.py`

**Interfaces:**
- Produces: `ParserBinding(kind: Literal["OPENDATALOADER_JSON"], artifact_path: str)`
- Produces: `SourceItem(source_path: str, role: AttachmentRole, document_id: str | None, display_title: str | None, parser: ParserBinding | None)`
- Produces: `SourceBatch(format: Literal["evidence-review/source-batch"], version: Literal[1], sources: tuple[SourceItem, ...])`
- Produces: `decode_source_batch(value: object) -> SourceBatch`
- Produces: `source_batch_document(batch: SourceBatch) -> dict[str, object]`

- [ ] **Step 1: Write contract tests**

Cover strict required fields, unknown fields, unsafe relative paths, unknown parser kind, duplicate source paths, and canonical round trip.

- [ ] **Step 2: Confirm tests fail**

Run: `pytest tests/unit/contracts/test_source_batch.py -v`

- [ ] **Step 3: Implement decoder and schema**

Reuse `ImmutableAttachment` role literals and path safety rules. Allow parser to be null so a PDF can be registered in pending state.

- [ ] **Step 4: Register schema in schema-document tests**

- [ ] **Step 5: Run contract tests**

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add schemas/source-batch.schema.json src/ansim_review/contracts/source_batch.py tests/unit/contracts
git commit -m "feat: define generic source batch contract"
```

### Task 6: Implement source-byte identity and generic importer

**Files:**
- Create: `src/ansim_review/parsing/source_batch_importer.py`
- Create: `tests/unit/parsing/test_source_batch_importer.py`
- Modify: `src/ansim_review/parsing/source_manifest.py`

**Interfaces:**
- Produces: `derive_document_id(source_sha256: str, explicit: str | None) -> str`
- Produces: `PreparedSource(source_path: Path, parser_path: Path | None, document_id: str, revision_id: str, source_sha256: str, display_title: str)`
- Produces: `prepare_source_batch(batch_root: Path, batch: SourceBatch) -> tuple[PreparedSource, ...]`

- [ ] **Step 1: Write identity tests**

Use temporary byte files to prove:

- same bytes/different filenames deduplicate;
- same filename/different bytes produce different IDs;
- explicit safe IDs are preserved;
- duplicate explicit ID with different bytes fails;
- missing parser returns a prepared source with `parser_path=None`;
- parser path outside root fails before reading.

- [ ] **Step 2: Confirm tests fail**

- [ ] **Step 3: Implement byte-based identity**

Auto ID format: `DOC-<first 20 uppercase source SHA-256 characters>`.

- [ ] **Step 4: Implement deterministic dedupe**

Sort prepared sources by `(document_id, revision_id, source_path.as_posix())`. Deduplicate identical source hashes. Reject explicit-ID conflicts.

- [ ] **Step 5: Run tests**

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/parsing/source_batch_importer.py src/ansim_review/parsing/source_manifest.py tests/unit/parsing/test_source_batch_importer.py
git commit -m "feat: prepare arbitrary PDF source batches"
```

### Task 7: Remove sample filename assumptions from legacy migration

**Files:**
- Modify: `src/ansim_review/parsing/_ansim_sources.py`
- Modify: `src/ansim_review/parsing/_ansim_csv.py`
- Modify: `src/ansim_review/parsing/ansim_workspace_adapter.py`
- Test: existing migration/parsing tests

**Interfaces:**
- Legacy adapter produces generic `SourceBatch` and calls the new preparation path.

- [ ] **Step 1: Add failing tests**

- `law-1.pdf` no longer becomes privileged `LAW1` unless explicitly declared.
- arbitrary Korean and English filenames produce source-hash IDs.
- visual manifest without `document_id` is rejected instead of inferred from filename.

- [ ] **Step 2: Confirm failures**

- [ ] **Step 3: Remove `law-1` and `law-2` branches**

Delete filename special cases from document identity and visual manifest selection.

- [ ] **Step 4: Convert fixed-folder discovery into a legacy SourceBatch builder**

Keep `02_source_pdf` and `05_exports` only inside the legacy adapter. The generic importer receives explicit paths.

- [ ] **Step 5: Run migration and parsing tests**

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/parsing tests
git commit -m "refactor: isolate legacy sample workspace discovery"
```

### Task 8: User-facing product identifier and CLI

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/ansim_review/cli.py`
- Modify: `README.md`
- Create or modify CLI tests

**Interfaces:**
- Primary command: `evidence-review`
- Compatibility alias: `ansim-review`
- New CLI status format: `evidence-review/review-run-cli-status`

- [ ] **Step 1: Add failing CLI tests**

Assert parser program name is `evidence-review`, subcommands are required, and status documents use the new prefix.

- [ ] **Step 2: Update entry points**

```toml
[project.scripts]
evidence-review = "ansim_review.cli:main"
ansim-review = "ansim_review.cli:main"
```

Keep the old entry point documented as temporary compatibility only.

- [ ] **Step 3: Require subcommands**

Set `required=True` for both subparser levels so incomplete invocation returns argparse error status.

- [ ] **Step 4: Update README examples**

Use neutral workspace paths, `evidence.sqlite`, and generic PDF source-batch examples. Move the numbered Ansim/Grist workspace to a legacy migration appendix.

- [ ] **Step 5: Run CLI tests**

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/ansim_review/cli.py README.md tests
git commit -m "docs: expose generic evidence review product identity"
```

### Task 9: Full verification and issue linkage

**Files:**
- Modify: relevant docs if verification finds mismatches

- [ ] **Step 1: Run focused tests**

```bash
pytest tests/unit/contracts -v
pytest tests/unit/rule_engine -v
pytest tests/unit/parsing -v
```

- [ ] **Step 2: Run full quality gates**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

- [ ] **Step 3: Search new artifacts and user-facing docs**

Run a repository search for `law-1`, `law-2`, `LAW1`, `LAW2`, `ansim-v1.0`, `F:\\ansim`, and `ansim/review-run-request`. Remaining occurrences must be located only in explicitly named legacy compatibility tests or adapters.

- [ ] **Step 4: Update issue state**

Close #17, #18, and #21 only when their focused tests and full CI pass. Add progress references to #22. Keep #19 and #20 open.

- [ ] **Step 5: Commit any verification corrections**

```bash
git add -A
git commit -m "test: verify generic PDF and hardening changes"
```
