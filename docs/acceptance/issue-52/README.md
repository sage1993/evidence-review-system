> Document status: CURRENT

# Issue #52 Parser Reproducibility Acceptance

## Current verdict

`IMPLEMENTED / NOT VERIFIED — DO NOT READY / DO NOT MERGE / DO NOT CLOSE`

The approved implementation scope is present on `agent/issue-52-opendataloader-reproducibility`. This ledger does not claim that local tests, static checks, wheel installation, or real OpenDataLoader fixture acceptance passed. GitHub Actions is excluded from acceptance under the repository's adopted manual-validation policy.

The implementation session could not obtain a runnable repository checkout because the execution container could not resolve or download the connected GitHub repository. No pytest, Ruff, mypy, compileall, documentation report, or wheel result is recorded from that environment.

## Implemented scope awaiting verification

- strict `parser-reproducibility.json` and immutable `parser-run.json` contracts;
- independent PDF page counting with `pypdf>=5,<6` for two-run validation;
- raw JSON/Markdown comparison and closed in-memory normalization;
- text, table, image, bounding-box, page-order, relationship, Markdown, and warning mismatch classification;
- exact OpenDataLoader warning taxonomy with raw-message preservation;
- stable `PWRN-*`, `PQUE-*`, and `PRUN-*` identities;
- immutable `REVIEW_REQUIRED` queue history with tamper checking;
- create-only single-output and all-or-nothing multi-output CLI writes;
- warning-only source-batch and `parser-run.json` identity binding without reopening the PDF;
- generated text, table, and warning fixture matrix;
- current user documentation and Stage 1 workflow guidance.

## Required implementation evidence

The final record must identify:

- exact implementation HEAD and final evidence HEAD;
- clean local and remote branch state;
- Windows version;
- Python 3.11 and 3.13 versions;
- parser configuration SHA-256;
- text, table, and warning fixture identities;
- reproducibility report status, counts, and SHA-256;
- warning report and review queue SHA-256 values;
- Python 3.11 and 3.13 wheel SHA-256 values.

## Required gates

| Gate | Current status |
|---|---|
| Strict configuration and parser-run authority | IMPLEMENTED / NOT VERIFIED |
| Independent source PDF page count | IMPLEMENTED / NOT VERIFIED |
| Raw and canonical JSON/Markdown comparison | IMPLEMENTED / NOT VERIFIED |
| Warning taxonomy and raw-message preservation | IMPLEMENTED / NOT VERIFIED |
| Stable `REVIEW_REQUIRED` queue | IMPLEMENTED / NOT VERIFIED |
| Text fixture | IMPLEMENTED / NOT VERIFIED |
| Table fixture | IMPLEMENTED / NOT VERIFIED |
| Warning fixture | IMPLEMENTED / NOT VERIFIED |
| Create-only and concurrent output protection | PARTIALLY TESTED IN CODE / NOT EXECUTED |
| Full pytest | NOT RUN |
| Ruff | NOT RUN |
| strict mypy | NOT RUN |
| compileall | NOT RUN |
| documentation integrity | NOT RUN |
| Python 3.11 wheel | NOT RUN |
| Python 3.13 wheel | NOT RUN |
| Human review | NOT STARTED |

## Acceptance rules

- `BYTE_IDENTICAL` or `SEMANTICALLY_IDENTICAL` is required for approved equal-run fixtures.
- Meaningful text, table, image, coordinate, page, relationship, Markdown, or warning mutations must produce `MISMATCH`.
- Parser version, adapter version, or configuration changes must produce `ENVIRONMENT_MISMATCH`.
- Missing or invalid PDF/parser authority must produce `PARSER_FAILED` or a documented exit-code-2 authority failure.
- Existing output files must remain byte-for-byte unchanged.
- Raw source PDFs and parser artifacts must remain unchanged.
- Final PASS may be recorded only after manual local verification at the exact remote HEAD.

## Actions not authorized by this ledger

- Draft PR creation before local verification
- Draft PR Ready conversion
- merge
- Issue #52 closure
- parent Issue #27 closure
