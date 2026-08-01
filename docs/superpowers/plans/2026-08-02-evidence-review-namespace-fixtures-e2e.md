# Evidence Review Namespace, Fixtures, and End-to-End Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish issue #22 by making `evidence_review` the canonical Python namespace, isolating all `ansim` compatibility code, replacing sample-specific fixtures, and proving the generic PDF pipeline end to end.

**Architecture:** Perform the package move in a dedicated migration PR after parser/state contracts are stable. Update imports and package data mechanically, retain a narrow `ansim_review` compatibility package that only forwards documented legacy entry points, and add repository gates plus a varied fixture matrix that prevents sample names from re-entering new outputs.

**Tech Stack:** Python 3.11 standard library, setuptools, SQLite schema v2, canonical JSON, pytest, Ruff, strict mypy.

## Global Constraints

- The parser registry/state PR must already be merged.
- Runtime dependencies remain empty.
- Canonical package is `src/evidence_review`.
- Canonical module execution is `python -m evidence_review`.
- Canonical console command remains `evidence-review`.
- New JSON, database, run, packet, release, and documentation outputs contain no `ansim` identifier.
- `src/ansim_review` may contain compatibility forwarding code only.
- Legacy readers are read-only and cannot authorize new release output.
- Renaming must not alter deterministic output except for explicitly versioned product identifiers.

---

## File Map

### Move

- `src/ansim_review/**` -> `src/evidence_review/**`, excluding compatibility-only modules that are recreated explicitly.

### Create

- `src/ansim_review/__init__.py`: deprecation metadata and compatibility import surface.
- `src/ansim_review/__main__.py`: forwards old module execution with a deprecation message.
- `src/ansim_review/cli.py`: forwards `main` only.
- `src/evidence_review/legacy/__init__.py`: explicit legacy package.
- `src/evidence_review/legacy/ansim_workspace.py`: old numbered-folder migration adapter.
- `src/evidence_review/legacy/acceptance.py`: old acceptance inspection adapter.
- `tests/unit/test_namespace_contract.py`: canonical/legacy import boundary.
- `tests/unit/test_no_ansim_new_artifacts.py`: repository and output naming gate.
- `tests/fixtures/generic_pdf/README.md`: fixture provenance and expected role.
- `tests/integration/test_generic_pdf_fixture_matrix.py`: varied input matrix.
- `tests/integration/test_generic_pdf_end_to_end.py`: source batch through searchable evidence and review preparation.

### Modify

- `pyproject.toml`: package discovery, entry points, package data, mypy package target.
- All `src`, `tests`, `scripts`, and `web_runtime` Python imports.
- `schemas/*.json`: identifiers or descriptions still naming the sample product.
- `README.md`, `AGENTS.md`, `docs/CODEX_WORKFLOW.md`, `docs/CHATGPT_WEB_WORKFLOW.md`, `docs/REVIEWER_WORKFLOW.md`.
- Golden fixtures under `tests/golden/**`.
- Release and packaging code paths still using `ansim-evidence.sqlite`, `ansim-v1.0`, or `ansim/` formats.

## Canonical Compatibility Boundary

Allowed legacy locations after completion:

```text
src/ansim_review/**
src/evidence_review/legacy/**
tests/legacy/**
docs/legacy/**
```

Outside those locations, the case-insensitive token `ansim` is forbidden in new source, schemas, fixtures, and user-facing documentation.

---

### Task 1: Freeze current package behavior before the move

**Files:**
- Create: `tests/unit/test_namespace_contract.py`
- Modify: `tests/integration/review_run/test_review_run_cli.py`
- Modify: `tests/integration/parsing/test_source_batch_cli.py`

**Interfaces:**
- Captures current canonical commands and selected public imports before migration.

- [ ] **Step 1: Write passing characterization tests on the parent branch**

Record these public functions/types:

```python
from ansim_review.cli import main
from ansim_review.contracts.source_batch import decode_source_batch
from ansim_review.parsing.source_batch_importer import import_source_batch
from ansim_review.release.attestation import validate_attestation
```

Record `evidence-review --help`, source-batch prepare output, and review-run prepare output.

- [ ] **Step 2: Record canonical output fixtures**

