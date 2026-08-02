# Legacy Document Lineage Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict, copy-on-write migration that removes only graph-equivalent legacy document aliases from evidence schema v2 while preserving canonical relationships and producing deterministic alias/report artifacts.

**Architecture:** A strict manifest decoder defines human-reviewed document and revision mappings. A read-only planner builds logical graph fingerprints and returns either an applicable plan or sorted unresolved reasons. A copy-on-write applier rewrites only equivalent references in a temporary schema v2 copy, verifies integrity and logical lineage, then atomically publishes the database, alias registry and migration report.

**Tech Stack:** Python 3.11/3.13 standard library, `sqlite3`, dataclasses, canonical JSON helpers, pytest, Ruff, strict mypy, GitHub Actions on Ubuntu and Windows.

## Global Constraints

- Keep evidence schema version exactly `2`; do not add a schema v3 alias table.
- Do not modify the source SQLite database, Grist file, CSV, PDF, parser output or visual assets.
- Require `evidence-review/legacy-lineage-manifest` version `1`; never infer aliases from filenames, paths, prefixes, row order or titles.
- Accept only lowercase 64-character SHA-256 digests.
- Require explicit legacy-to-canonical revision mappings.
- Merge only graph-equivalent records; fuzzy text, geometry tolerance and implicit reviewed-value promotion are forbidden.
- Any unresolved item blocks the entire migration; partial migration is forbidden.
- Write output database, alias registry and migration report with create-only semantics and atomic publication.
- Preserve existing canonical source-batch, visual loader, release and review authorization behavior.
- Grist attachment/comment rows are outside this schema v2 migration and remain preserved by Issue #38 acceptance evidence.

---

## File Structure

- Create `src/ansim_review/evidence/lineage_contract.py`: strict manifest and result dataclasses/codecs.
- Create `src/ansim_review/evidence/lineage_graph.py`: read-only graph loading, logical projections and fingerprint matching.
- Create `src/ansim_review/evidence/lineage_migration.py`: planner, copy-on-write applier, verification and artifact writers.
- Modify `src/ansim_review/contracts/formats.py`: three versioned format constants.
- Modify `src/ansim_review/cli.py`: `evidence migrate-lineage` command and exit codes.
- Create `tests/unit/evidence/test_lineage_contract.py`: strict contract tests.
- Create `tests/unit/evidence/test_lineage_graph.py`: graph equivalence and unresolved tests.
- Create `tests/integration/evidence/test_lineage_migration.py`: successful and blocked migration tests.
- Create `tests/integration/evidence/test_lineage_migration_cli.py`: CLI behavior tests.
- Create `tests/unit/evidence/test_lineage_migration_documentation.py`: documentation boundary tests.
- Create `docs/LEGACY_LINEAGE_MIGRATION.md`: operator workflow and guarantees.
- Create `docs/examples/legacy-lineage-manifest.example.json`: explicit non-authoritative example.
- Modify `README.md`: link and concise command reference.
- Modify `docs/LEGACY_VISUALS.md`: clarify separation between visual inspection and document lineage migration.

---

### Task 1: Strict Lineage Manifest Contract

**Files:**
- Create: `src/ansim_review/evidence/lineage_contract.py`
- Modify: `src/ansim_review/contracts/formats.py`
- Test: `tests/unit/evidence/test_lineage_contract.py`

**Interfaces:**
- Produces: `RevisionMapping`, `DocumentLineageMapping`, `LegacyLineageManifest`, `decode_legacy_lineage_manifest(payload: object) -> LegacyLineageManifest`, `legacy_lineage_manifest_document(manifest: LegacyLineageManifest) -> dict[str, object]`.
- Produces constants: `LEGACY_LINEAGE_MANIFEST_FORMAT`, `LEGACY_LINEAGE_ALIASES_FORMAT`, `LEGACY_LINEAGE_MIGRATION_REPORT_FORMAT`.

- [ ] **Step 1: Write the failing strict-contract tests**

