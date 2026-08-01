# Ansim Housing PDF-to-Grist Workspace Instructions

## 1. Purpose

This workspace converts the `law-1` and `law-2` PDF sources into traceable structured records, visual assets, CSV exports, and a local Grist database.

All work must preserve four invariants:

1. **Source immutability** — original PDFs and raw parser outputs are evidence and must not be overwritten.
2. **Source traceability** — every derived record must retain document, page, coordinates, source ID, or source path.
3. **Reproducibility** — generated artifacts must be rebuildable from scripts and stable IDs.
4. **Human review precedence** — automated extraction and interpretation must never be presented as reviewed fact.

## 2. Mandatory Skill Routing

Before editing files, classify the requested work by stage and read the matching `SKILL.md`. Load only the stages needed for the task, but never skip an earlier stage whose outputs are missing, stale, or invalid.

The project-local skill copies are under `skills/`. If the same skills are installed in the agent runtime, use the installed copies with the same names.

| Stage | Read this skill | Use when the task involves |
|---:|---|---|
| 1 | `skills/01-preserving-and-parsing-pdfs/SKILL.md` (`preserving-and-parsing-pdfs`) | adding or replacing PDFs, freezing originals, hashing, page inventory, OpenDataLoader parsing, OCR/hybrid passes, or raw parser output |
| 2 | `skills/02-structuring-content-and-visuals/SKILL.md` (`structuring-pdf-content-and-visuals`) | rebuilding chapters/sections/clauses, flattening parser JSON, extracting tables, embedded images, page renders, crops, diagrams, coordinates, or visual manifests |
| 3 | `skills/03-cleaning-pdf-derived-data/SKILL.md` (`cleaning-pdf-derived-data`) | whitespace/OCR cleanup, normalized text, duplicate analysis, record linking, rule/case candidates, provenance, or review states |
| 4 | `skills/04-building-and-exporting-grist-databases/SKILL.md` (`building-and-exporting-grist-databases`) | CSV creation, Grist table construction, Attachments, References, `.grist` SQLite changes, exports, or incremental rebuilds |
| 5 | `skills/05-validating-pdf-database-workflows/SKILL.md` (`validating-pdf-database-workflows`) | validation, completion decisions, Grist display errors, broken images/references, integrity checks, regression checks, or acceptance reports |

### Routing rules

- **New or changed source PDF:** use Stages **1 → 2 → 3 → 4 → 5**.
- **Existing parser output, but structure or visuals need rebuilding:** use Stages **2 → 3 → 4 → 5**.
- **Existing structured data needs cleanup or review-state changes:** use Stages **3 → 4 → 5**.
- **Only CSV or Grist construction/export changes:** use Stages **4 → 5**.
- **Only validation or diagnosis:** start with Stage **5**; also load Stage 4 when repairing Grist metadata, Attachments, References, or exports.
- **Any claim that work is complete, fixed, valid, or ready for delivery:** Stage 5 is mandatory.
- When the correct starting stage is unclear, inspect source hashes, parser manifests, generated manifests, database timestamps, and validation results. Start at the earliest stage with missing, stale, or invalid outputs.
- For an end-to-end request, follow the skill handoff order. Do not replace the five-stage workflow with an improvised combined process.

### How to apply a skill

1. Read the complete matching `SKILL.md` before changing artifacts.
2. Follow its input contract, procedure, output contract, common-failure guidance, and verification steps.
3. Preserve the handoff artifacts required by the next stage.
4. Record deviations and unresolved items in the completion report.

## 3. Workspace Map

- `01_database/안심주택DB.grist` — primary local database; back up before scripted modification.
- `02_source_pdf/` — source PDFs and raw OpenDataLoader JSON/Markdown; never normalize or overwrite in place.
- `03_extracted_images/opendataloader/` — images emitted by OpenDataLoader.
- `03_extracted_images/pdf_embedded/` — PDF streams, transparency composites, unique images, occurrence crops, and manifests.
- `04_visuals/page_renders/` — full rendered pages used to recover composite/vector content.
- `04_visuals/image_context_crops/` — crops showing actual image placement and surrounding context.
- `04_visuals/table_crops/` — rendered table regions.
- `04_visuals/composite_diagrams/` — combined visual regions associated with a page and clause.
- `04_visuals/manifests/` — generated paths, coordinates, hashes, counts, and record links.
- `05_exports/` — UTF-8 BOM CSV exports.
- `scripts/` — rebuild, repair, export, and validation scripts.
- `skills/` — the five stage-specific workflow skills.

## 4. Source and Data Rules

1. Do not modify files in `02_source_pdf/`. Add a new source revision under a new file name and update the source manifest.
2. Keep source evidence and derived interpretation separate:
   - `RawText` — source transcription
   - `NormalizedText` — formatting cleanup only
   - `Summary`, `Rules`, `Cases` — interpretation or structured meaning
3. Store PDF bounding boxes as `left, bottom, right, top` unless a field explicitly declares another coordinate system.
4. Do not invent image descriptions, OCR text, table values, missing cells, legal dates, exceptions, or rule outcomes.
5. Keep parser-generated and AI-generated records in an automatic-review state. Only human-confirmed values may use the existing reviewed status.
6. Preserve existing database labels, field names, and status values exactly unless the user requests a schema migration. Do not translate Korean data values merely because this instruction file is in English.
7. Keep `SourceElements.RawJSON` unchanged.
8. Manage duplicate images with SHA-256 and `DuplicateGroup`; do not delete source occurrences merely because the binary content is duplicated.
9. Use workspace-relative paths as persistent identifiers. Do not store machine-specific absolute paths in exported data.
10. Keep original PDFs external to Grist unless the user explicitly requires them embedded. Attach review-critical crops and visual evidence instead.

