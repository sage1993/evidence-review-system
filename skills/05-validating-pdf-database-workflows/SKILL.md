---
name: validating-pdf-database-workflows
description: Use when deciding whether a PDF-to-database build is complete, diagnosing broken Grist images or references, checking source traceability, or verifying incremental rebuilds.
---

# Validating PDF Database Workflows

## Overview

Validate the entire chain from immutable PDF through parser output, cleaned records, visual files, CSV exports, and Grist display behavior.

**Core principle:** automated integrity is necessary, but visible Grist behavior and source comparison are also required.

## Automated Validation

A validation script must check at least:

```text
Source PDF existence and SHA-256
Source page count vs parser page count
Required tables and columns
Duplicate stable IDs
Reference integrity
Attachment integrity
Manifest paths and file existence
Image SHA-256 values
CSV row counts vs database row counts
SQLite PRAGMA integrity_check
Grist Reference helper metadata
Preservation of reviewed fields after rebuild
```

Minimum SQL check:

```sql
PRAGMA integrity_check;
```

Expected result:

```text
ok
```

## Grist Desktop Screen Validation

Open the final `.grist` file and confirm:

1. `Visuals.Image` shows actual thumbnails.
2. `ExtractedTables.TableImage` shows table crops.
3. Reference columns show document names or stable clause IDs.
4. No cell displays raw values such as `["L", 3]`.
5. No `Invalid column ...` notification appears.
6. Crops match the source PDF page and region.
7. At least 10 records or 5% of each visual/table type are manually sampled.

A database cannot be marked complete when only SQLite checks pass.

## Diagnostic Matrix

| Symptom | Primary check | Likely repair |
|---|---|---|
| Pink image cells | Attachment cell JSON and internal file tables | Convert typed lists and repair attachment records |
| Blank Reference values | Target row IDs, `visibleCol`, `displayCol` | Restore helper formula metadata |
| Wrong clause linked to image | Page range, bbox overlap, heading boundaries | Re-run spatial/structural linking |
| Crop is inverted or shifted | Coordinate convention and page rotation | Correct bbox transform |
| Table lost merged cells | RowsJSON/HTML availability | Rebuild from structure and crop |
| Reviewed values disappeared | Stable-ID merge log | Restore backup and fix incremental merge |
| Parser page count differs | Parser failure or encrypted pages | Reparse affected document before continuing |

## Acceptance Criteria

All items must pass:

- [ ] Source PDFs and parser outputs remain unchanged.
- [ ] Documents, clauses, source elements, tables, and visuals exist.
- [ ] Every clause and visual has document/page provenance.
- [ ] Composite and vector diagrams have rendered crops when needed.
- [ ] Duplicate images are identified by SHA-256.
- [ ] Reference and Attachment IDs are valid.
- [ ] Grist shows thumbnails and readable Reference values.
- [ ] SQLite integrity check returns `ok`.
- [ ] CSV files use UTF-8 BOM.
- [ ] Automatic and human-reviewed states are distinct.
- [ ] A test rebuild preserves human-reviewed fields.

## Required Test Scenarios

### Mixed diagram

A table contains raster images, vector lines, and separate text.

Pass when embedded images and a complete page-render crop both exist, with clause, page, and bbox provenance.

### Attachment representation error

An Attachment cell displays `["L",168]`.

Pass when the local value becomes `[168]`, both internal attachment tables contain the file, and a thumbnail appears.

### Reference display error

`Clauses.Document` is blank and `Invalid column Clauses.Title` appears.

Pass when the target row ID exists, `visibleCol` points to `Documents.Title`, and a current-table `$Document.Title` helper is used as `displayCol`.

### Source revision

A new PDF adds clauses while existing rules have been reviewed.

Pass when new automatic records are added, reviewed records remain unchanged, and removed source records remain traceable.

## Stop Conditions

Stop and repair before completion when:

- Source files were overwritten.
- AI summaries were stored as raw evidence.
- Blank table cells were inferred without support.
- Only embedded images were used for composite diagrams.
- `.grist` was edited without a backup.
- Screen verification was skipped.
- A rebuild removed reviewed fields.

## Completion Report Template

```text
Changed files:
- ...

Record counts:
- Documents:
- Clauses:
- Tables:
- Visuals:
- Rules:
- Cases:

Visual outputs:
- Unique embedded images:
- Occurrence crops:
- Table crops:
- Composite diagrams:
- Page renders:

Validation:
- SQLite integrity_check:
- Reference errors:
- Attachment errors:
- Missing files:
- CSV/DB row count differences:
- Grist screen validation:

Human review still required:
- ...
```

## Final Rule

Do not report `PASS` until both automated validation and Grist Desktop screen validation have passed.