```python
from copy import deepcopy

import pytest

from ansim_review.evidence.lineage_contract import (
    decode_legacy_lineage_manifest,
    legacy_lineage_manifest_document,
)


def valid_payload() -> dict[str, object]:
    return {
        "format": "evidence-review/legacy-lineage-manifest",
        "version": 1,
        "source_database_sha256": "a" * 64,
        "reviewer_id": "ksh",
        "reviewed_at": "2026-08-02T16:49:00+09:00",
        "mappings": [
            {
                "legacy_document_id": "LAW3",
                "canonical_document_id": "DOC-ACFD68E34043268C",
                "source_sha256": "b" * 64,
                "reason": "same immutable PDF registered under a legacy alias",
                "revision_mappings": [
                    {
                        "legacy_revision_id": "REV-LAW3-001",
                        "canonical_revision_id": "REV-DOC-001",
                    }
                ],
            }
        ],
    }


def test_manifest_round_trips_canonically() -> None:
    decoded = decode_legacy_lineage_manifest(valid_payload())
    assert legacy_lineage_manifest_document(decoded) == valid_payload()


def test_unknown_fields_are_rejected() -> None:
    payload = valid_payload()
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        decode_legacy_lineage_manifest(payload)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (("format", "other"), "unsupported format"),
        (("version", 2), "unsupported version"),
        (("source_database_sha256", "A" * 64), "lowercase SHA-256"),
        (("reviewer_id", ""), "reviewer_id"),
        (("reviewed_at", "2026-08-02T16:49:00"), "timezone"),
    ],
)
def test_invalid_top_level_values_are_rejected(mutation, message) -> None:
    payload = valid_payload()
    payload[mutation[0]] = mutation[1]
    with pytest.raises(ValueError, match=message):
        decode_legacy_lineage_manifest(payload)


def test_duplicate_aliases_and_revision_ids_are_rejected() -> None:
    payload = valid_payload()
    duplicate = deepcopy(payload["mappings"][0])
    payload["mappings"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate legacy_document_id"):
        decode_legacy_lineage_manifest(payload)
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```bash
pytest tests/unit/evidence/test_lineage_contract.py -v
```

Expected: collection fails because `ansim_review.evidence.lineage_contract` does not exist.

- [ ] **Step 3: Add format constants**

Append to `src/ansim_review/contracts/formats.py`:

```python
LEGACY_LINEAGE_MANIFEST_FORMAT = "evidence-review/legacy-lineage-manifest"
LEGACY_LINEAGE_ALIASES_FORMAT = "evidence-review/legacy-lineage-aliases"
LEGACY_LINEAGE_MIGRATION_REPORT_FORMAT = (
    "evidence-review/legacy-lineage-migration-report"
)
```

- [ ] **Step 4: Implement immutable dataclasses and strict decoder**

Create `lineage_contract.py` with:

```python
@dataclass(frozen=True, slots=True)
class RevisionMapping:
    legacy_revision_id: str
    canonical_revision_id: str


@dataclass(frozen=True, slots=True)
class DocumentLineageMapping:
    legacy_document_id: str
    canonical_document_id: str
    source_sha256: str
    reason: str
    revision_mappings: tuple[RevisionMapping, ...]


@dataclass(frozen=True, slots=True)
class LegacyLineageManifest:
    source_database_sha256: str
    reviewer_id: str
    reviewed_at: datetime
    mappings: tuple[DocumentLineageMapping, ...]
```

Decoder requirements:

- object and exact-key validation at every level
- timezone-aware `datetime.fromisoformat`
- `_SHA = re.compile(r"^[0-9a-f]{64}$")`
- legacy and canonical IDs validated through existing shared identifier policy
- non-empty mappings and revision mappings
- reject equal legacy/canonical IDs
- reject duplicate legacy document IDs, duplicate legacy revision IDs and duplicate canonical revision IDs
- deterministic tuple ordering by `legacy_document_id`, then revision ID
- encoder returns `reviewed_at.isoformat()` and sorted arrays

- [ ] **Step 5: Run focused tests and static checks**

```bash
pytest tests/unit/evidence/test_lineage_contract.py -v
ruff check src/ansim_review/evidence/lineage_contract.py tests/unit/evidence/test_lineage_contract.py
mypy src/ansim_review/evidence/lineage_contract.py
```

Expected: all pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/ansim_review/contracts/formats.py src/ansim_review/evidence/lineage_contract.py tests/unit/evidence/test_lineage_contract.py
git commit -m "feat: define legacy lineage manifest contract"
```

---

### Task 2: Read-Only Graph Loader and Equivalence Planner