Store canonical JSON bytes for one source-batch preparation and one review-run preparation. These bytes become the post-move equality baseline except for paths that include module names, which must not be emitted.

- [ ] **Step 3: Commit characterization tests**

```bash
pytest tests/unit/test_namespace_contract.py tests/integration/review_run/test_review_run_cli.py tests/integration/parsing/test_source_batch_cli.py -v
git add tests
git commit -m "test: freeze public behavior before namespace migration"
```

### Task 2: Move the canonical package and update packaging configuration

**Files:**
- Move: `src/ansim_review/**` -> `src/evidence_review/**`
- Modify: `pyproject.toml`
- Modify: all Python imports under `src`, `tests`, `scripts`, `web_runtime`

**Interfaces:**
- Canonical import: `evidence_review`
- Canonical module: `python -m evidence_review`
- Console script: `evidence-review = "evidence_review.cli:main"`

- [ ] **Step 1: Move the package as one mechanical commit**

Use filesystem move, preserving file contents:

```bash
git mv src/ansim_review src/evidence_review
```

Do not edit behavior in the same step.

- [ ] **Step 2: Replace imports mechanically**

Replace exact package references:

```text
from ansim_review -> from evidence_review
import ansim_review -> import evidence_review
ansim_review. -> evidence_review.
```

Review string literals separately; do not blindly replace legacy artifact formats.

- [ ] **Step 3: Update `pyproject.toml`**

```toml
[project.scripts]
evidence-review = "evidence_review.cli:main"
ansim-review = "ansim_review.cli:main"

[tool.setuptools.package-data]
"evidence_review.evidence" = ["schema.sql"]
"evidence_review.llm_layer" = ["templates/*.md"]
"evidence_review.review_packet" = ["assets/*.css"]

[tool.mypy]
packages = ["evidence_review", "ansim_review"]
```

- [ ] **Step 4: Run compile and import checks**

```bash
python -m compileall -q src tests scripts web_runtime
python -c "import evidence_review; from evidence_review.cli import main"
```

Expected: PASS for canonical import; legacy import is temporarily absent until Task 3.

- [ ] **Step 5: Commit the mechanical move**

```bash
git add -A
git commit -m "refactor: move runtime to evidence review namespace"
```

### Task 3: Recreate a narrow legacy compatibility package

**Files:**
- Create: `src/ansim_review/__init__.py`
- Create: `src/ansim_review/__main__.py`
- Create: `src/ansim_review/cli.py`
- Create: `src/evidence_review/legacy/__init__.py`
- Move/Modify: legacy workspace and acceptance adapters into `src/evidence_review/legacy/`
- Modify: `tests/unit/test_namespace_contract.py`

**Interfaces:**

```python
# allowed compatibility surface
from ansim_review.cli import main
python -m ansim_review
```

No general submodule aliasing such as `ansim_review.evidence.store` is guaranteed.

- [ ] **Step 1: Write failing compatibility tests**

Assert:

```text
import ansim_review succeeds
from ansim_review.cli import main is evidence_review.cli.main
python -m ansim_review --help exits 0 and writes a deprecation warning to stderr
import ansim_review.evidence.store fails with ModuleNotFoundError
```

- [ ] **Step 2: Implement forwarding files only**

`src/ansim_review/cli.py`:

```python
from evidence_review.cli import main

__all__ = ["main"]
```

`__main__.py` emits one concise warning and exits through `main()`.

- [ ] **Step 3: Move legacy implementation under canonical ownership**

Old numbered-folder import and old acceptance inspection live under `evidence_review.legacy`. Compatibility wrappers may import them, but new code may not import from `ansim_review`.

- [ ] **Step 4: Run tests and commit**

```bash
pytest tests/unit/test_namespace_contract.py -v
git add src/ansim_review src/evidence_review/legacy tests/unit/test_namespace_contract.py
git commit -m "feat: isolate legacy ansim compatibility surface"
```

### Task 4: Remove legacy names from new runtime paths and formats

**Files:**
- Modify: `src/evidence_review/release/validator.py`
- Modify: `src/evidence_review/review_run.py`
- Modify: packaging/release modules under `src/evidence_review/packaging/` and `src/evidence_review/release/`
- Modify: tests covering paths and formats.

