> Document status: CURRENT

# Issue #52 Parser Reproducibility Acceptance

## Current verdict

`NOT VERIFIED — DO NOT READY / DO NOT MERGE / DO NOT CLOSE`

Implementation is present on `agent/issue-52-opendataloader-reproducibility`, but this ledger does not claim that local tests, static checks, wheel installation, or real OpenDataLoader fixture acceptance passed. GitHub Actions is excluded from acceptance under the repository's adopted manual-validation policy.

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
| Strict configuration and parser-run authority | NOT VERIFIED |
| Independent source PDF page count | NOT VERIFIED |
| Raw and canonical JSON/Markdown comparison | NOT VERIFIED |
| Warning taxonomy and raw-message preservation | NOT VERIFIED |
| Stable `REVIEW_REQUIRED` queue | NOT VERIFIED |
| Text fixture | NOT VERIFIED |
| Table fixture | NOT VERIFIED |
| Warning fixture | NOT VERIFIED |
| Create-only and concurrent output protection | NOT VERIFIED |
| Full pytest | NOT VERIFIED |
| Ruff | NOT VERIFIED |
| strict mypy | NOT VERIFIED |
| compileall | NOT VERIFIED |
| documentation integrity | NOT VERIFIED |
| Python 3.11 wheel | NOT VERIFIED |
| Python 3.13 wheel | NOT VERIFIED |
| Human review | NOT VERIFIED |

## Acceptance rules

- `BYTE_IDENTICAL` or `SEMANTICALLY_IDENTICAL` is required for approved equal-run fixtures.
- Meaningful text, table, image, coordinate, page, relationship, Markdown, or warning mutations must produce `MISMATCH`.
- Parser version, adapter version, or configuration changes must produce `ENVIRONMENT_MISMATCH`.
- Missing or invalid PDF/parser authority must produce `PARSER_FAILED` or a documented exit-code-2 authority failure.
- Existing output files must remain byte-for-byte unchanged.
- Raw source PDFs and parser artifacts must remain unchanged.
- Final PASS may be recorded only after manual local verification at the exact remote HEAD.

## Actions not authorized by this ledger

- Draft PR Ready conversion
- merge
- Issue #52 closure
- parent Issue #27 closure