**Files:**
- Create: `src/ansim_review/evidence/lineage_graph.py`
- Test: `tests/unit/evidence/test_lineage_graph.py`

**Interfaces:**
- Consumes: `LegacyLineageManifest`, `DocumentLineageMapping`, `RevisionMapping`.
- Produces: `UnresolvedLineageItem(code: str, legacy_id: str, canonical_id: str, detail: str)`, `EntityMapping(table: str, legacy_id: str, canonical_id: str)`, `LegacyLineagePlan(status: Literal["READY", "BLOCKED"], entity_mappings: tuple[EntityMapping, ...], unresolved: tuple[UnresolvedLineageItem, ...])`.
- Produces: `plan_legacy_lineage_migration(source_database: Path, manifest: LegacyLineageManifest) -> LegacyLineagePlan`.

- [ ] **Step 1: Write graph planner tests using a minimal schema v2 fixture**

Create helpers that initialize `schema.sql` through `EvidenceStore(create=True)` and insert:

- legacy and canonical documents
- revisions with the same source hash, size and page count
- page 1 on both sides with equal geometry
- one equivalent element, clause, table and visual under each graph
- equivalent links, review flags and retrieval records

Core tests:

```python
def test_equivalent_duplicate_graph_builds_ready_plan(tmp_path: Path) -> None:
    database, manifest = build_equivalent_graph(tmp_path)
    plan = plan_legacy_lineage_migration(database, manifest)
    assert plan.status == "READY"
    assert plan.unresolved == ()
    assert {(item.table, item.legacy_id, item.canonical_id) for item in plan.entity_mappings} >= {
        ("documents", "LAW3", "DOC-ACFD68E34043268C"),
        ("revisions", "REV-LAW3-001", "REV-DOC-001"),
        ("pages", "PAGE-LAW3-001", "PAGE-DOC-001"),
    }


def test_payload_difference_blocks_plan(tmp_path: Path) -> None:
    database, manifest = build_equivalent_graph(tmp_path)
    mutate_legacy_element_text(database, "different")
    plan = plan_legacy_lineage_migration(database, manifest)
    assert plan.status == "BLOCKED"
    assert [item.code for item in plan.unresolved] == [
        "EVIDENCE_COUNTERPART_MISSING"
    ]


def test_reviewed_value_conflict_blocks_without_promotion(tmp_path: Path) -> None:
    database, manifest = build_equivalent_graph(tmp_path)
    set_legacy_clause_reviewed(database, normalized_text="human value")
    plan = plan_legacy_lineage_migration(database, manifest)
    assert plan.status == "BLOCKED"
    assert "REVIEWED_VALUE_CONFLICT" in {item.code for item in plan.unresolved}
```

Also test:

- source hash mismatch
- unsupported schema
- unknown table in source database
- revision ownership mismatch
- revision metadata mismatch
- page set and geometry mismatch
- ambiguous duplicate content fingerprints
- missing link/review flag/retrieval counterpart
- deterministic unresolved ordering

- [ ] **Step 2: Run graph tests and confirm RED**

```bash
pytest tests/unit/evidence/test_lineage_graph.py -v
```

Expected: collection fails because `lineage_graph` is absent.

- [ ] **Step 3: Implement read-only source validation**

Required helpers:

```python
def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _require_exact_schema_v2_tables(connection: sqlite3.Connection) -> None:
    expected = {
        "schema_meta", "documents", "revisions", "pages", "elements",
        "clauses", "tables", "visuals", "links", "review_flags",
        "snapshot_meta", "retrieval_records", "evidence_fts",
        "evidence_fts_data", "evidence_fts_idx", "evidence_fts_content",
        "evidence_fts_docsize", "evidence_fts_config", "retrieval_meta",
    }
```

Permit SQLite internal tables required by FTS only. Any other user table yields `SOURCE_SCHEMA_VERSION_UNSUPPORTED` because version 1 cannot claim preservation.

Run integrity and foreign-key checks before loading graph rows.

- [ ] **Step 4: Implement canonical logical projections**

Use `dump_bytes` and SHA-256 for projections.

Projection examples:

