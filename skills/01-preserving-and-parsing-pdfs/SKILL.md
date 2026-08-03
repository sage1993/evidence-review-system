---
name: preserving-and-parsing-pdfs
description: Use when preparing PDF source files for reproducible extraction, especially when originals must remain immutable or parser outputs need traceable page and coordinate metadata.
---

# Preserving and Parsing PDFs

## Overview

Create a reproducible source layer before any cleanup or database work. The PDF and raw parser outputs are evidence; they are never replaced by normalized text or later interpretations.

**Core principle:** freeze the source first, then parse into a separate output area.

## When to Use

Use this skill for regulatory PDFs, guidelines, manuals, scanned documents, or mixed digital/scanned files that will later become structured data. Do not use it for PDF editing, signing, merging, or final database construction.

## Required Workspace

```text
workspace/
├─ 01_source_pdf/          # read-only originals
├─ 02_parser_output/       # immutable run directories
├─ 03_working/             # later stages only
├─ manifests/
└─ scripts/
```

Each OpenDataLoader run directory contains:

```text
02_parser_output/<document>/<run>/
├─ parser-run.json
├─ document.json
├─ document.md
├─ parser.log              # optional warning source
└─ images/
```

## Procedure

### 1. Inventory every source

Record, at minimum:

```text
DocumentID
OriginalFileName
RelativePath
SHA256
PageCount
FileSize
PDFKind: digital | scanned | mixed
Encrypted: true | false
ParserVersion
ParserConfiguration
AdapterVersion
```

Use the source-batch document ID policy. File names and row numbers do not define identity.

Example hash command:

```bash
python -c "import hashlib, pathlib; p=pathlib.Path('01_source_pdf/reference.pdf'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
```

### 2. Define acceptance criteria before parsing

Minimum criteria:

- Source and parser page counts match.
- Every parser element has a document and page.
- Bounding boxes are preserved when available.
- Parser images keep their original relative paths.
- Raw JSON, Markdown, logs, and images are never overwritten.
- Parser version, adapter version, and configuration are explicit.
- Repeated runs are checked before downstream ingestion.

### 3. Classify the PDF

- **Digital:** selectable text is present on most pages.
- **Scanned:** pages are primarily full-page images with little or no text.
- **Mixed:** digital text and scanned pages coexist.

Do not run OCR over reliable digital text by default. Keep OCR output separate so it can be compared rather than silently merged.

### 4. Parse with OpenDataLoader

Confirm installed options first:

```bash
opendataloader-pdf --help
```

Typical extraction:

```bash
opendataloader-pdf 01_source_pdf/reference.pdf \
  -o 02_parser_output/reference/run-a \
  -f json,markdown \
  --image-output external \
  --image-format png \
  --markdown-with-html
```

OpenDataLoader is executed outside the evidence-review validator. After parsing, create immutable `parser-run.json` with the source relative path, source SHA-256, source size, source page count, document/revision IDs, parser version, adapter version, exact parser configuration, and platform family.

For scanned or difficult pages, run a separate OCR or hybrid pass under a distinct run directory. Do not merge it into the base run.

### 5. Preserve raw fields

Retain fields such as:

```text
file name
number of pages
type
id
page number
bounding box
content
kids
rows / cells
source
font size
previous / next linkage
warnings
```

PDF metadata `creation date` and `modification date` are file metadata, not enactment, amendment, or effective dates. Store legal dates separately only when supported by document content.

### 6. Validate two parser runs

```powershell
evidence-review parser reproducibility validate `
  --source 01_source_pdf/reference.pdf `
  --run-a 02_parser_output/reference/run-a `
  --run-b 02_parser_output/reference/run-b `
  --config parser-reproducibility.json `
  --output 03_working/reference-reproducibility.json
```

Use a fresh output path. `MISMATCH`, `ENVIRONMENT_MISMATCH`, and `PARSER_FAILED` are not parser acceptance.

### 7. Collect warnings for review

```powershell
evidence-review parser warnings collect `
  --source-manifest manifests/source-batch.json `
  --parser-artifacts 02_parser_output/reference/run-a `
  --config parser-reproducibility.json `
  --warning-output 03_working/reference-warnings.json `
  --queue-output 03_working/reference-review-queue.json
```

Warning collection binds the source-batch entry to `parser-run.json` and does not reopen the PDF. Every warning remains visible and creates or updates one `REVIEW_REQUIRED` queue entry.

## Outputs

This stage must produce:

```text
manifests/source-batch.json
02_parser_output/<document>/<run>/parser-run.json
02_parser_output/<document>/<run>/document.json
02_parser_output/<document>/<run>/document.md
02_parser_output/<document>/<run>/images/
03_working/<document>-reproducibility.json
03_working/<document>-warnings.json
03_working/<document>-review-queue.json
```

The next stage receives immutable PDFs, verified parser runs, parser report hashes, warning evidence, and page counts.

## Common Mistakes

| Mistake | Correction |
|---|---|
| Writing cleaned text back into parser JSON | Keep raw parser files immutable |
| Treating PDF metadata as legal dates | Extract legal dates from document text separately |
| OCRing every page | OCR only scanned or failed pages and preserve both versions |
| Renaming files without a manifest | Use source-batch identity and preserve original names |
| Parsing without exact run authority | Record `parser-run.json` beside every run |
| Ignoring parser warnings | Preserve them in the review queue |
| Comparing runs with different parser versions | Record `ENVIRONMENT_MISMATCH`; do not claim equivalence |
| Reusing an existing report path | Use create-only fresh output paths |

## Verification

- Recompute PDF and parser artifact SHA-256 values.
- Confirm independent PDF page count equals parser page count.
- Confirm JSON and Markdown exist for every run.
- Confirm parser output is outside the source directory.
- Confirm validation does not modify any source or raw parser artifact.
- Confirm equal fixtures are `BYTE_IDENTICAL` or `SEMANTICALLY_IDENTICAL`.
- Confirm text, table, coordinate, page, Markdown, and warning mutations are `MISMATCH`.
- Confirm warning collection is deduplicated and raw messages remain unchanged.

## Handoff

**REQUIRED NEXT SKILL:** Use `structuring-pdf-content-and-visuals` only after the selected parser run has passed reproducibility validation and warning pages have been queued for review.
