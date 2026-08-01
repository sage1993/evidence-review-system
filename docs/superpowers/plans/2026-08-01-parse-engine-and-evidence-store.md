# Parse Engine and Evidence Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a deterministic SQLite evidence snapshot from immutable PDFs, OpenDataLoader output, tables, images, page renders, and coordinate manifests.

**Architecture:** Adapters import parser-owned data, normalize all bboxes into PDF points with bottom-left origin, assign stable IDs, and transactionally load an append-only evidence schema. Grist is synchronized later but is not authoritative for execution.

**Tech Stack:** Python 3.11+, SQLite, hashlib/json/csv, PyMuPDF only in Codex ingestion, existing OpenDataLoader JSON/Markdown.

## Global Constraints

- Never modify `02_source_pdf/` or raw parser records.
- Every evidence element carries document revision, page, element ID, source coordinate system, canonical bbox, and source hash.
- Identical sources and parser output produce identical IDs and snapshot hash.
- LLM anomaly flags are separate records and cannot mutate raw evidence.

---

### Task 1: Source Manifest

**Files:** Create `src/ansim_review/parsing/source_manifest.py`, `schemas/source-manifest.schema.json`; test `tests/unit/parsing/test_source_manifest.py`.

**Interfaces:** `build_source_entry(...) -> SourceEntry`; `verify_source_entry(...) -> list[VerificationError]`.

- [ ] Write a failing test: hash a PDF, modify it, then expect `SOURCE_HASH_MISMATCH`.
- [ ] Run: `pytest tests/unit/test_source_manifest.py -v`.
- [ ] Implement streaming SHA-256, byte size, page count, parser artifact hashes, and revision ID `<document>-<hash12>`.
- [ ] Re-run tests and verify the source directory hash remains unchanged.
- [ ] Commit: `git commit -m "feat: add immutable source manifest"`.

### Task 2: OpenDataLoader Adapter and Stable Element IDs

**Files:** Create `src/ansim_review/parsing/odl_adapter.py`, fixture `tests/golden/fixtures/minimal-parser-output.json`; test `tests/unit/parsing/test_odl_adapter.py`.

**Interfaces:** `load_raw_elements(path, document_id, revision_id) -> tuple[RawElement, ...]`; ID `<doc>-<rev>-P####-E#####`.

- [ ] Write a test asserting stable IDs, page ordering, raw payload hash, type, and parser order.
- [ ] Run and observe missing adapter failure.
- [ ] Implement recursive flattening while preserving original raw JSON fragment/hash and original array position.
- [ ] Run fixture tests twice and compare canonical output bytes.
- [ ] Commit: `git commit -m "feat: import parser elements with stable provenance"`.

### Task 3: Coordinate Normalization

**Files:** Create `src/ansim_review/parsing/pdf_geometry.py`; test `tests/unit/parsing/test_coordinate_normalization.py`.

**Interfaces:** `normalize_bbox(raw_bbox, source_system, page_width, page_height) -> BBox`; canonical `left,bottom,right,top` PDF points.

- [ ] Write a top-left-to-bottom-left test: `(10,20,110,70)` on height 800 becomes `(10,730,110,780)`.
- [ ] Run and observe failure.
- [ ] Implement supported transforms and reject inverted/out-of-page bboxes beyond 0.5-point tolerance.
- [ ] Run unit tests including rotation fixtures.
- [ ] Commit: `git commit -m "feat: normalize pdf evidence coordinates"`.

### Task 4: Visual and Table Manifests

**Files:** Create `src/ansim_review/parsing/visual_manifest.py`; test `tests/unit/parsing/test_visual_manifest.py`.

**Interfaces:** imports unique images, occurrence crops, table crops, composites, and page renders with stable IDs, relative paths, hashes, page, bbox, and source links.

- [ ] Test that identical image bytes on two pages remain two occurrences sharing one duplicate group.
- [ ] Run and observe failure.
- [ ] Implement relative POSIX path validation, SHA-256 verification, stable occurrence IDs, and missing-file reports.
- [ ] Run tests against a copied sample manifest.
- [ ] Commit: `git commit -m "feat: import traceable visual evidence"`.

### Task 5: Evidence SQLite Schema and Transactional Ingest

**Files:** Create `src/ansim_review/evidence/schema.sql`, `src/ansim_review/evidence/store.py`, `src/ansim_review/evidence/ingest.py`; test `tests/integration/evidence/test_evidence_ingest.py`.

**Interfaces:** tables `documents`, `revisions`, `pages`, `elements`, `clauses`, `tables`, `visuals`, `links`, `review_flags`, `snapshot_meta`.

- [ ] Write a failing test proving a duplicate element ID rolls back the entire ingest transaction.
- [ ] Run and observe missing schema failure.
- [ ] Implement foreign keys, unique IDs, separate raw/normalized fields, indexes, and one transaction per snapshot.
- [ ] Run `PRAGMA foreign_key_check`, `integrity_check`, row-count tests, and double-import hash comparison.
- [ ] Commit: `git commit -m "feat: add transactional evidence store"`.

### Task 6: Ansim Workspace Migration Adapter

**Files:** Create `src/ansim_review/parsing/ansim_workspace_adapter.py`, `src/ansim_review/evidence/snapshot.py`; test `tests/integration/parsing/test_ansim_workspace_adapter.py`.

**Interfaces:** `import_ansim_workspace(root, output_db) -> MigrationReport`; `compute_snapshot_hash(store) -> str`.

- [ ] Write a test importing two copies of the same workspace and asserting identical counts and snapshot hash.
- [ ] Run and observe failure.
- [ ] Map `law-1`, `law-2`, clauses, source elements, tables, visuals, and reviewed fields using explicit stable IDs rather than Grist row IDs.
- [ ] Produce `unresolved-links.json` instead of guessing missing links.
- [ ] Commit: `git commit -m "feat: migrate ansim evidence into deterministic snapshot"`.
