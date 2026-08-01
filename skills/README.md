# PDF-to-Grist Skill Set

This package replaces one large end-to-end skill with five focused skills. Load only the stage that matches the current task.

## Recommended order

1. `preserving-and-parsing-pdfs`
2. `structuring-pdf-content-and-visuals`
3. `cleaning-pdf-derived-data`
4. `building-and-exporting-grist-databases`
5. `validating-pdf-database-workflows`

## Stage contracts

| Stage | Required input | Main output |
|---|---|---|
| 1 | Original PDFs | Immutable source inventory, hashes, parser JSON/Markdown/images |
| 2 | Parser outputs + PDFs | Documents, clauses, source elements, tables, visuals, crops |
| 3 | Raw structured records | Normalized text, reviewed mappings, rule/case candidates |
| 4 | Clean records + image files | Local `.grist` database and UTF-8 BOM CSV exports |
| 5 | Entire workspace | Automated validation report and manual Grist acceptance result |

## Shared invariants

- Never overwrite source PDFs or raw parser outputs.
- Keep raw evidence separate from normalized, summarized, or interpreted data.
- Every derived record must retain source provenance: document, page, coordinates, source element ID, or source path.
- Do not treat parser output as verified legal interpretation.
- Do not declare completion without both automated checks and Grist Desktop screen verification.

## Installation layout

Copy each skill directory into the skills directory recognized by the target agent runtime. Keep directory names unchanged so cross-references remain discoverable.
