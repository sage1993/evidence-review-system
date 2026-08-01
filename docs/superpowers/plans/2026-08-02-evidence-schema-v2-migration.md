# Evidence Schema v2 and Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `pages.id` the authoritative page identity, reject invalid bbox data, and migrate existing v1 evidence databases to schema v2 without modifying the source database.

**Architecture:** Introduce explicit schema-version detection, a v2 schema in which all page-bearing evidence references `page_id`, shared page/bbox validation, and a copy-on-write migrator. Retrieval metadata is rebuilt from joins through `pages`, `revisions`, and `documents` rather than trusting duplicated ingest values.

**Tech Stack:** Python 3.11 standard library, SQLite STRICT tables, FTS5, dataclasses, pathlib, canonical JSON, pytest.

## Global Constraints

- Runtime dependencies remain empty.
- `pages.id` is the only authoritative page identity for elements, tables, and visuals.
- Existing v1 database bytes must remain unchanged.
- Migration must be copy-on-write and atomic.
- A failed migration must not leave the requested output database.
- Bbox validation occurs before insertion and migration copy.
- Same logical evidence snapshot before and after migration must produce the same logical snapshot hash.
- New databases are created directly as schema v2.

---

## File Map

### Create

- `src/ansim_review/evidence/schema_version.py`: schema constants, detection, and open policy.
- `src/ansim_review/evidence/page_geometry.py`: page lookup and bbox validation.
- `src/ansim_review/evidence/migrations/__init__.py`: migration package marker.
- `src/ansim_review/evidence/migrations/v1_to_v2.py`: copy-on-write migration.
- `tests/fixtures/evidence/schema_v1.sql`: frozen v1 schema fixture.
- `tests/unit/evidence/test_schema_version.py`: version-detection tests.
- `tests/unit/evidence/test_page_geometry.py`: bbox/page validation tests.
- `tests/integration/evidence/test_v1_to_v2_migration.py`: migration and rollback tests.

### Modify

- `src/ansim_review/evidence/schema.sql`: canonical v2 schema.
- `src/ansim_review/evidence/store.py`: version-aware creation/open behavior.
- `src/ansim_review/evidence/ingest.py`: page-only evidence insertion and pre-insert validation.
- `src/ansim_review/evidence/snapshot.py`: logical snapshot hashing independent of physical v1/v2 columns.
- `src/ansim_review/retrieval/index.py`: build retrieval records through page joins.
- `src/ansim_review/parsing/source_batch_importer.py`: emit v2 element records without duplicate page metadata.
- `src/ansim_review/cli.py`: add `evidence migrate` command.
- `tests/unit/evidence/test_ingest.py`: invalid relationship and bbox tests.
- `tests/integration/retrieval/test_index.py`: citation projection equivalence.
- `tests/integration/parsing/test_source_batch_cli.py`: direct v2 creation assertion.
- `README.md`: schema migration command and failure behavior.

## Public Interfaces

```python
SCHEMA_VERSION = 2

class SchemaUpgradeRequired(RuntimeError): ...
class UnsupportedSchemaVersion(RuntimeError): ...


def detect_schema_version(connection: sqlite3.Connection) -> int:
    ...


def validate_bbox_within_page(
    bbox: BBox | None,
    *,
    page_width: float,
    page_height: float,
    tolerance: float = 1e-6,
) -> None:
    ...


def migrate_v1_to_v2(source: Path, output: Path) -> MigrationReport:
    ...
```

`MigrationReport` fields:

```python
@dataclass(frozen=True, slots=True)
class MigrationReport:
    source_path: Path
    output_path: Path
    source_sha256: str
    output_sha256: str
    source_schema_version: int
    output_schema_version: int
    logical_snapshot_hash_before: str
    logical_snapshot_hash_after: str
    row_counts: dict[str, int]
```

---

### Task 1: Freeze schema v1 and detect database versions

**Files:**
- Create: `tests/fixtures/evidence/schema_v1.sql`
- Create: `src/ansim_review/evidence/schema_version.py`
- Create: `tests/unit/evidence/test_schema_version.py`

**Interfaces:**
- Produces: `detect_schema_version(connection) -> int`
- Produces: `require_current_schema(connection) -> None`

- [ ] **Step 1: Save the current schema as the immutable v1 test fixture**

Copy the pre-change `schema.sql` exactly into `tests/fixtures/evidence/schema_v1.sql`. Do not add `schema_meta` to this fixture.