**Interfaces:**

Canonical names:

```text
evidence/evidence.sqlite
evidence-review/release-validation
evidence-review/review-run-request
evidence-review/review-run-cli-status
evidence-review/human-attestation
evidence-review-runtime-<version>
```

- [ ] **Step 1: Add failing path/format tests**

Assert new workspace creation and release validation never create or emit:

```text
ansim-evidence.sqlite
ansim-v1.0
ansim/release-validation
ansim/review-run-request
```

- [ ] **Step 2: Remove fallback creation behavior**

Read-only legacy fallback is permitted only inside `evidence_review.legacy`. Canonical runtime code requires `evidence/evidence.sqlite` and new formats.

- [ ] **Step 3: Generate release names from package version/product constant**

Create or use:

```python
PRODUCT_ID = "evidence-review"
PACKAGE_NAME = "evidence-review-system"
```

Release directory name:

```python
f"{PRODUCT_ID}-runtime-{version}"
```

- [ ] **Step 4: Run focused tests and commit**

```bash
pytest tests/integration/release tests/integration/review_run -v
git add src/evidence_review tests
git commit -m "refactor: remove legacy names from new runtime output"
```

### Task 5: Add repository gate for new `ansim` references

**Files:**
- Create: `tests/unit/test_no_ansim_new_artifacts.py`
- Modify: `.github/workflows/ci.yml` only if pytest is not already guaranteed to run the gate.

**Interfaces:**
- Test scans tracked source/schema/docs/fixture text with explicit allowlisted roots.

- [ ] **Step 1: Write the failing scanner test**

Scan extensions:

```text
.py .json .md .toml .yml .yaml .html .css .js
```

Exclude:

```python
_ALLOWED_PREFIXES = (
    "src/ansim_review/",
    "src/evidence_review/legacy/",
    "tests/legacy/",
    "docs/legacy/",
)
```

Reject case-insensitive `ansim` elsewhere.

- [ ] **Step 2: Run test and capture all current failures**

Run: `pytest tests/unit/test_no_ansim_new_artifacts.py -v`

Use the result as a deterministic cleanup list.

- [ ] **Step 3: Make scanner resilient**

Read UTF-8 text only. A decode failure in a tracked text extension is a test failure, not an ignored file.

- [ ] **Step 4: Commit the gate before cleanup**

The branch may be intentionally red at this commit if using strict TDD:

```bash
git add tests/unit/test_no_ansim_new_artifacts.py
git commit -m "test: prohibit legacy identifiers in new artifacts"
```

### Task 6: Replace sample-specific tests and documentation

**Files:**
- Move: legacy-specific tests/fixtures into `tests/legacy/**` when still required.
- Modify: `README.md`, `AGENTS.md`, and workflow docs.
- Modify: schemas and golden fixtures reported by Task 5.

- [ ] **Step 1: Classify every scanner finding**

For each result choose exactly one:

```text
rename to generic product terminology
move to explicit legacy path
remove obsolete sample fixture
```

Do not expand the allowlist for convenience.

- [ ] **Step 2: Rename generic golden fixtures**

Examples:

```text
tests/golden/questions/ansim_cases.json
-> tests/golden/questions/generic_review_cases.json
```

Replace sample document IDs `LAW1`/`LAW2` with neutral IDs generated from fixture hashes or explicit IDs such as `REFERENCE-A` only where manifest-declared.

- [ ] **Step 3: Update all user-facing commands**

Use:

```text
python -m evidence_review
evidence-review
evidence-review-workspace
evidence.sqlite
```

Legacy commands belong in a clearly labeled compatibility appendix only.

- [ ] **Step 4: Run the gate and documentation tests**

```bash
pytest tests/unit/test_no_ansim_new_artifacts.py tests/unit/test_documentation_contracts.py -v
```

- [ ] **Step 5: Commit cleanup**

```bash
git add -A
git commit -m "docs: complete generic evidence review terminology"
```

### Task 7: Build the generic PDF fixture matrix

**Files:**
- Create: `tests/fixtures/generic_pdf/README.md`
- Create fixture manifests and compact parser artifacts under `tests/fixtures/generic_pdf/`.
- Create: `tests/integration/test_generic_pdf_fixture_matrix.py`

