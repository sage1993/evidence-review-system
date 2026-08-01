---
name: structuring-pdf-content-and-visuals
description: Use when parser output contains flattened headings, tables, embedded images, vector diagrams, or page-coordinate data that must be reconstructed into document, clause, table, and visual records.
---

# Structuring PDF Content and Visuals

## Overview

Convert raw parser elements into traceable document structure while rebuilding visual material that cannot be recovered from embedded-image extraction alone.

**Core principle:** structure follows source order and coordinates, not Markdown heading levels alone.

## Inputs

- Immutable PDFs
- Parser JSON and Markdown
- Parser-extracted images
- Source manifest from `preserving-and-parsing-pdfs`

## Procedure

### 1. Flatten raw elements without losing hierarchy

Create a `SourceElements` record for every top-level element and any required child element.

Recommended fields:

```text
ElementID, DocumentID, SourceID, ParentElementID,
ElementType, Page, BBoxLeft, BBoxBottom, BBoxRight, BBoxTop,
Content, SourceImagePath, RawJSON, Used
```

Parser elements without IDs need deterministic IDs:

```text
LAW1-P005-LIST-001
LAW1-P005-LIST-001-ITEM-01
```

Base IDs on document, page, type, and original order so reruns remain stable.

### 2. Reconstruct chapters, sections, and clauses

Do not trust Markdown heading depth when every heading has been flattened to `#`.

Use evidence in this order:

1. JSON element type and source order
2. Font size and position
3. Heading text patterns
4. Previous/next element linkage
5. Human review

Useful patterns:

```regex
^제\s*\d+\s*장
^제\s*\d+\s*절
^\d+-\d+-\d+\.
^제\s*\d+\s*조(?:의\s*\d+)?
```

A body citation can match the same pattern. Confirm that the candidate is a heading-like element and appears at a plausible structural boundary.

Recommended `Clauses` fields:

```text
ClauseID, DocumentID, ParentClauseID, Chapter, Section,
ClauseNumber, ClauseTitle, StartPage, EndPage,
RawText, ContentType, ReviewStatus
```

### 3. Extract visuals through two independent routes

#### Embedded-image route

Preserve:

- Raw image streams
- Transparency-mask composites
- Unique images by SHA-256
- Every page occurrence and placement bbox

Do not discard duplicate occurrences. A repeated image can appear in different clauses or pages.

#### Page-render route

Use page rendering for vector lines, cell backgrounds, text overlays, combined diagrams, and table layouts.

Create:

```text
page_renders/
image_context_crops/
table_crops/
composite_diagrams/
case_crops/
```

OpenDataLoader commonly reports `[left, bottom, right, top]`. PyMuPDF uses a top-left display coordinate system. Convert explicitly:

```python
from __future__ import annotations
import fitz


def bottom_bbox_to_rect(page: fitz.Page, bbox, margin: float = 0) -> fitz.Rect:
    left, bottom, right, top = map(float, bbox)
    return fitz.Rect(
        left - margin,
        page.rect.height - top - margin,
        right + margin,
        page.rect.height - bottom + margin,
    ) & page.rect
```

For rotated pages, inspect `page.rotation_matrix`, `page.derotation_matrix`, and `page.transformation_matrix` before cropping.

### 4. Preserve tables as both data and images

Recommended fields:

```text
TableID, DocumentID, ClauseID, StartPage, EndPage,
Title, RowCount, ColumnCount, PlainText,
TableHTML, RowsJSON, TableImagePath,
PreviousTableID, NextTableID, ReviewStatus
```

Keep row/column indices, rowspan, colspan, header flags, cell bboxes, and raw cell content. JSON table count and Markdown `<table>` count may differ because of page splitting or conversion behavior.

### 5. Build visual records

Recommended fields:

```text
VisualID, DocumentID, ClauseID, Page, VisualType,
ImagePath, SourcePath, SourceKey,
BBoxLeft, BBoxBottom, BBoxRight, BBoxTop,
PixelWidth, PixelHeight, SHA256, DuplicateGroup,
RelatedTableID, ReviewStatus
```

## Outputs

- `documents.csv`
- `clauses_raw.csv`
- `source_elements.csv`
- `extracted_tables_raw.csv`
- `visuals_raw.csv`
- Rendered pages and crops
- Visual manifests with hashes and coordinates

## Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Only part of a diagram is extracted | Diagram mixes vector, text, and images | Render and crop the page region |
| Crop is vertically inverted | Bottom-left and top-left coordinates were mixed | Apply page-height conversion |
| Same image appears under many names | Reused xref or repeated placements | Separate unique file from occurrence records |
| Clause hierarchy is flat | Markdown levels were trusted | Rebuild from JSON type, font, order, and patterns |
| Merged table cells disappear | Table was flattened to CSV only | Preserve JSON/HTML plus a crop image |

## Verification

- Every clause has a document and page range.
- Every visual has a source path or rendered crop.
- Every crop matches the intended PDF region.
- Duplicate files share a hash while occurrences remain separate.
- Tables preserve structural data and a visual reference.

## Handoff

**REQUIRED NEXT SKILL:** Use `cleaning-pdf-derived-data` to normalize text, connect records, and separate source evidence from interpretation.