```python
def _element_payload(row: sqlite3.Row) -> dict[str, object]:
    return {
        "element_type": row["element_type"],
        "raw_json": json.loads(row["raw_json"]),
        "raw_text": row["raw_text"],
        "normalized_text": row["normalized_text"],
        "raw_payload_hash": row["raw_payload_hash"],
        "bbox_json": None if row["bbox_json"] is None else json.loads(row["bbox_json"]),
        "parser_order": row["parser_order"],
    }
```

Implement equivalent payload functions for clauses, tables, visuals, links, review flags and retrieval records. Parent IDs are excluded from the payload fingerprint and validated separately through explicit parent mappings.

- [ ] **Step 5: Implement deterministic one-to-one matching**

For each mapped parent:

1. group legacy and canonical rows by payload fingerprint
2. require exactly one row on each side for a fingerprint
3. produce `EntityMapping`
4. zero counterpart → missing
5. more than one candidate → ambiguous
6. unmatched canonical rows are allowed only if they are independent canonical evidence; unmatched legacy rows always block

For clauses, check review status and normalized text before generic fingerprint matching so a reviewed/automatic difference returns `REVIEWED_VALUE_CONFLICT`.

- [ ] **Step 6: Implement links, flags and retrieval verification**

Build a complete `legacy_id -> canonical_id` dictionary from matched rows. Project auxiliary rows after substituting mapped endpoint/evidence IDs. Missing or ambiguous counterparts return the table-specific stable reason code.

- [ ] **Step 7: Run focused and full unit checks**

```bash
pytest tests/unit/evidence/test_lineage_graph.py tests/unit/evidence/test_lineage_contract.py -v
ruff check src/ansim_review/evidence/lineage_graph.py tests/unit/evidence/test_lineage_graph.py
mypy src/ansim_review/evidence/lineage_graph.py
```

Expected: all pass.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/ansim_review/evidence/lineage_graph.py tests/unit/evidence/test_lineage_graph.py
git commit -m "feat: plan safe legacy lineage graph merges"
```

---

### Task 3: Copy-on-Write Migration and Deterministic Artifacts

**Files:**
- Create: `src/ansim_review/evidence/lineage_migration.py`
- Test: `tests/integration/evidence/test_lineage_migration.py`

**Interfaces:**
- Consumes: `decode_legacy_lineage_manifest`, `plan_legacy_lineage_migration`.
- Produces: `LegacyLineageMigrationResult(output_database: Path, aliases_path: Path, report_path: Path, output_sha256: str, logical_lineage_digest: str, removed_counts: Mapping[str, int])`.
- Produces: `apply_legacy_lineage_migration(source_database: Path, manifest_path: Path, output_database: Path) -> LegacyLineageMigrationResult`.

- [ ] **Step 1: Write successful integration test**

```python
def test_copy_on_write_migration_removes_only_equivalent_legacy_graph(
    tmp_path: Path,
) -> None:
    source, manifest_path = write_equivalent_source_and_manifest(tmp_path)
    source_before = source.read_bytes()
    output = tmp_path / "migrated" / "evidence.sqlite"

    result = apply_legacy_lineage_migration(source, manifest_path, output)

    assert source.read_bytes() == source_before
    assert result.output_database == output.resolve()
    with sqlite3.connect(output) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT id FROM documents ORDER BY id"
        ).fetchall() == [("DOC-ACFD68E34043268C",)]
        assert connection.execute(
            "SELECT document_id FROM retrieval_records"
        ).fetchall() == [("DOC-ACFD68E34043268C",)]
