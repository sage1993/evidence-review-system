# Generic Parser Registry and Source State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the generic PDF intake architecture by replacing hard-coded parser dispatch with a registry, representing all required source states, and requiring explicit visual page identity.

**Architecture:** Upgrade `source-batch` to version 2 while retaining a strict version 1 reader, separate source preparation from role-specific readiness, and dispatch parser artifacts through registered adapters that emit one normalized evidence contribution contract. Visual evidence must identify document, revision, and page explicitly; filenames never imply identity.

**Tech Stack:** Python 3.11 standard library, dataclasses, pathlib, SQLite schema v2, canonical JSON, JSON Schema documents, pytest.

## Global Constraints

- PRs for #19, #25, #26, and #20 must already be merged.
- Runtime dependencies remain empty.
- Parser adapters do not modify source or parser artifact bytes.
- Filenames and display titles never determine document identity.
- Source hash and explicit manifest data determine document and revision identity.
- New status documents use `evidence-review/` formats.
- Unsupported or unavailable parser output produces a pending/blocked state, never an empty successful database.
- Case drawings and supporting images are not silently inserted as reference-document evidence.
- All page-bearing records use schema v2 `page_id` authority.

---

## File Map

### Create

- `src/ansim_review/parsing/parser_registry.py`: adapter protocol, registry, and deterministic dispatch.
- `src/ansim_review/parsing/parser_models.py`: normalized parser contribution dataclasses.
- `src/ansim_review/parsing/source_states.py`: source-state enum and transition rules.
- `src/ansim_review/parsing/visual_manifest.py`: strict explicit visual identity decoder.
- `schemas/source-batch-v2.schema.json`: version 2 contract.
- `schemas/visual-manifest.schema.json`: explicit visual identity contract.
- `tests/unit/parsing/test_parser_registry.py`: registration and dispatch tests.
- `tests/unit/parsing/test_source_states.py`: transition/readiness tests.
- `tests/unit/parsing/test_visual_manifest.py`: identity and path tests.
- `tests/integration/parsing/test_multi_adapter_source_batch.py`: mixed-adapter integration.

### Modify

- `src/ansim_review/contracts/source_batch.py`: v1/v2 decoding and parser configuration.
- `schemas/source-batch.schema.json`: retain version 1 as legacy/current compatibility schema or redirect schema registration explicitly.
- `src/ansim_review/parsing/odl_adapter.py`: implement normalized adapter protocol.
- `src/ansim_review/parsing/odl_source.py`: keep ODL-specific parsing behind adapter boundary.
- `src/ansim_review/parsing/source_batch_importer.py`: registry dispatch and complete source states.
- `src/ansim_review/parsing/_ansim_csv.py`: consume strict visual manifest, remove filename inference.
- `src/ansim_review/cli.py`: status-only `prepare` and registry-aware `ingest` output.
- `tests/unit/contracts/test_source_batch.py`: v1/v2 compatibility and strictness.
- `tests/unit/parsing/test_source_batch_importer.py`: state matrix and no-empty-DB tests.
- `tests/integration/parsing/test_source_batch_cli.py`: CLI state projections.
- `tests/unit/contracts/test_schema_documents.py`: new schemas.
- `README.md`: version 2 examples and adapter list.
- `docs/CODEX_WORKFLOW.md`: source state behavior.

## Public Interfaces

```python
ParserKind = str

@dataclass(frozen=True, slots=True)
class ParserArtifactBinding:
    kind: str
    artifact_path: str
    options: Mapping[str, object]

@dataclass(frozen=True, slots=True)
class NormalizedParserContribution:
    page_count: int
    page_dimensions: tuple[PageDimensions, ...]
    elements: tuple[ParsedElement, ...]
    tables: tuple[ParsedTable, ...]
    visuals: tuple[ParsedVisual, ...]
    parser_artifact_sha256: str

class ParserAdapter(Protocol):
    kind: str
    def parse(self, context: ParserContext) -> NormalizedParserContribution: ...

class ParserRegistry:
    def register(self, adapter: ParserAdapter) -> None: ...
    def require(self, kind: str) -> ParserAdapter: ...
    def kinds(self) -> tuple[str, ...]: ...
```

Source states:

```text
RECEIVED
CLASSIFYING_INPUTS
PENDING_PARSER_OUTPUT
PENDING_REFERENCE_INGESTION
PENDING_DRAWING_INGESTION
INPUT_CONFIRMATION_REQUIRED
READY_TO_EVALUATE
BLOCKED
FAILED
```

---

### Task 1: Define normalized parser contribution models

**Files:**
- Create: `src/ansim_review/parsing/parser_models.py`
- Create: `tests/unit/parsing/test_parser_models.py`