- [ ] **Step 2: Write failing version-detection tests**

```python
def test_missing_schema_meta_with_exact_v1_shape_is_version_one(tmp_path: Path) -> None:
    connection = create_v1_database(tmp_path / "v1.sqlite")
    assert detect_schema_version(connection) == 1


def test_schema_meta_reports_version_two(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "v2.sqlite")
    connection.executescript("CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;")
    connection.execute("INSERT INTO schema_meta VALUES('schema_version', '2')")
    assert detect_schema_version(connection) == 2


def test_unknown_legacy_shape_is_rejected(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "unknown.sqlite")
    connection.execute("CREATE TABLE documents(id TEXT PRIMARY KEY)")
    with pytest.raises(UnsupportedSchemaVersion):
        detect_schema_version(connection)
```

- [ ] **Step 3: Run focused tests**

Run: `pytest tests/unit/evidence/test_schema_version.py -v`

Expected: FAIL because `schema_version.py` does not exist.

- [ ] **Step 4: Implement exact-shape detection**

For v1 inference, require all expected v1 tables and the exact page-bearing columns:

```python
_V1_COLUMNS = {
    "pages": ("id", "revision_id", "page_number", "width", "height"),
    "elements": ("id", "revision_id", "page_id", "page_number", ...),
    "tables": ("id", "revision_id", "page_number", ...),
    "visuals": ("id", "revision_id", "page_number", ...),
}
```

Do not infer v1 from table names alone.

- [ ] **Step 5: Run focused tests and commit**

```bash
pytest tests/unit/evidence/test_schema_version.py -v
git add tests/fixtures/evidence/schema_v1.sql src/ansim_review/evidence/schema_version.py tests/unit/evidence/test_schema_version.py
git commit -m "test: freeze evidence schema v1"
```

### Task 2: Define schema v2 and version-aware store opening

**Files:**
- Modify: `src/ansim_review/evidence/schema.sql`
- Modify: `src/ansim_review/evidence/store.py`
- Modify: `tests/unit/evidence/test_store.py`

**Interfaces:**
- `EvidenceStore(path, *, create: bool = False)` creates only when explicitly requested.
- Opening v1 raises `SchemaUpgradeRequired`.
- Opening a newer or unknown schema raises `UnsupportedSchemaVersion`.

- [ ] **Step 1: Write failing store tests**

Cover:

```text
new path + create=False       -> FileNotFoundError
new path + create=True        -> schema v2 database
existing v1                   -> SchemaUpgradeRequired
existing v2                   -> opens
schema version 99             -> UnsupportedSchemaVersion
```

- [ ] **Step 2: Run focused tests and confirm current auto-mutation behavior fails the tests**

Run: `pytest tests/unit/evidence/test_store.py -v`

- [ ] **Step 3: Replace page-bearing tables in `schema.sql`**

Required columns:

```sql
CREATE TABLE schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
INSERT INTO schema_meta(key, value) VALUES('schema_version', '2');

CREATE TABLE elements (
    id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES pages(id),
    element_type TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    raw_text TEXT,
    normalized_text TEXT,
    raw_payload_hash TEXT NOT NULL CHECK(length(raw_payload_hash) = 64),
    bbox_json TEXT,
    parser_order INTEGER NOT NULL CHECK(parser_order >= 0)
) STRICT;
```

Apply the same `page_id` rule to `tables` and `visuals`. Add `page_id` to `retrieval_records`.

- [ ] **Step 4: Implement explicit create/open behavior**

Use SQLite URI read-only mode for existing DB inspection where appropriate:

```python
sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
```

