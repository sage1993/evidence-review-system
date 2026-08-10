---
name: ers-pdf
description: Use when a user invokes $ERS_PDF or asks Codex Desktop to parse a PDF for evidence-backed review.
---

# ERS PDF Parsing

## Overview

`$ERS_PDF` is the user-facing shortcut for preparing a PDF for Evidence Review System questions. It creates immutable parser evidence and a searchable local evidence database; it does not answer the review question.

## Required workflow

1. Use only the PDF explicitly attached or named by the user. Do not select repository samples by filename.
2. Preserve the original PDF under a separate source directory and record its SHA-256, size, page count, and document identity.
3. If an immutable parser artifact is already supplied, bind and validate it. Otherwise check `opendataloader-pdf --help` and run the parser into a new output directory. If the parser is unavailable, stop and report the missing tool; never claim that a plain text extraction is an ERS parse.
4. Keep `parser-run.json`, raw JSON, Markdown, images, logs, parser version, configuration, source hash, and page counts together. Never overwrite a source or raw parser run.
5. Run two-run reproducibility validation and parser warning collection using fresh output paths. A mismatch, missing authority, or parser failure is not success.
6. Create a source-batch v2 manifest, then run:

```powershell
evidence-review source-batch prepare --root <workspace> --manifest <workspace>\manifests\source-batch.json
evidence-review source-batch ingest --root <workspace> --manifest <workspace>\manifests\source-batch.json --output <workspace>\evidence\evidence.sqlite
```

7. Report success only when parser-ready reference/table evidence was ingested, `evidence.sqlite` exists, and the source state is `READY_TO_EVALUATE`. Preserve `PENDING_PARSER_OUTPUT`, `PENDING_DRAWING_INGESTION`, `INPUT_CONFIRMATION_REQUIRED`, `BLOCKED`, and `FAILED` states exactly.

## Output contract

Give the user a short Korean summary containing:

- original PDF name and preserved workspace;
- parser status and any warnings;
- searchable evidence count or the exact blocking reason;
- the next command: `$ERS_REVIEW <질문>` only when the evidence database is ready.

For a drawing-only PDF, explain that it is routed to drawing confirmation and is not searchable reference evidence until the required confirmation is complete.

## Safety rules

- 원본 PDF와 raw parser output을 덮어쓰지 않는다.
- Do not infer document role, legal authority, dates, or identity from a filename or title.
- Do not invent missing text, table cells, coordinates, parser metadata, or page references.
- Do not use unconfirmed drawing candidates as Math or Rule Engine inputs.
- Do not call the PDF “parsed,” “searchable,” or “ready for questions” when `PENDING_PARSER_OUTPUT`, `BLOCKED`, or `FAILED` remains.

## Handoff

After a successful parse, wait for the user to invoke `$ERS_REVIEW` with a question. Do not produce a regulatory conclusion during the parsing step.