**Interfaces:**
- Produces immutable page, element, table, visual, and contribution dataclasses.

- [ ] **Step 1: Write failing invariant tests**

Cover:

```text
page numbers start at 1
page IDs are not supplied by adapters
page dimensions are positive and finite
element/table/visual page numbers exist in page dimensions
bbox is finite and inside declared page
parser artifact hash is lowercase SHA-256
```

Example:

```python
def test_contribution_rejects_element_for_unknown_page() -> None:
    with pytest.raises(ValueError, match="PARSER_PAGE_NOT_FOUND"):
        NormalizedParserContribution(
            page_count=1,
            page_dimensions=(PageDimensions(1, 612.0, 792.0),),
            elements=(ParsedElement(page_number=2, ...),),
            tables=(),
            visuals=(),
            parser_artifact_sha256="a" * 64,
        )
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/parsing/test_parser_models.py -v`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement focused immutable models**

Adapters emit page numbers and source-relative values only. The importer derives `page_id` from the resolved revision ID.

- [ ] **Step 4: Reuse schema v2 bbox validation**

Call `validate_bbox_within_page()` from issue #19 rather than duplicating geometry checks.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/unit/parsing/test_parser_models.py -v
git add src/ansim_review/parsing/parser_models.py tests/unit/parsing/test_parser_models.py
git commit -m "feat: define normalized parser contribution model"
```

### Task 2: Implement deterministic parser registry

**Files:**
- Create: `src/ansim_review/parsing/parser_registry.py`
- Create: `tests/unit/parsing/test_parser_registry.py`

**Interfaces:**
- Produces: `ParserAdapter` protocol and `ParserRegistry`.
- Produces: `build_default_parser_registry() -> ParserRegistry`.

- [ ] **Step 1: Write failing registry tests**

Assert:

```text
register unique kind -> available
duplicate kind -> error
blank/unsafe kind -> error
unknown kind -> UNSUPPORTED_PARSER_KIND
kinds() -> sorted tuple
adapter exception -> propagated as parser failure, not converted to success
```

- [ ] **Step 2: Run tests and confirm failure**

- [ ] **Step 3: Implement exact-kind dispatch**

Use validated machine identifiers for `kind`. Registry lookup is case-sensitive; do not normalize unknown strings.

- [ ] **Step 4: Build default registry**

Register the ODL adapter under exactly:

```text
OPENDATALOADER_JSON
```

No module-level mutable registry is allowed. Construct the registry at the command/application boundary and inject it.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/unit/parsing/test_parser_registry.py -v
git add src/ansim_review/parsing/parser_registry.py tests/unit/parsing/test_parser_registry.py
git commit -m "feat: add deterministic parser adapter registry"
```

### Task 3: Convert OpenDataLoader code to the adapter protocol

**Files:**
- Modify: `src/ansim_review/parsing/odl_adapter.py`
- Modify: `src/ansim_review/parsing/odl_source.py`
- Modify: `tests/unit/parsing/test_odl_adapter.py`

**Interfaces:**
- Produces: `OpenDataLoaderJsonAdapter.parse(context) -> NormalizedParserContribution`.

- [ ] **Step 1: Add failing normalized-output test**

Use an existing ODL JSON fixture and assert the adapter returns page dimensions, stable parser order, raw payload hashes, and bboxes without document/revision/page IDs.

- [ ] **Step 2: Add source-binding mismatch test**

A parser-declared filename that conflicts with the source PDF must raise `PARSER_SOURCE_MISMATCH` before contribution output.

- [ ] **Step 3: Run focused tests**

- [ ] **Step 4: Move ODL orchestration behind the adapter class**

The generic importer must no longer import `read_parser_json`, `load_raw_elements`, or ODL-specific helper functions directly.

- [ ] **Step 5: Preserve byte-equivalent ODL evidence output**