Do not execute `schema.sql` against an existing database.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/unit/evidence/test_store.py tests/unit/evidence/test_schema_version.py -v
git add src/ansim_review/evidence/schema.sql src/ansim_review/evidence/store.py tests/unit/evidence/test_store.py
git commit -m "feat: add evidence schema v2 open policy"
```

### Task 3: Add shared page and bbox validation

**Files:**
- Create: `src/ansim_review/evidence/page_geometry.py`
- Create: `tests/unit/evidence/test_page_geometry.py`

**Interfaces:**
- Produces: `validate_bbox_within_page(...) -> None`
- Produces: `load_page_geometry(connection, page_id) -> PageGeometry`

- [ ] **Step 1: Write parameterized failing tests**

Reject:

```python
@pytest.mark.parametrize("bbox", [
    BBox(-0.1, 0, 10, 10),
    BBox(0, 0, 100.1, 10),
    BBox(20, 0, 10, 10),
    BBox(0, 20, 10, 10),
])
def test_bbox_outside_page_is_rejected(bbox: BBox) -> None: ...
```

Also reject NaN and infinity constructed through raw values. Accept `[0, 0, width, height]` exactly.

- [ ] **Step 2: Confirm failure**

Run: `pytest tests/unit/evidence/test_page_geometry.py -v`

- [ ] **Step 3: Implement finite and range checks**

Use `math.isfinite()` on all values. Raise `ValueError("BBOX_OUT_OF_PAGE")` for range violations and `ValueError("PAGE_REFERENCE_NOT_FOUND")` for missing pages.

- [ ] **Step 4: Run tests and commit**

```bash
pytest tests/unit/evidence/test_page_geometry.py -v
git add src/ansim_review/evidence/page_geometry.py tests/unit/evidence/test_page_geometry.py
git commit -m "feat: validate evidence page geometry"
```

### Task 4: Convert ingest and source-batch records to page-only identity

**Files:**
- Modify: `src/ansim_review/evidence/ingest.py`
- Modify: `src/ansim_review/parsing/source_batch_importer.py`
- Modify: `tests/unit/evidence/test_ingest.py`
- Modify: `tests/unit/parsing/test_source_batch_importer.py`

**Interfaces:**
- `EvidenceSnapshot.elements`, `.tables`, and `.visuals` carry `page_id` and no duplicated revision/page fields.

- [ ] **Step 1: Add failing relationship tests**

Assert ingest rejects:

```text
unknown page_id
element bbox beyond referenced page
table page_id from absent page
visual page_id from absent page
```

- [ ] **Step 2: Run tests and confirm failures**

- [ ] **Step 3: Resolve page geometry before every page-bearing insert**

For each row:

```python
page = load_page_geometry(connection, record["page_id"])
validate_bbox_within_page(record.get("bbox"), page_width=page.width, page_height=page.height)
```

- [ ] **Step 4: Remove duplicate fields from generic importer output**

Element records become:

```python
{
    "id": element.element_id,
    "page_id": f"{source.revision_id}-P{element.page_number:04d}",
    "element_type": element.element_type,
    ...
}
```

- [ ] **Step 5: Run focused tests and commit**

```bash
pytest tests/unit/evidence/test_ingest.py tests/unit/parsing/test_source_batch_importer.py -v
git add src/ansim_review/evidence/ingest.py src/ansim_review/parsing/source_batch_importer.py tests/unit/evidence/test_ingest.py tests/unit/parsing/test_source_batch_importer.py
git commit -m "refactor: derive evidence page metadata from page id"
```

### Task 5: Rebuild retrieval projections from joins

**Files:**
- Modify: `src/ansim_review/retrieval/index.py`
- Modify: `src/ansim_review/evidence/snapshot.py`
- Modify: `tests/integration/retrieval/test_index.py`
- Modify: `tests/unit/evidence/test_snapshot.py`

**Interfaces:**
- `build_fts_index(connection)` inserts `page_id`, revision, page number, dimensions, document ID, and source hash using joins.
- `compute_logical_snapshot_hash(connection) -> str` is stable across v1 and v2 physical layouts.

- [ ] **Step 1: Write failing projection tests**

Insert an element with only `page_id`, build the index, and assert the retrieval record contains the page's revision and number. Add a tampered test fixture proving no caller-supplied page number is available to trust.

- [ ] **Step 2: Write logical-hash equivalence test**

Create equivalent v1 and v2 databases and assert:

```python
assert compute_logical_snapshot_hash(v1) == compute_logical_snapshot_hash(v2)
```

- [ ] **Step 3: Run tests and confirm failure**

- [ ] **Step 4: Implement join-based projection**

The element query must join:

```sql
FROM elements e
JOIN pages p ON p.id = e.page_id
JOIN revisions r ON r.id = p.revision_id
JOIN documents d ON d.id = r.document_id
```

Use equivalent queries for tables and visuals.

- [ ] **Step 5: Implement logical snapshot serialization**

Serialize canonical rows with derived page metadata so physical duplicate-column differences do not affect the hash.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/integration/retrieval/test_index.py tests/unit/evidence/test_snapshot.py -v
git add src/ansim_review/retrieval/index.py src/ansim_review/evidence/snapshot.py tests/integration/retrieval/test_index.py tests/unit/evidence/test_snapshot.py
git commit -m "fix: build citations from authoritative page joins"
```