**Interfaces:**
- Fixtures are synthetic or redistributable and document their generation method.

Required cases:

```text
reference-text/       legal or operational text PDF
report/               general report PDF
table-heavy/          table-centered PDF
scan/                 image-based scan PDF
drawing/              architectural drawing PDF
same-name-different/  same filename, different bytes
different-name-same/  different filename, identical bytes
```

- [ ] **Step 1: Add fixture provenance README**

For every fixture record:

```text
source generation command or origin
SHA-256
parser adapter kind
expected role
expected page/element/table/visual counts
expected preparation state
```

- [ ] **Step 2: Write failing parameterized matrix test**

For each case assert source identity, revision identity, state, counts, and expected parser dispatch.

- [ ] **Step 3: Add collision/dedupe assertions**

```python
assert same_name_different[0].document_id != same_name_different[1].document_id
assert different_name_same[0].source_sha256 == different_name_same[1].source_sha256
assert len(deduplicated_sources) == 1
```

- [ ] **Step 4: Run matrix tests and correct fixtures**

```bash
pytest tests/integration/test_generic_pdf_fixture_matrix.py -v
```

- [ ] **Step 5: Commit fixtures and tests**

```bash
git add tests/fixtures/generic_pdf tests/integration/test_generic_pdf_fixture_matrix.py
git commit -m "test: add generic PDF fixture matrix"
```

### Task 8: Add generic end-to-end review preparation

**Files:**
- Create: `tests/integration/test_generic_pdf_end_to_end.py`
- Modify: integration helpers only when shared setup is duplicated.

**Interfaces:**
- End-to-end boundary:

```text
source-batch v2
-> prepare
-> ingest schema-v2 evidence DB
-> build retrieval index
-> query evidence
-> create review-run request
-> prepare Track A bundle
-> verify citations and numeric provenance
```

- [ ] **Step 1: Write failing E2E ready scenario**

Use at least a text reference and table-heavy reference. Assert:

```text
overall source state READY_TO_EVALUATE
schema version 2
retrieval citations include page_id/revision/page/source hash
review run state AWAITING_TRACK_OUTPUTS
new artifact formats use evidence-review prefix
```

- [ ] **Step 2: Write pending parser scenario**

A scan PDF without parser artifact must end at `PENDING_PARSER_OUTPUT`, create no evidence DB, and not prepare a review run.

- [ ] **Step 3: Write drawing scenario**

A drawing role must end at `PENDING_DRAWING_INGESTION` or `INPUT_CONFIRMATION_REQUIRED`; it must not be silently inserted as a reference document.

- [ ] **Step 4: Write byte-reproducibility scenario**

Run the ready scenario twice in separate directories and compare canonical machine JSON bytes and logical DB snapshot hashes.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/integration/test_generic_pdf_end_to_end.py -v
git add tests/integration/test_generic_pdf_end_to_end.py
git commit -m "test: verify generic PDF review pipeline end to end"
```

### Task 9: Full namespace and epic verification

- [ ] **Step 1: Run canonical and compatibility commands**

```bash
evidence-review --help
python -m evidence_review --help
ansim-review --help
python -m ansim_review --help
```

Canonical commands must be warning-free. Legacy commands must emit one deprecation warning and otherwise behave equivalently.

- [ ] **Step 2: Run focused suites**

```bash
pytest tests/unit/test_namespace_contract.py -v
pytest tests/unit/test_no_ansim_new_artifacts.py -v
pytest tests/integration/test_generic_pdf_fixture_matrix.py -v
pytest tests/integration/test_generic_pdf_end_to_end.py -v
```

- [ ] **Step 3: Run full quality gate**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

- [ ] **Step 4: Inspect built package contents**

```bash
python -m build
python -m zipfile -l dist/*.whl
```

Confirm package contains `evidence_review/**`, narrow `ansim_review/**` wrappers, schema/package data, and no duplicated full runtime under the legacy namespace.

- [ ] **Step 5: Commit verification corrections**

```bash
git add -A
git commit -m "test: verify generic evidence review release"
```

- [ ] **Step 6: PR body and issue closure**

Use `Closes #22` only when the repository gate, fixture matrix, E2E scenarios, and full CI all pass.