Build a golden expected normalized contribution and compare canonical JSON projection.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/unit/parsing/test_odl_adapter.py -v
git add src/ansim_review/parsing/odl_adapter.py src/ansim_review/parsing/odl_source.py tests/unit/parsing/test_odl_adapter.py
git commit -m "refactor: expose OpenDataLoader through parser adapter"
```

### Task 4: Define source-batch version 2

**Files:**
- Create: `schemas/source-batch-v2.schema.json`
- Modify: `src/ansim_review/contracts/source_batch.py`
- Modify: `tests/unit/contracts/test_source_batch.py`
- Modify: `tests/unit/contracts/test_schema_documents.py`

**Interfaces:**
- `decode_source_batch()` accepts version 1 and 2.
- Canonical new writer emits version 2 only.

Version 2 parser object:

```json
{
  "kind": "OPENDATALOADER_JSON",
  "artifact_path": "inputs/parser/document.json",
  "options": {}
}
```

- [ ] **Step 1: Add failing v2 contract tests**

Cover strict fields, unknown options shape, unsafe artifact path, unknown parser kind at contract level permitted as a string but rejected by registry at preparation, and canonical v2 round-trip.

- [ ] **Step 2: Add v1 reader compatibility test**

The existing version 1 object decodes to the same internal model with `options={}`.

- [ ] **Step 3: Run tests and confirm failure**

- [ ] **Step 4: Split external version from internal model**

Use one internal `SourceBatch` dataclass whose writer always emits:

```text
format = evidence-review/source-batch
version = 2
```

Keep `decode_source_batch_v1()` private and explicit.

- [ ] **Step 5: Register schema tests and commit**

```bash
pytest tests/unit/contracts/test_source_batch.py tests/unit/contracts/test_schema_documents.py -v
git add schemas/source-batch-v2.schema.json src/ansim_review/contracts/source_batch.py tests/unit/contracts
git commit -m "feat: add extensible source batch version two"
```

### Task 5: Implement complete source-state model

**Files:**
- Create: `src/ansim_review/parsing/source_states.py`
- Create: `tests/unit/parsing/test_source_states.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class SourceReadiness:
    state: SourceState
    reason_codes: tuple[str, ...]
    can_ingest_reference: bool
    can_evaluate: bool


def evaluate_source_readiness(source: PreparedSource) -> SourceReadiness:
    ...
```

- [ ] **Step 1: Write failing state matrix tests**

Required mapping:

```text
REFERENCE_DOCUMENT + no parser      -> PENDING_PARSER_OUTPUT
REFERENCE_DOCUMENT + parser ready   -> PENDING_REFERENCE_INGESTION
CASE_DRAWING                         -> PENDING_DRAWING_INGESTION
CASE_DRAWING + candidate confirmation pending -> INPUT_CONFIRMATION_REQUIRED
SUPPORTING_IMAGE                     -> BLOCKED for rule evaluation, available as supporting evidence
unknown role/config conflict         -> FAILED
fully ingested reference set         -> READY_TO_EVALUATE
```

- [ ] **Step 2: Write transition tests**

Reject illegal direct transitions such as `RECEIVED -> READY_TO_EVALUATE` without preparation/ingestion evidence.

- [ ] **Step 3: Run tests and confirm failure**

- [ ] **Step 4: Implement pure state evaluation**

The function does not write files or databases. It returns deterministic reasons that the importer/CLI projects.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/unit/parsing/test_source_states.py -v
git add src/ansim_review/parsing/source_states.py tests/unit/parsing/test_source_states.py
git commit -m "feat: define generic source readiness states"
```

### Task 6: Refactor source-batch preparation and ingest around registry/state

**Files:**
- Modify: `src/ansim_review/parsing/source_batch_importer.py`
- Modify: `tests/unit/parsing/test_source_batch_importer.py`

**Interfaces:**

```python
def prepare_source_batch(
    batch_root: Path,
    batch: SourceBatch,
    registry: ParserRegistry,
) -> SourceBatchPreparationReport:
    ...


def import_source_batch(
    batch_root: Path,
    batch: SourceBatch,
    output_db: Path,
    registry: ParserRegistry,
) -> SourceBatchImportReport:
    ...
```

- [ ] **Step 1: Add failing preparation-state tests**

Prove preparation returns all source states without creating an evidence DB.

- [ ] **Step 2: Add no-empty-database tests**

For pending parser, drawing-only, blocked, or failed batches:

```python
with pytest.raises(SourceBatchNotReady): ...
assert not output_db.exists()
```

- [ ] **Step 3: Add unknown parser-kind test**

The contract accepts the string in v2, but preparation reports `BLOCKED` with `UNSUPPORTED_PARSER_KIND` unless the registry contains it.

- [ ] **Step 4: Replace ODL conditional dispatch**

Delete:

```python
if source.parser_kind != "OPENDATALOADER_JSON": ...
```

Use:

```python
adapter = registry.require(source.parser.kind)
contribution = adapter.parse(context)
```

- [ ] **Step 5: Build schema-v2 records from normalized contribution**

