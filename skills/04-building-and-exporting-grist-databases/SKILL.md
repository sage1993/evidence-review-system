---
name: building-and-exporting-grist-databases
description: Use when cleaned PDF-derived records must be loaded into a local Grist database or exported as CSV, especially when Attachments, References, or direct .grist SQLite edits are involved.
---

# Building and Exporting Grist Databases

## Overview

Create a local, portable Grist database from cleaned records and image files. Prefer supported imports and a valid template; direct SQLite editing is a controlled exception.

**Core principle:** Grist values, metadata, and embedded files must agree with each other.

## Inputs

- Cleaned CSV-ready records
- Visual and table image files
- Stable IDs and relative paths
- Review-state definitions

## CSV Contract

Create these files as needed:

```text
00_guide.csv
documents.csv
clauses.csv
source_elements.csv
extracted_tables.csv
visuals.csv
rules.csv
cases.csv
manifest.csv
```

Rules:

- Encoding: UTF-8 with BOM (`utf-8-sig`)
- Dates: `YYYY-MM-DD`
- Boolean: `TRUE` / `FALSE`
- IDs: text, never spreadsheet row numbers
- Paths: workspace-relative
- Multiline text: standard CSV quoting
- Relationships: stable target IDs

A local image path in CSV does not automatically become a Grist Attachment. Import metadata first, then attach files through Grist or a verified script.

## Recommended Data Model

```text
Documents 1 ── N Clauses
Clauses   1 ── N SourceElements
Clauses   1 ── N Visuals
Clauses   1 ── N ExtractedTables
Clauses   1 ── N Rules
Rules     1 ── N Cases
Visuals   N ── 1 ExtractedTables  # optional
```

Recommended import order:

```text
Documents → Clauses → SourceElements → ExtractedTables → Visuals → Rules → Cases
```

## Preferred Build Method

1. Create a valid empty `.grist` document in Grist Desktop.
2. Define tables and column types.
3. Import CSV files in dependency order.
4. Convert relationship columns to References.
5. Configure display columns.
6. Add selected images as Attachments.
7. Save a backup before scripted changes.

## Direct `.grist` Editing

A `.grist` file is SQLite-based, but its metadata is version-sensitive. Direct editing is allowed only when using a valid Grist document as the template and only through a reproducible script.

### Attachment cells

Do not confuse typed API values with local SQLite cell values.

```text
Wrong local value: ["L", 3]
Correct local value: [3]
```

The wrong form may display as a pink cell containing raw list data.

Every attachment must exist in both:

```text
_grist_Attachments
_gristsys_Files
```

The user-table Attachment cell stores a list of `_grist_Attachments.id` values.

### Reference cells

The physical value is the target table row ID. Display text is configured separately.

```text
Clauses.Document value → Documents.id
Visible column          → Documents.Title
```

For direct metadata construction:

- `type`: `Ref:Documents`
- `visibleCol`: metadata ID of the target table display column
- `displayCol`: hidden formula column in the current table
- helper formula example: `$Document.Title`

Do not point `displayCol` directly to `Documents.Title`. That can produce blank references or errors such as `Invalid column Clauses.Title`.

## Exporting

Export each user table to UTF-8 BOM CSV. Replace physical Grist row IDs with stable domain IDs where possible. Produce `manifest.csv` with file name, row count, generated timestamp, and source database hash.

## Incremental Rebuilds

1. Back up the `.grist` file with a dated name.
2. Regenerate automatic tables by stable ID.
3. Merge human-reviewed fields.
4. Add new attachments without changing existing attachment IDs unnecessarily.
5. Mark removed source records instead of silently deleting them.
6. Re-export CSV and run full validation.

## Common Failures

| Symptom | Cause | Fix |
|---|---|---|
| Pink attachment cell with `["L",3]` | API typed list stored in SQLite | Store `[3]` and validate file tables |
| Reference column is blank | Missing target row or bad metadata | Check target ID, `visibleCol`, helper `displayCol` |
| `Invalid column Clauses.Title` | Target column used directly as `displayCol` | Use current-table helper formula |
| CSV Korean text is broken in Excel | No BOM | Export with `utf-8-sig` |
| Database becomes very large | All PDFs and duplicate renders embedded | Keep originals external; attach review-critical visuals |

## Build Verification

Before handoff:

```sql
PRAGMA integrity_check;
```

Also confirm:

- All Reference IDs exist.
- All Attachment IDs exist in both internal tables.
- Every `displayCol` points to a current-table formula helper.
- Every `visibleCol` points to the target display field.
- View fields do not reference deleted columns.
- CSV row counts match database table counts.

## Handoff

**REQUIRED NEXT SKILL:** Use `validating-pdf-database-workflows` before declaring the database complete.