```

- [ ] **Step 2: Write failure and rollback tests**

Test:

- blocked plan creates no output, alias or report
- existing output returns `FileExistsError`
- source equals output rejected
- existing temporary path preserved and blocks execution
- source modified after planning returns `SOURCE_CHANGED_DURING_MIGRATION`
- simulated exception during transaction removes generated temporary files
- two isolated runs produce equal logical lineage digest and canonical JSON artifacts

- [ ] **Step 3: Run integration tests and confirm RED**

```bash
pytest tests/integration/evidence/test_lineage_migration.py -v
```

Expected: collection fails because `lineage_migration` is absent.

- [ ] **Step 4: Implement create-only path preparation**

Use distinct paths:

```python
aliases_path = output.with_name(f"{output.name}.legacy-lineage-aliases.json")
report_path = output.with_name(f"{output.name}.legacy-lineage-migration-report.json")
temporary_output = output.with_name(f".{output.name}.lineage.tmp")
temporary_aliases = aliases_path.with_name(f".{aliases_path.name}.tmp")
temporary_report = report_path.with_name(f".{report_path.name}.tmp")
```

Reject any existing final or temporary path. Use `shutil.copyfile` only after the plan is `READY`.

- [ ] **Step 5: Apply mappings transactionally**

Open the temporary database with foreign keys enabled and `BEGIN IMMEDIATE`.

Use the plan mapping dictionary to verify counterpart rows still exist. Delete equivalent legacy auxiliary and evidence rows child-to-parent. Do not mutate canonical row payloads.

Required deletion order:

```text
retrieval_records
links
review_flags
elements
tables
visuals
clauses
pages
revisions
documents
```

For links and flags, delete only legacy duplicate rows already mapped to an existing canonical equivalent.

- [ ] **Step 6: Rebuild and verify retrieval state**

After deletion:

- remove and rebuild FTS records through existing retrieval index helper
- update `snapshot_meta.database_snapshot_hash` using existing snapshot helper
- run integrity and foreign-key checks
- verify every legacy document/revision/page/entity ID from the plan is absent
- verify every canonical counterpart remains
- verify before/after canonical graph counts equal after subtracting removed duplicates

- [ ] **Step 7: Implement deterministic alias registry**

Registry entries are sorted by legacy document ID and revision ID and contain only manifest-reviewed values plus the final migration report hash. To avoid a hash cycle, build the report body without `aliases_sha256`, hash it, then build aliases with `migration_report_body_sha256`; finally build the report with `aliases_sha256` and a separate `report_sha256` over the final report document excluding its own hash field.

Do not generate current timestamps.

- [ ] **Step 8: Implement migration report**

Report includes:

```python
{
    "format": LEGACY_LINEAGE_MIGRATION_REPORT_FORMAT,
    "version": 1,
    "status": "MIGRATED",
    "source_database": {"file": source.name, "sha256": source_hash},
    "output_database": {"file": output.name, "sha256": output_hash},
    "manifest_sha256": manifest_hash,
    "reviewer_id": manifest.reviewer_id,
    "reviewed_at": manifest.reviewed_at.isoformat(),
    "logical_lineage_digest": logical_digest,
    "removed_counts": dict(sorted(removed_counts.items())),
    "preserved_counts": dict(sorted(preserved_counts.items())),
    "removed_legacy_ids": sorted(removed_ids),
    "preserved_canonical_ids": sorted(canonical_ids),
    "integrity_check": "ok",
    "foreign_key_violations": 0,
    "unresolved": [],
}
```

- [ ] **Step 9: Atomically publish all outputs**

Write JSON temporary files with `os.open(..., O_CREAT | O_EXCL)`, fsync, then replace final paths only after all verification succeeds. On any exception remove only paths created by this execution.

Re-hash source immediately before publication and fail if changed.

- [ ] **Step 10: Run integration and regression tests**

```bash
pytest tests/integration/evidence/test_lineage_migration.py -v
pytest tests/integration/evidence tests/unit/evidence -v
ruff check src tests
mypy src
```

Expected: all pass.

- [ ] **Step 11: Commit Task 3**

```bash
git add src/ansim_review/evidence/lineage_migration.py tests/integration/evidence/test_lineage_migration.py
git commit -m "feat: apply copy-on-write lineage migration"
```

---

### Task 4: CLI Contract

**Files:**
- Modify: `src/ansim_review/cli.py`
- Test: `tests/integration/evidence/test_lineage_migration_cli.py`

**Interfaces:**
- Consumes: `apply_legacy_lineage_migration`.
- Produces command: `evidence-review evidence migrate-lineage --source PATH --manifest PATH --output PATH`.

- [ ] **Step 1: Write CLI RED tests**

```python
def test_migrate_lineage_cli_outputs_canonical_status(tmp_path: Path) -> None:
    source, manifest = write_equivalent_source_and_manifest(tmp_path)
    output = tmp_path / "out" / "evidence.sqlite"
    completed = run_cli(
        "evidence", "migrate-lineage",
        "--source", str(source),
        "--manifest", str(manifest),
        "--output", str(output),
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["format"] == "evidence-review/legacy-lineage-migration-status"
    assert payload["status"] == "MIGRATED"
    assert payload["output_database"] == str(output.resolve())


def test_migrate_lineage_cli_uses_declared_exit_codes(tmp_path: Path) -> None:
    source, manifest = write_equivalent_source_and_manifest(tmp_path)
    output = tmp_path / "existing.sqlite"
    output.write_bytes(b"existing")
    assert run_cli(...).returncode == 1
    corrupt_manifest_hash(manifest)
    assert run_cli(..., output=tmp_path / "other.sqlite").returncode == 2
```

Also test `--help` includes all three required arguments.

- [ ] **Step 2: Run CLI tests and confirm RED**

```bash
pytest tests/integration/evidence/test_lineage_migration_cli.py -v
```

Expected: argparse rejects `migrate-lineage`.

- [ ] **Step 3: Add parser and handler**

Add to the existing `evidence` subparser:

```python
lineage = evidence_stages.add_parser(
    "migrate-lineage",
    help="copy equivalent legacy document aliases into one canonical lineage",
)
lineage.add_argument("--source", required=True, type=Path)
lineage.add_argument("--manifest", required=True, type=Path)
lineage.add_argument("--output", required=True, type=Path)
```

Handler:

```python
def _evidence_migrate_lineage(source: Path, manifest: Path, output: Path) -> int:
    try:
        result = apply_legacy_lineage_migration(source, manifest, output)
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError, json.JSONDecodeError, sqlite3.Error, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout({
        "format": "evidence-review/legacy-lineage-migration-status",
        "version": 1,
        "status": "MIGRATED",
        "output_database": str(result.output_database),
        "aliases": str(result.aliases_path),
        "report": str(result.report_path),
        "output_sha256": result.output_sha256,
        "logical_lineage_digest": result.logical_lineage_digest,
    })
    return 0
```

Route it before generic unreachable state.

- [ ] **Step 4: Run CLI and full static checks**

```bash
pytest tests/integration/evidence/test_lineage_migration_cli.py -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

Expected: all pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/ansim_review/cli.py tests/integration/evidence/test_lineage_migration_cli.py
git commit -m "feat: add legacy lineage migration CLI"
```

---

### Task 5: Documentation and Normal-Path Isolation

**Files:**
- Create: `docs/LEGACY_LINEAGE_MIGRATION.md`
- Create: `docs/examples/legacy-lineage-manifest.example.json`
- Modify: `docs/LEGACY_VISUALS.md`
- Modify: `README.md`
- Test: `tests/unit/evidence/test_lineage_migration_documentation.py`

**Interfaces:**
- Documents the exact command, guarantees, non-guarantees, exit codes and Issue #38 preservation boundary.
- Proves source-batch and visual normal paths do not import lineage alias code.

- [ ] **Step 1: Write documentation and isolation RED tests**

```python
def test_lineage_docs_are_explicit_and_fail_closed() -> None:
    text = Path("docs/LEGACY_LINEAGE_MIGRATION.md").read_text(encoding="utf-8")
    for token in (
        "copy-on-write",
        "evidence-review/legacy-lineage-manifest",
        "LAW3",
        "DOC-ACFD68E34043268C",
        "source SHA-256",
        "BLOCKED",
        "schema version 2",
        "does not cryptographically verify reviewer identity",
        "evidence migrate-lineage",
    ):
        assert token in text


def test_example_cannot_be_mistaken_for_real_authority() -> None:
    text = Path("docs/examples/legacy-lineage-manifest.example.json").read_text(
        encoding="utf-8"
    )
    assert "EXAMPLE_ONLY_NOT_REVIEWED" in text


def test_normal_paths_do_not_consume_alias_registry() -> None:
    importer = Path("src/ansim_review/parsing/source_batch_importer.py").read_text()
    visual = Path("src/ansim_review/parsing/visual_manifest.py").read_text()
    assert "legacy-lineage-aliases" not in importer
    assert "legacy-lineage-aliases" not in visual
```

- [ ] **Step 2: Run documentation tests and confirm RED**

```bash
pytest tests/unit/evidence/test_lineage_migration_documentation.py -v
```

Expected: missing documentation files fail.

- [ ] **Step 3: Write operator documentation**

`docs/LEGACY_LINEAGE_MIGRATION.md` must include:

1. prerequisite source DB hash and schema v2 checks
2. manifest preparation and human review
3. dry planning occurs inside the command before copy
4. exact PowerShell command
5. output files and create-only behavior
6. stable failure reasons
7. verification commands using SQLite integrity and CLI status
8. source immutability verification
9. reviewed-value conflict behavior
10. Grist attachment/comment preservation boundary from #38
11. non-cryptographic reviewer assurance statement
12. rollback and retry procedure using a new empty output path

- [ ] **Step 4: Add explicit example manifest**

Use valid syntax but unmistakable placeholders:

```json
{
  "format": "evidence-review/legacy-lineage-manifest",
  "version": 1,
  "source_database_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "reviewer_id": "EXAMPLE_ONLY_NOT_REVIEWED",
  "reviewed_at": "2026-08-02T16:49:00+09:00",
  "mappings": []
}
```

The decoder rejects empty mappings; the example is intentionally a template, not executable acceptance evidence. State that immediately above or below the JSON in the documentation.

- [ ] **Step 5: Update README and legacy visual boundary**

README links to the operator guide and gives only the command synopsis. `LEGACY_VISUALS.md` states that visual inspection does not create lineage mappings and that document migration does not canonicalize legacy visual CSV.

- [ ] **Step 6: Run documentation and complete test suite**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

Expected: all pass.

- [ ] **Step 7: Commit Task 5**

```bash
git add README.md docs/LEGACY_LINEAGE_MIGRATION.md docs/examples/legacy-lineage-manifest.example.json docs/LEGACY_VISUALS.md tests/unit/evidence/test_lineage_migration_documentation.py
git commit -m "docs: add legacy lineage migration workflow"
```

---

### Task 6: Wheel, Cross-Platform and PR Verification

**Files:**
- Modify only if a packaging regression is discovered: `pyproject.toml` or CI files.
- Test: all existing test suites and GitHub Actions.

**Interfaces:**
- Produces final verification evidence for Issue #46 and PR review.

- [ ] **Step 1: Run full local-equivalent validation**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
python -m build --wheel
```

Expected: all pass and wheel builds.

- [ ] **Step 2: Verify installed wheel CLI**

Create an isolated environment, install the wheel, then run:

```bash
evidence-review evidence migrate-lineage --help
python -m evidence_review evidence migrate-lineage --help
```

Expected: both show `--source`, `--manifest` and `--output`.

- [ ] **Step 3: Verify no unplanned scope expansion**

Review diff and require:

- no schema version change
- no Grist mutation
- no source-batch alias lookup
- no visual identity inference
- no release attestation changes
- no external dependencies

- [ ] **Step 4: Open draft PR and wait for all GitHub Actions jobs**

PR title:

```text
feat: migrate explicit legacy document lineage aliases
```

PR body includes RED runs, final GREEN run, exact HEAD SHA, test count, Windows/Ubuntu jobs, Python 3.11/3.13 wheel results, and `Refs #46`.

- [ ] **Step 5: Mark PR ready only after exact-head GREEN**

Required jobs:

- validate
- wheel-python313
- Workspace validator Ubuntu
- Workspace validator Windows

- [ ] **Step 6: Record completion evidence**

Comment on Issue #46 and parent Issue #27 with:

- PR URL
- exact HEAD
- final Actions run ID
- migration boundary
- automated test evidence
- statement that no real `LAW3` production migration has been executed unless a real reviewed manifest and source DB were supplied

---

## Plan Self-Review

### Spec coverage

- strict manifest: Task 1
- read-only graph verification and fail-closed unresolved state: Task 2
- copy-on-write schema v2 migration and atomic outputs: Task 3
- deterministic CLI: Task 4
- documentation, Grist boundary and normal-path isolation: Task 5
- full wheel and cross-platform verification: Task 6

### Placeholder scan

The plan contains no `TBD`, `TODO`, deferred implementation statement or unspecified error-handling step. The example's placeholder reviewer ID is deliberately invalid acceptance evidence and explicitly documented as such.

### Type consistency

- `LegacyLineageManifest` is produced in Task 1 and consumed by Task 2.
- `LegacyLineagePlan` is produced in Task 2 and consumed by Task 3.
- `LegacyLineageMigrationResult` is produced in Task 3 and consumed by Task 4.
- All path arguments use `pathlib.Path` and all external documents use canonical JSON dictionaries.