## 5. Stable IDs

Do not renumber existing IDs during rebuilds.

- Documents: `LAW1`, `LAW2`
- Unique PDF images: `PDF-LAW*-U###`
- Page image occurrences: `OCC-LAW*-###`
- Table crops: `TBL-LAW*-###`
- Composite diagrams: `COMP-LAW*-###`
- Page renders: `PAGE-LAW*-###`

New ID schemes must be deterministic, documented in a manifest, and stable across identical reruns.

## 6. Grist Data Model

Expected relationships:

- `Documents` 1 → N `Clauses`
- `Clauses` 1 → N `SourceElements`
- `Clauses` 1 → N `Visuals`
- `Clauses` 1 → N `ExtractedTables`
- `Clauses` 1 → N `Rules`
- `Rules` 1 → N `Cases`
- `Visuals.RelatedTable` → `ExtractedTables`
- `ExtractedTables.TableImage` → table-crop Attachment

Recommended load order:

```text
Documents → Clauses → SourceElements → ExtractedTables → Visuals → Rules → Cases
```

## 7. Grist-Specific Safety Rules

1. Prefer Grist Desktop imports or a known-valid `.grist` template. Direct SQLite editing is a controlled exception.
2. Before any direct `.grist` modification, create a dated backup.
3. Local SQLite values for Grist `Attachments` and `RefList` cells use JSON arrays such as `[1,2]`. Do not store API typed-list values such as `["L",1,2]`.
4. Every Attachment ID must exist in both `_grist_Attachments` and `_gristsys_Files`.
5. A Reference cell stores the target table row ID. Display text is metadata, not the physical Reference value.
6. For Reference display metadata:
   - `visibleCol` points to the target table display column.
   - `displayCol` points to a helper formula column in the current table.
   - Do not point `displayCol` directly to a target-table column. This can produce blank cells or errors such as `Invalid column Clauses.Title`.
7. After SQLite changes, run the repair and validation scripts before export or delivery.

## 8. Standard Workflows

### A. Review-only work with unchanged sources

1. Load Stage 3 when changing normalized text, links, rules, cases, or review states.
2. Edit only derived/review fields in Grist.
3. Run:

```bash
python scripts/repair_grist_document.py
python scripts/export_grist_csv.py
python scripts/validate_workspace.py
```

4. Load Stage 5 and complete Grist Desktop screen validation before reporting completion.

### B. Changed PDF or parser output

1. Load Stages 1 through 5 in order.
2. Back up `01_database/안심주택DB.grist` with a dated file name.
3. Add the new source revision without overwriting prior evidence.
4. Rebuild structure and visuals.
5. Merge human-reviewed fields by stable ID; do not replace them with regenerated automatic values.
6. Run:

```bash
python scripts/rebuild_visuals_and_grist.py
python scripts/repair_grist_document.py
python scripts/export_grist_csv.py
python scripts/validate_workspace.py
```

7. Compare `04_visuals/manifests/summary.csv`, CSV row counts, and Grist table counts.
8. Complete Stage 5 screen acceptance.

### C. Grist image or Reference error

1. Load Stage 5 to diagnose the symptom.
2. Load Stage 4 before changing Attachment or Reference storage/metadata.
3. Reproduce the issue and preserve a backup.
4. Repair through a script, not an undocumented manual SQLite edit.
5. Run automated validation.
6. Open Grist Desktop and confirm thumbnails, Reference display values, and absence of error notifications.

## 9. Prohibited Actions

- Overwriting source PDF, JSON, or Markdown with normalized output
- Writing unreviewed AI interpretation into raw-evidence fields
- Silently filling unsupported legal, table, OCR, or diagram content
- Deleting source records only because they appear duplicated
- Replacing reviewed values during an automatic rebuild
- Editing Grist metadata without a backup and validation
- Storing API typed-list values directly in `.grist` SQLite cells
- Using only embedded-image extraction for mixed vector/text/raster diagrams
- Deleting page renders because embedded images already exist
- Declaring success based only on `PRAGMA integrity_check`
- Skipping Grist Desktop screen verification when claiming completion

## 10. Completion Gate

The task is not complete until all applicable Stage 5 checks pass:

- Source files and raw parser outputs remain unchanged.
- Source SHA-256 and page-count checks pass.
- Required records and columns exist.
- Stable IDs are unique and References resolve.
- All Attachment IDs resolve in both internal Grist file tables.
- Manifest paths exist and hashes match.
- CSV files use UTF-8 BOM and row counts match the database.
- `PRAGMA integrity_check` returns `ok`.
- Human-reviewed fields survive a test rebuild.
- Grist Desktop displays actual thumbnails rather than raw list values.
- Reference columns display readable values rather than blanks.
- No `Invalid column ...` notification appears.
- A manual sample of visual and table records matches the source PDF.

If Grist Desktop cannot be launched in the current environment, report automated validation separately and state that final screen acceptance remains pending. Do not report overall `PASS`.

## 11. Work Report Format

Every completion report must include:

```text
Skills used:
- ...

Changed files:
- ...

Record changes:
- Documents: + / ~ / -
- Clauses: + / ~ / -
- SourceElements: + / ~ / -
- Tables: + / ~ / -
- Visuals: + / ~ / -
- Rules: + / ~ / -
- Cases: + / ~ / -

Visual outputs:
- Unique embedded images:
- Occurrence crops:
- Table crops:
- Composite diagrams:
- Page renders:

Validation:
- Commands executed:
- SQLite integrity_check:
- Reference errors:
- Attachment errors:
- Missing files:
- CSV/DB row-count differences:
- Grist Desktop screen validation:

Human review still required:
- ...
```
