# OpenDataLoader Parser Reproducibility

> Document status: CURRENT

Issue #52 adds an offline, read-only validator for OpenDataLoader parser warnings and two-run JSON/Markdown reproducibility. It does not run OpenDataLoader and never rewrites the source PDF or raw parser artifacts.

## Parser artifact directory

Each parser run directory contains:

```text
parser-output/
├─ parser-run.json
├─ document.json
├─ document.md
└─ parser.log        # optional warning source
```

`parser-run.json` is immutable execution authority. It records the source SHA-256, source byte size, source page count, document and revision identity, parser version, adapter version, parser configuration, and platform family.

`parser.log` is read-only input and remains byte-for-byte unchanged. Warning extraction accepts `WARN`, `WARNING`, `ERROR`, `SEVERE`, and `FATAL` severity lines, including timestamped Python log lines (`YYYY-MM-DD HH:MM:SS,mmm - LEVEL - message`) and `LEVEL: message` lines. On Korean Windows, OpenDataLoader's Java logger can localize `WARNING` as `경고` and `SEVERE` as `심각`; these exact aliases map to the corresponding canonical severity. The Java timestamp header line is ignored, and the following severity line is parsed. `INFO`, `DEBUG`, `TRACE`, `정보`, progress output, status headers, and blank lines are excluded. For timestamped Python lines, only the allowlisted timestamp and severity wrapper are removed from the warning fingerprint; the exact raw line is retained in the warning record.

## Reproducibility validation

```powershell
evidence-review parser reproducibility validate `
  --source <source.pdf> `
  --run-a <first-parser-output> `
  --run-b <second-parser-output> `
  --config parser-reproducibility.json `
  --output <fresh-report.json>
```

The validator independently reads the PDF with `pypdf`, verifies both run authorities, compares raw JSON and Markdown bytes, and then applies only the repository-owned `opendataloader-v1` comparison profile.

Statuses:

| Status | Meaning | Exit |
|---|---|---:|
| `BYTE_IDENTICAL` | Raw JSON, Markdown, and warning identity are identical. | 0 |
| `SEMANTICALLY_IDENTICAL` | Only approved execution metadata or run-local paths differ. | 0 |
| `MISMATCH` | Extracted content, page order, table data, image occurrence, coordinates, relationships, Markdown, or warnings differ. | 1 |
| `ENVIRONMENT_MISMATCH` | Parser version, adapter version, configuration, or required authority differs. No equivalence claim is made. | 2 |
| `PARSER_FAILED` | Source PDF or required parser authority/artifact is missing, malformed, unreadable, or inconsistent. | 3 |

Every report path is create-only. Use a new output path for each invocation.

## Warning collection

```powershell
evidence-review parser warnings collect `
  --source-manifest <source-batch.json> `
  --parser-artifacts <parser-output-directory> `
  --config parser-reproducibility.json `
  --warning-output <fresh-warning-report.json> `
  --queue-output <fresh-review-queue.json>
```

To carry forward immutable review history, add:

```text
--previous-queue <previous-parser-review-queue.json>
```

Warning-only collection does not reopen the PDF. It strictly binds one source-batch entry to `parser-run.json`, requires `OPENDATALOADER_JSON`, and verifies document and revision identity before reading warnings.

Warnings do not automatically mean parser failure. Every warning remains visible and creates or updates one `REVIEW_REQUIRED` queue entry. Unknown warnings retain their exact raw message and use `PARSER_WARNING_UNKNOWN`.

## Normalization boundary

The validator may normalize only:

- approved parser execution timestamp fields;
- approved output-directory metadata;
- run-local path values;
- UTF-8 BOM and CRLF/LF representation for canonical comparison.

It does not normalize extracted text whitespace, table formatting, bounding boxes, element order, page order, image identity, or arbitrary fields. Unexpected differences fail closed as `MISMATCH`.

## Manual acceptance

GitHub Actions is not an acceptance dependency for this repository. Final acceptance requires a clean exact HEAD and local results for:

```powershell
python -m pytest -v
python -m ruff check src tests
python -m mypy src
python -m compileall -q src scripts web_runtime tests
```

Build and install the wheel in an isolated Python 3.13 environment. Run `pip check`, verify the canonical and compatibility entry points, and execute the documented parser commands from the installed wheel. Record report and wheel SHA-256 values in the release acceptance record for the exact candidate HEAD.
