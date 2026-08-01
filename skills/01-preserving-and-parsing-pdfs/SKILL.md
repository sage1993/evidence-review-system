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
├─ 02_parser_output/       # JSON, Markdown, parser images
├─ 03_working/             # later stages only
├─ manifests/
└─ scripts/
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
ParsedAt
```

Use stable document IDs such as `LAW1`, not row numbers that may change.

Example hash command:

```bash
python -c "import hashlib, pathlib; p=pathlib.Path('01_source_pdf/law-1.pdf'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
```

### 2. Define acceptance criteria before parsing

Minimum criteria:

- Source and parser page counts match.
- Every parser element has a document and page.
- Bounding boxes are preserved when available.
- Parser images keep their original relative paths.
- Raw JSON and Markdown are never overwritten by cleanup scripts.

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
opendataloader-pdf 01_source_pdf/law-1.pdf \
  -o 02_parser_output/law-1 \
  -f json,markdown \
  --image-output external \
  --image-format png \
  --markdown-with-html
```

For scanned or difficult pages, run a separate OCR or hybrid pass. Store it under a distinct path such as:

```text
02_parser_output/law-1/base/
02_parser_output/law-1/ocr/
```

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
```

PDF metadata `creation date` and `modification date` are file metadata, not enactment, amendment, or effective dates. Store those legal dates separately only when supported by document content.

## Outputs

This stage must produce:

```text
manifests/source_documents.csv
02_parser_output/<document>/document.json
02_parser_output/<document>/document.md
02_parser_output/<document>/images/
manifests/parser_runs.csv
```

The next stage receives immutable PDFs, parser outputs, file hashes, and page counts.

## Common Mistakes

| Mistake | Correction |
|---|---|
| Writing cleaned text back into parser JSON | Keep raw parser files immutable |
| Treating PDF metadata as legal dates | Extract legal dates from document text separately |
| OCRing every page | OCR only scanned or failed pages and preserve both versions |
| Renaming files without a manifest | Use stable document IDs and preserve original names |
| Parsing without recording the tool version | Store parser version and command line |

## Verification

- Recompute SHA-256 and compare with the manifest.
- Confirm PDF page count equals parser page count.
- Confirm JSON and Markdown exist for every source.
- Confirm parser output is outside the source directory.
- Confirm rerunning parsing does not modify the original PDF.

## Handoff

**REQUIRED NEXT SKILL:** Use `structuring-pdf-content-and-visuals` when parser outputs must be reconstructed into clauses, tables, and visual records.