### Task 6: Implement copy-on-write v1-to-v2 migration

**Files:**
- Create: `src/ansim_review/evidence/migrations/__init__.py`
- Create: `src/ansim_review/evidence/migrations/v1_to_v2.py`
- Create: `tests/integration/evidence/test_v1_to_v2_migration.py`

**Interfaces:**
- Produces: `migrate_v1_to_v2(source: Path, output: Path) -> MigrationReport`

- [ ] **Step 1: Build a valid v1 fixture in the integration test**

Include one document, revision, page, element, table, visual, retrieval row, and FTS row.

- [ ] **Step 2: Add failing migration tests**

Cover:

```text
valid v1 -> v2
source bytes unchanged
output already exists -> fail
mismatched element page_id -> fail
missing table page -> fail
out-of-page visual bbox -> fail
failed migration -> no final output
logical hash before == after
```

- [ ] **Step 3: Run tests and confirm import failure**

- [ ] **Step 4: Implement temporary-file migration**

Use:

```python
temporary = output.with_name(f".{output.name}.tmp")
```

Remove stale temporary files only after verifying they are ordinary files beside the requested output. Create v2 with `EvidenceStore(temporary, create=True)`.

- [ ] **Step 5: Resolve v1 page relationships strictly**

For elements, require both conditions:

```text
old page_id exists
old page_id resolves to old revision_id + old page_number
```

For tables and visuals, resolve exactly one page by `(revision_id, page_number)`.

- [ ] **Step 6: Validate and rebuild**

Run:

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

Rebuild retrieval records and FTS from v2 joins. Compare logical hashes, write canonical report JSON, close DBs, then call `temporary.replace(output)`.

- [ ] **Step 7: Run tests and commit**

```bash
pytest tests/integration/evidence/test_v1_to_v2_migration.py -v
git add src/ansim_review/evidence/migrations tests/integration/evidence/test_v1_to_v2_migration.py
git commit -m "feat: migrate evidence databases to schema v2"
```

### Task 7: Add migration CLI and documentation

**Files:**
- Modify: `src/ansim_review/cli.py`
- Modify: `README.md`
- Create: `tests/integration/evidence/test_migration_cli.py`

**Interfaces:**

```powershell
evidence-review evidence migrate --source old.sqlite --output evidence.sqlite
```

- [ ] **Step 1: Write failing CLI tests**

Assert successful canonical status output and distinct exit codes:

```text
0 success
1 output exists
2 invalid or unmigratable input
```

- [ ] **Step 2: Add the `evidence migrate` parser and handler**

Output format:

```json
{
  "format": "evidence-review/evidence-migration-status",
  "version": 1,
  "status": "MIGRATED",
  "source_schema_version": 1,
  "output_schema_version": 2,
  "logical_snapshot_hash": "..."
}
```

- [ ] **Step 3: Document backup and failure semantics**

State explicitly that the source DB is read-only and unchanged.

- [ ] **Step 4: Run focused tests and commit**

```bash
pytest tests/integration/evidence/test_migration_cli.py -v
git add src/ansim_review/cli.py README.md tests/integration/evidence/test_migration_cli.py
git commit -m "docs: add evidence schema migration workflow"
```

### Task 8: Full verification and issue closure

- [ ] **Step 1: Run focused suites**

```bash
pytest tests/unit/evidence -v
pytest tests/integration/evidence -v
pytest tests/integration/retrieval -v
pytest tests/unit/parsing/test_source_batch_importer.py -v
```

- [ ] **Step 2: Run the full quality gate**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

- [ ] **Step 3: Inspect a migrated DB manually**

Run:

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;
SELECT e.id, e.page_id, p.revision_id, p.page_number
FROM elements e JOIN pages p ON p.id = e.page_id;
```

Confirm no `revision_id` or `page_number` column remains in `elements`, `tables`, or `visuals`.

- [ ] **Step 4: Commit verification corrections**

```bash
git add -A
git commit -m "test: verify evidence schema v2 migration"
```

- [ ] **Step 5: PR body**

Use `Closes #19` only after all gates pass.