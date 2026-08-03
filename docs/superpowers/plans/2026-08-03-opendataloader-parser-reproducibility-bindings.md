# OpenDataLoader Reproducibility Implementation Bindings

> Document status: CURRENT

Issue: #52
Parent epic: #27
Applies to: `docs/superpowers/plans/2026-08-03-opendataloader-parser-reproducibility.md`

This document resolves implementation ambiguities found during plan self-review. It does not expand Issue #52 beyond OpenDataLoader warning collection and parser artifact reproducibility. Where this document conflicts with the implementation plan, this document is authoritative.

## 1. Parser run authority

Every parser artifact directory contains immutable `parser-run.json` with this exact version 1 contract:

```json
{
  "format": "evidence-review/opendataloader-parser-run",
  "version": 1,
  "source_relative_path": "inputs/original/reference.pdf",
  "source_sha256": "64 lowercase hexadecimal characters",
  "source_size": 12345,
  "source_page_count": 10,
  "document_id": "DOC-0123456789ABCDEF0123",
  "revision_id": "DOC-0123456789ABCDEF0123-0123456789ab",
  "parser_kind": "opendataloader",
  "parser_version": "1.2.3",
  "adapter_version": 1,
  "parser_configuration": {
    "markdown_with_html": true
  },
  "platform_family": "windows"
}
```

Rules:

- `source_relative_path` is canonical POSIX relative syntax with no absolute path, drive, backslash, empty component, `.` component, or `..` component.
- The source hash is lowercase in input authority. Canonical reports may use the repository's established digest casing consistently.
- `revision_id` must equal the repository revision identity derived from `document_id` and `source_sha256`.
- `source_size` and `source_page_count` are positive integers and Boolean values are rejected.
- Parser configuration SHA-256 is computed from existing canonical JSON bytes of `parser_configuration`.
- The sidecar is read-only evidence. Validation never rewrites it.

## 2. Independent source page-count verification

The reproducibility command receives the source PDF and must independently count its pages. Add runtime dependency:

```toml
dependencies = [
  "pypdf>=5,<6",
]
```

Implementation:

```python
from pypdf import PdfReader


def count_source_pdf_pages(path: Path) -> int:
    with path.open("rb") as stream:
        count = len(PdfReader(stream, strict=True).pages)
    if count < 1:
        raise ValueError("source PDF must contain at least one page")
    return count
```

The run manifest contains both:

```python
source_page_count: int
parser_page_count: int
```

Validation is `PARSER_FAILED` when any of these differ:

- actual PDF count versus `parser-run.json.source_page_count`;
- OpenDataLoader JSON page count versus `parser-run.json.source_page_count`;
- run A source page count versus run B source page count.

Encrypted, malformed, unreadable, or zero-page PDFs are `PARSER_FAILED`. No fallback regex page counter is permitted.

## 3. Warning collection CLI

Use the approved spec command shape. The main plan's temporary `--source` and `--run` wording for warning collection is superseded.

```powershell
evidence-review parser warnings collect `
  --source-manifest <source-batch-manifest.json> `
  --parser-artifacts <artifact-directory> `
  --config parser-reproducibility.json `
  --warning-output <warning-report.json> `
  --queue-output <review-queue.json>
```

Optional prior queue input:

```text
--previous-queue <parser-review-queue.json>
```

Resolution procedure:

1. Strictly decode the source-batch manifest using the existing contract.
2. Strictly decode `<artifact-directory>/parser-run.json`.
3. Select exactly one source item whose `source_path` equals `parser-run.json.source_relative_path`.
4. Require parser kind `OPENDATALOADER_JSON` in the source-batch manifest.
5. Derive or validate `document_id` and `revision_id` from the source item and sidecar source hash.
6. Require exact equality with sidecar `document_id` and `revision_id`.
7. Collect warnings from the selected artifact directory.

Failure conditions:

```text
SOURCE_MANIFEST_ENTRY_MISSING
SOURCE_MANIFEST_ENTRY_DUPLICATE
SOURCE_MANIFEST_PARSER_KIND_MISMATCH
SOURCE_IDENTITY_MISMATCH
SOURCE_REVISION_MISMATCH
PARSER_RUN_AUTHORITY_MISSING
PARSER_RUN_AUTHORITY_INVALID
```

These are exit code 2 authority/configuration errors. The command does not need a source-batch root because source bytes are not re-read during warning-only collection; source identity is cross-checked between the source-batch manifest and immutable parser run authority.

## 4. Reproducibility CLI

The reproducibility command remains:

```powershell
evidence-review parser reproducibility validate `
  --source <pdf> `
  --run-a <artifact-directory> `
  --run-b <artifact-directory> `
  --config parser-reproducibility.json `
  --output <report.json>
```

It verifies actual source bytes, size, and page count against both run sidecars before comparing parser artifacts.

## 5. Required plan changes during implementation

Task 1:

- `ParserRunMetadata` includes all source identity fields in Section 1.
- Add strict tests for source hash, size, page count, document ID, and revision ID.

Task 2:

- `ParserRunManifest` includes both `source_page_count` and `parser_page_count`.
- Add `pypdf>=5,<6` to `pyproject.toml`.
- Test malformed, encrypted, zero-page, and count-mismatch PDFs.

Task 8:

- Parser-shape and CLI tests use `--source-manifest` and `--parser-artifacts` for warning collection.
- Source-batch identity selection follows Section 3.

Task 10:

- Wheel installation must install and verify `pypdf` through `pip check`.
- Installed-wheel acceptance exercises independent source page counting.

## 6. Final consistency check

The implementation must preserve these signatures:

```python
def compare_parser_runs(
    pair: ParsedRunPair,
    config: ReproducibilityConfig,
) -> ComparisonResult:
    ...


def validate_opendataloader_reproducibility(
    source_pdf: Path,
    run_a_root: Path,
    run_b_root: Path,
    config: ReproducibilityConfig,
) -> ParserReproducibilityReport:
    ...
```

Warning collection may use this internal interface after source-manifest resolution:

```python
def collect_opendataloader_warnings(
    source_identity: SourceIdentity,
    run_root: Path,
    config: ReproducibilityConfig,
    previous_queue: ParserReviewQueue | None = None,
) -> WarningCollectionResult:
    ...
```
