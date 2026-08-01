---
name: cleaning-pdf-derived-data
description: Use when extracted text, tables, and visual metadata contain spacing, line-break, OCR, duplication, or interpretation issues and raw evidence must remain separate from normalized and reviewed data.
---

# Cleaning PDF-Derived Data

## Overview

Produce human-reviewable records without changing source evidence. Cleaning fixes representation; it does not silently create legal meaning.

**Core principle:** `RawText`, `NormalizedText`, summaries, rules, and cases are distinct data layers.

## Inputs

- Raw clauses
- Source elements
- Table structures and crops
- Visual manifests and images
- Immutable parser output

## Data Layers

| Layer | Purpose | Editable |
|---|---|---|
| Raw | Exact parser/source evidence | No |
| Normalized | Spacing, line-break, Unicode, obvious parser repair | Yes, reviewed |
| Summary | Concise meaning for human use | Yes, reviewed |
| Rule | Atomic condition or requirement | Yes, reviewed |
| Case | Example-specific decision or outcome | Yes, reviewed |

## Procedure

### 1. Normalize text conservatively

Allowed operations:

- Collapse repeated whitespace
- Join line breaks that split a sentence
- Remove repeated page headers and footers
- Normalize Unicode to NFC
- Mark or correct obvious broken parser characters
- Preserve paragraph and list boundaries when meaningful

Prohibited operations:

- Replacing legal terminology with simpler wording in `NormalizedText`
- Removing provisos, exceptions, qualifications, or footnotes
- Filling uncertain table cells by inference
- Changing `recommended` into `required`
- Adding an eligibility decision not present in the source

When uncertain, keep the source text and add a `ReviewNote`.

### 2. Link clauses, tables, and visuals

Use more than page proximity. Evaluate:

- Bbox overlap or vertical adjacency
- Clause page range
- Heading boundaries
- Captions and nearby labels
- Table continuation markers
- Visual occurrence order

Do not attach a visual to the nearest preceding clause when coordinates or layout contradict that choice.

### 3. Separate visuals, rules, and cases

`Visuals` describes what is shown. `Rules` stores atomic conditions. `Cases` stores example-specific decisions.

Recommended `Rules` fields:

```text
RuleID, ClauseID, RuleName, Subject,
ConditionField, Operator, NumericValue, TextValue,
Unit, Result, Exception, SourceQuote,
ReviewStatus, ReviewNote
```

Recommended `Cases` fields:

```text
CaseID, RuleID, VisualID, CaseName,
ConditionSummary, Decision, DecisionBasis,
CaseImagePath, ReviewStatus, ReviewNote
```

Split multiple conditions into multiple rule rows. Keep modal meaning distinct:

```text
required | recommended | permitted | principle | exception
```

### 4. Manage duplicates without destroying provenance

Use SHA-256 for file identity and retain occurrence records for every page and bbox. Mark one representative file when useful, but do not delete source occurrences that support provenance.

### 5. Use explicit review states

Recommended values:

```text
Unreviewed
Automatically Extracted
Needs Correction
Reviewed
Excluded
Removed from Source
```

Only a human-confirmed record may be marked `Reviewed`.

### 6. Prepare stable output records

All relationships must use stable IDs, not row positions. Keep relative file paths rooted at the workspace.

Recommended cleaned outputs:

```text
documents.csv
clauses.csv
source_elements.csv
extracted_tables.csv
visuals.csv
rules.csv
cases.csv
```

### 7. Preserve reviewed data during updates

When a PDF or parser output changes:

1. Back up existing cleaned data.
2. Compare document hashes and page counts.
3. Regenerate automatic records by stable ID.
4. Merge reviewed `NormalizedText`, summaries, rules, cases, and notes by ID.
5. Mark missing source elements as `Removed from Source`; do not erase them immediately.
6. Re-run validation.

Automatic rebuilds must never overwrite human review fields.

## Common Mistakes

| Mistake | Correction |
|---|---|
| Storing AI summary in `RawText` | Preserve raw text and use a separate summary field |
| Removing a proviso to improve readability | Keep the proviso and structure it separately |
| Treating empty merged cells as missing values | Preserve merge metadata and visual evidence |
| Deleting duplicate images | Deduplicate files, not occurrences |
| Marking automatic interpretation as reviewed | Use `Automatically Extracted` until confirmed |
| Rebuilding by row number | Merge by stable IDs |

## Verification

- Raw source text is byte-for-byte or field-for-field unchanged.
- Normalized text preserves all substantive conditions and exceptions.
- Every rule has a source clause and quote or element link.
- Every case has a source visual or explicit textual basis.
- Human review fields survive a test rebuild.
- Relative paths resolve inside the workspace.

## Handoff

**REQUIRED NEXT SKILL:** Use `building-and-exporting-grist-databases` when cleaned records must become CSV exports and a local Grist database.