Derive `page_id` using revision ID and contribution page number. Insert tables and visuals as well as elements.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/unit/parsing/test_source_batch_importer.py tests/unit/parsing/test_source_states.py -v
git add src/ansim_review/parsing/source_batch_importer.py tests/unit/parsing/test_source_batch_importer.py
git commit -m "refactor: prepare source batches through registry and states"
```

### Task 7: Require explicit visual identity

**Files:**
- Create: `schemas/visual-manifest.schema.json`
- Create: `src/ansim_review/parsing/visual_manifest.py`
- Create: `tests/unit/parsing/test_visual_manifest.py`
- Modify: `src/ansim_review/parsing/_ansim_csv.py`
- Modify: `tests/unit/contracts/test_schema_documents.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class VisualManifestEntry:
    visual_id: str
    document_id: str
    revision_id: str
    page_id: str
    kind: str
    relative_path: str
    sha256: str
    bbox: BBox | None
```

- [ ] **Step 1: Write failing strict identity tests**

Reject entries missing any of:

```text
document_id
revision_id
page_id
```

Reject a page ID that does not belong to the declared revision or document when resolving against the DB.

- [ ] **Step 2: Add filename-inference regression**

A file named `law-1-page-3.png` without explicit IDs must be rejected; it must not become `LAW1` page 3.

- [ ] **Step 3: Run tests and confirm failure**

- [ ] **Step 4: Implement decoder and DB resolver**

Validate safe relative path and source hash. Resolve:

```sql
SELECT d.id, r.id, p.id
FROM pages p
JOIN revisions r ON r.id = p.revision_id
JOIN documents d ON d.id = r.document_id
WHERE p.id = ?
```

Require all three IDs to match.

- [ ] **Step 5: Remove visual filename inference from legacy CSV path**

Legacy conversion must construct explicit entries before calling the common visual importer.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/unit/parsing/test_visual_manifest.py tests/unit/contracts/test_schema_documents.py -v
git add schemas/visual-manifest.schema.json src/ansim_review/parsing/visual_manifest.py src/ansim_review/parsing/_ansim_csv.py tests
git commit -m "fix: require explicit visual page identity"
```

### Task 8: Add prepare/ingest CLI state projections

**Files:**
- Modify: `src/ansim_review/cli.py`
- Modify: `tests/integration/parsing/test_source_batch_cli.py`
- Modify: `README.md`
- Modify: `docs/CODEX_WORKFLOW.md`

**Interfaces:**

```powershell
evidence-review source-batch prepare --root ... --manifest ...
evidence-review source-batch ingest --root ... --manifest ... --output ...
```

- [ ] **Step 1: Add failing CLI tests**

`prepare` returns canonical status without DB creation. `ingest` returns exit 2 and no DB when any source is not ready for reference ingestion.

- [ ] **Step 2: Define status document**

```json
{
  "format": "evidence-review/source-batch-status",
  "version": 2,
  "overall_state": "PENDING_PARSER_OUTPUT",
  "sources": [
    {
      "document_id": "...",
      "revision_id": "...",
      "role": "REFERENCE_DOCUMENT",
      "state": "PENDING_PARSER_OUTPUT",
      "reason_codes": ["PARSER_ARTIFACT_MISSING"]
    }
  ]
}
```

- [ ] **Step 3: Update user messages**

Explain that parser output or drawing confirmation must complete before evaluation. Do not describe pending input as a failed import unless state is `FAILED`.

- [ ] **Step 4: Run tests and commit**

```bash
pytest tests/integration/parsing/test_source_batch_cli.py -v
git add src/ansim_review/cli.py tests/integration/parsing/test_source_batch_cli.py README.md docs/CODEX_WORKFLOW.md
git commit -m "feat: expose generic source readiness states"
```

### Task 9: Mixed-adapter integration and full verification

**Files:**
- Create: `tests/integration/parsing/test_multi_adapter_source_batch.py`
- Create test-only adapter inside the test module.

- [ ] **Step 1: Register a deterministic test adapter**

The adapter kind `TEST_REPORT_JSON` returns one page, one element, one table, and one visual from a minimal JSON fixture.

- [ ] **Step 2: Ingest a mixed batch**

Use one ODL document and one test-adapter document. Assert both appear in the same schema-v2 DB with correct page IDs and retrieval records.

- [ ] **Step 3: Prove duplicate names do not collide**

Both source PDFs may be named `document.pdf` in different directories with different bytes; identities must differ.

- [ ] **Step 4: Run focused suites**

```bash
pytest tests/unit/contracts/test_source_batch.py -v
pytest tests/unit/parsing -v
pytest tests/integration/parsing -v
```

- [ ] **Step 5: Run full quality gate**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

- [ ] **Step 6: Commit verification corrections**

```bash
git add -A
git commit -m "test: verify parser registry and source states"
```

- [ ] **Step 7: PR body**

Use `Progress on #22`; do not close the epic until the namespace/fixture/E2E PR is complete.