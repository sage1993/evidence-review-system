# OpenDataLoader Parser Warning and Reproducibility Design

> Document status: CURRENT

Issue: #52
Parent epic: #27
Approved: 2026-08-03

## 1. Purpose

The repository must be able to determine whether two OpenDataLoader parser runs over the same PDF are reproducible under the same parser version and configuration. It must also convert parser warnings into deterministic, traceable review evidence without modifying the source PDF or raw parser artifacts.

The subsystem distinguishes byte-for-byte reproducibility from semantic reproducibility. It permits only explicitly approved non-deterministic metadata to be normalized for comparison. Any unexpected difference in page order, text, tables, images, coordinates, element structure, or warning placement fails closed as a mismatch.

This work is the final P2 implementation unit under Issue #27. It is intentionally limited to OpenDataLoader parser warnings and parser artifact reproducibility.

## 2. Goals

The implementation must:

1. Record immutable run metadata for two OpenDataLoader parser outputs.
2. Compare raw JSON and Markdown bytes before applying any normalization.
3. Apply an explicit, versioned allowlist only to known non-deterministic metadata.
4. Produce deterministic canonical JSON reports for reproducibility, warnings, and review queue entries.
5. Detect meaningful differences in text, tables, images, coordinates, pages, warnings, and structural relationships.
6. Preserve every parser warning and associate it with document, revision, parser run, and page when available.
7. Deduplicate repeated warning queue entries through a stable key without deleting historical warning evidence.
8. Operate offline on Windows and Linux.
9. Support manual acceptance with isolated Python 3.11 and 3.13 wheel verification.

## 3. Non-goals

This work does not:

- modify OpenDataLoader or its extraction algorithms;
- rerun OCR automatically;
- merge, repair, clean, or rewrite raw parser JSON or Markdown;
- validate downstream evidence retrieval, citations, calculations, rules, abstention, or review packets;
- create a release-wide golden matrix;
- infer missing warning locations or warning meanings;
- treat the absence of warnings as proof that parsing is correct;
- allow arbitrary ignore rules, wildcard field deletion, or user-provided executable normalization code;
- use GitHub Actions as an acceptance dependency.

## 4. Approved policy decisions

The following decisions are fixed for Issue #52:

- The supported parser kind is `opendataloader` only.
- The same source SHA-256, parser version, adapter version, and configuration SHA-256 are required before reproducibility can be evaluated.
- Environment differences produce `ENVIRONMENT_MISMATCH`, not a false parser mismatch.
- Raw artifacts are compared first and are never changed.
- Semantic comparison uses a repository-owned, versioned allowlist.
- Unknown or newly observed differences are mismatches until reviewed and explicitly added to the allowlist through code and tests.
- Parser warnings do not make a parser run fail automatically. Every warning must remain visible and must create or update a deterministic review queue entry.
- Unknown warning text is preserved verbatim and classified as `PARSER_WARNING_UNKNOWN`.
- Persistent paths are canonical POSIX relative paths. Machine-specific absolute paths are prohibited in canonical reports.
- All report outputs are create-only.

## 5. Existing authority and boundaries

This design extends the Stage 1 source-preservation boundary described by:

- `AGENTS.md`;
- `skills/01-preserving-and-parsing-pdfs/SKILL.md`;
- the source-batch manifest and parser adapter registry;
- the repository canonical JSON and create-only output conventions.

Original PDFs and raw parser outputs remain evidence. The new subsystem reads them and writes independent validation artifacts. It must not become a parser-output cleanup layer.

The canonical Python implementation remains under the physical `ansim_review` source tree, with the public `evidence_review` namespace using the existing compatibility identity.

## 6. Architecture

The subsystem is isolated under:

```text
src/ansim_review/parser_reproducibility/
├─ __init__.py
├─ contract.py
├─ paths.py
├─ run_manifest.py
├─ opendataloader.py
├─ normalization.py
├─ warnings.py
├─ comparison.py
├─ queue.py
├─ report.py
└─ cli.py
```

Responsibilities:

- `contract.py` defines strict immutable config, run, warning, difference, queue, and report models.
- `paths.py` validates roots and produces safe POSIX relative paths.
- `run_manifest.py` verifies source and artifact files and constructs parser run manifests.
- `opendataloader.py` decodes supported OpenDataLoader JSON/Markdown artifact layouts without rewriting them.
- `normalization.py` applies the versioned allowlist to in-memory comparison values only.
- `warnings.py` extracts and normalizes warnings while preserving raw warning text.
- `comparison.py` performs raw and canonical comparisons and emits structural differences.
- `queue.py` creates deterministic warning review queue entries and deduplicates by stable key.
- `report.py` sorts, deduplicates, and encodes canonical JSON reports.
- `cli.py` exposes create-only commands and stable exit codes.

The core comparison API does not write files:

```python
def validate_opendataloader_reproducibility(
    source_pdf: Path,
    run_a_root: Path,
    run_b_root: Path,
    config: ReproducibilityConfig,
) -> ParserReproducibilityReport:
    ...
```

Warning collection is independently callable:

```python
def collect_opendataloader_warnings(
    source_pdf: Path,
    run_root: Path,
    config: ReproducibilityConfig,
) -> ParserWarningReport:
    ...
```

## 7. Configuration contract

The repository authority file is:

```text
parser-reproducibility.json
```

Version 1 contract:

```json
{
  "format": "evidence-review/parser-reproducibility-config",
  "version": 1,
  "parser_kind": "opendataloader",
  "adapter_version": 1,
  "json_artifact_names": ["document.json"],
  "markdown_artifact_names": ["document.md"],
  "warning_sources": ["document.json", "parser.log"],
  "normalization_profile": "opendataloader-v1",
  "allowed_nondeterministic_fields": [
    "$.metadata.parsed_at",
    "$.metadata.output_directory"
  ]
}
```

### 7.1 Strict decoding

The decoder rejects:

- duplicate JSON keys;
- unknown top-level fields;
- unsupported format or version;
- parser kinds other than `opendataloader`;
- unsupported adapter or normalization profile versions;
- empty artifact names;
- absolute artifact names;
- backslash paths;
- `.` or `..` path components;
- duplicate artifact names or allowlist entries;
- wildcard JSON paths;
- recursive JSON paths;
- allowlist paths not supported by the selected normalization profile.

The v1 allowlist is closed. Configuration may select from fields implemented by `opendataloader-v1`; it cannot introduce arbitrary field deletion.

## 8. Parser run manifest

Each run manifest uses:

```text
evidence-review/parser-run-manifest
```

version 1 and records:

```text
source_sha256
source_size
source_page_count
parser_kind
parser_version
adapter_version
configuration_sha256
platform_family
json_relative_path
json_sha256
json_size
markdown_relative_path
markdown_sha256
markdown_size
warning_source_relative_paths
warning_count
warning_codes
parser_page_count
```

The manifest may record execution metadata such as the operating system and Python version, but execution timestamps and absolute paths are excluded from equality decisions and canonical persistent identifiers.

A run manifest is invalid when:

- source bytes do not match the declared SHA-256;
- a required artifact is missing;
- an artifact path escapes the run root;
- JSON or Markdown cannot be decoded under the required encoding;
- parser page count cannot be reconciled with the source page count;
- parser version or configuration identity is absent.

## 9. Reproducibility statuses

The report status is exactly one of:

### 9.1 `BYTE_IDENTICAL`

- run environment identity matches;
- raw JSON bytes match;
- raw Markdown bytes match;
- normalized warning collections match.

### 9.2 `SEMANTICALLY_IDENTICAL`

- run environment identity matches;
- one or both raw artifacts differ;
- after the approved normalization profile, canonical JSON and Markdown match;
- normalized warning collections match;
- every raw difference is attributable to an allowed non-deterministic field or approved path representation normalization.

### 9.3 `MISMATCH`

At least one meaningful difference exists, including:

- page count or page order;
- text content or text order;
- table structure, row, column, span, or cell value;
- image occurrence, source reference, or placement;
- bounding box, coordinate system, or page association;
- element type, ID relationship, parent/child order, previous/next relationship;
- Markdown body, table, image link, or section order;
- warning presence, code, page, or normalized message;
- any unknown raw difference outside the allowlist.

### 9.4 `ENVIRONMENT_MISMATCH`

The source SHA-256 may match, but at least one required execution identity differs:

- parser version;
- adapter version;
- parser configuration SHA-256;
- normalization profile version.

No semantic equivalence claim is made in this status.

### 9.5 `PARSER_FAILED`

A required parser artifact is missing, unsafe, unreadable, malformed, or internally inconsistent. The report includes deterministic failure findings and makes no reproducibility claim.

## 10. Normalization policy

### 10.1 Comparison-only behavior

Normalization operates on decoded in-memory values. It never writes a normalized replacement beside or over the raw parser output.

The report records:

- raw hashes;
- canonical hashes;
- normalization profile;
- every field path normalized;
- the before/after value category, without leaking prohibited absolute machine paths into the canonical report.

### 10.2 V1 allowed differences

The initial `opendataloader-v1` profile may normalize only values proven by fixtures to be operational metadata rather than extracted evidence:

- parser execution timestamp fields;
- output-directory fields that contain only the run root;
- path separators within approved run-local artifact references;
- run-root prefixes in approved run-local paths.

Normalization must not change:

- document title or source file name;
- page number or page count;
- element IDs unless the exact field is separately approved in a future profile version;
- content, table values, image identifiers, bounding boxes, coordinates, order, or relationships;
- warning text except for line-ending and path-separator normalization explicitly covered below.

### 10.3 Text normalization

JSON strings and Markdown body text are not generally whitespace-normalized. The only text-level normalization permitted in v1 is:

- UTF-8 BOM removal at decode boundary when present;
- CRLF to LF for canonical comparison;
- replacement of an approved run-root path prefix with `<RUN_ROOT>`;
- backslash to slash conversion inside an approved run-local path value.

Trailing spaces, blank-line counts, heading order, table formatting, and content whitespace remain meaningful unless a future profile explicitly proves otherwise.

## 11. Structural comparison

The comparison engine produces stable difference records:

```json
{
  "kind": "TABLE_CELL_VALUE_CHANGED",
  "artifact": "document.json",
  "page_number": 7,
  "path": "$.pages[6].elements[12].rows[2].cells[4].content",
  "left_hash": "...",
  "right_hash": "..."
}
```

Difference records contain hashes or bounded summaries rather than duplicating large extracted content. They are sorted by:

1. artifact type;
2. page number, with document-level findings first;
3. canonical structural path;
4. difference kind;
5. left hash;
6. right hash.

Representative difference kinds include:

```text
PAGE_COUNT_CHANGED
PAGE_ORDER_CHANGED
ELEMENT_ADDED
ELEMENT_REMOVED
ELEMENT_TYPE_CHANGED
TEXT_CONTENT_CHANGED
TABLE_STRUCTURE_CHANGED
TABLE_CELL_VALUE_CHANGED
IMAGE_OCCURRENCE_CHANGED
BOUNDING_BOX_CHANGED
RELATIONSHIP_CHANGED
MARKDOWN_CONTENT_CHANGED
WARNING_ADDED
WARNING_REMOVED
WARNING_CHANGED
UNAPPROVED_NONDETERMINISM
```

## 12. Warning contract

Warning artifacts use:

```text
evidence-review/parser-warning-report
```

version 1.

A canonical warning records:

```text
warning_id
severity
code
document_id
revision_id
source_sha256
parser_kind
parser_version
configuration_sha256
page_number
raw_source_relative_path
raw_location
raw_message
normalized_message_sha256
```

### 12.1 Warning taxonomy

The v1 taxonomy is:

```text
PARSER_WARNING_TEXT_EXTRACTION
PARSER_WARNING_TABLE_EXTRACTION
PARSER_WARNING_IMAGE_EXTRACTION
PARSER_WARNING_LAYOUT
PARSER_WARNING_PAGE
PARSER_WARNING_UNKNOWN
```

Classification is based only on explicit, tested OpenDataLoader warning forms. No warning is discarded when classification fails.

### 12.2 Warning identity

The stable warning ID is derived from:

```text
source_sha256
parser_kind
parser_version
configuration_sha256
page_number or document-level sentinel
warning code
normalized message SHA-256
```

The raw message is preserved. Line endings and approved run-root path values may be normalized only for identity hashing.

## 13. Review queue contract

The review queue uses:

```text
evidence-review/parser-review-queue
```

version 1.

Each queue entry records:

```text
queue_id
status = REVIEW_REQUIRED
warning_id
document_id
revision_id
source_sha256
parser_version
configuration_sha256
page_number
warning_code
first_seen_run_id
last_seen_run_id
occurrence_count
```

The stable queue key is:

```text
source_sha256 + parser_version + configuration_sha256 + page + warning_code + normalized_message_sha256
```

Repeated collection increments `occurrence_count` and updates `last_seen_run_id` in the newly generated queue artifact. It does not emit duplicate queue entries.

A warning that disappears in a later run is not deleted from historical evidence. The current comparison report records `WARNING_REMOVED`, while prior queue artifacts remain immutable.

## 14. CLI design

The canonical commands are:

```powershell
evidence-review parser reproducibility validate `
  --source <pdf> `
  --run-a <artifact-directory> `
  --run-b <artifact-directory> `
  --config parser-reproducibility.json `
  --output <report.json>
```

```powershell
evidence-review parser warnings collect `
  --source-manifest <source-batch-manifest.json> `
  --parser-artifacts <artifact-directory> `
  --config parser-reproducibility.json `
  --warning-output <warning-report.json> `
  --queue-output <review-queue.json>
```

The commands are also exposed through:

```text
python -m evidence_review ...
python -m ansim_review ...
```

### 14.1 Create-only outputs

- Every output path must not exist.
- If any requested output exists, the command exits before writing any output.
- Multi-output warning collection uses an all-or-nothing preflight.
- Concurrent creation is handled with exclusive file creation.
- Partial temporary files are removed on failure.

### 14.2 Exit codes

```text
0 = BYTE_IDENTICAL, SEMANTICALLY_IDENTICAL, or warning collection completed
1 = MISMATCH
2 = usage, configuration, unsafe path, existing output, or ENVIRONMENT_MISMATCH
3 = PARSER_FAILED or unreadable required artifact
```

`ENVIRONMENT_MISMATCH` is reported as a completed report when the output path is valid, but its process exit is 2 because the requested reproducibility comparison was not valid.

## 15. Canonical reports

The reproducibility report uses:

```text
evidence-review/parser-reproducibility-report
```

version 1 and includes:

- status;
- source identity;
- run manifest summaries;
- raw JSON and Markdown hashes;
- canonical JSON and Markdown hashes;
- normalization profile and applied normalization paths;
- warning counts and hashes;
- structural difference records;
- error and warning counts;
- stable summary text.

Canonical encoding follows existing repository conventions:

- UTF-8 without BOM;
- LF line endings;
- sorted object keys;
- deterministic list ordering;
- no absolute paths;
- no timestamps in equality-sensitive output;
- trailing newline;
- duplicate finding elimination.

## 16. Fixtures

At least three checked-in or deterministically generated fixtures are required:

1. **Text fixture** — selectable text with headings and multiple pages.
2. **Table fixture** — at least one multi-row, multi-column table with coordinates.
3. **Warning fixture** — a layout, image, table, or page condition that produces a stable OpenDataLoader warning or a captured real parser warning artifact.

Large source PDFs are not added merely to satisfy tests. When licensing, size, or parser-runtime constraints prevent checking in the original PDF, the repository stores a minimal lawful fixture plus captured raw parser artifacts and their provenance hashes.

Fixture metadata records:

- source SHA-256;
- parser version;
- parser command or configuration identity;
- artifact hashes;
- expected warning codes;
- expected reproducibility status.

## 17. Test strategy

### 17.1 Contract tests

- strict config decoding;
- duplicate key rejection;
- unknown field rejection;
- unsafe path rejection;
- unsupported parser/profile rejection;
- canonical report round trip;
- create-only output protection.

### 17.2 Normalization tests

- approved timestamp difference becomes `SEMANTICALLY_IDENTICAL`;
- approved run-root path difference becomes `SEMANTICALLY_IDENTICAL`;
- Windows and POSIX run-local path forms compare equally;
- unapproved field difference becomes `MISMATCH`;
- normalization never changes raw files;
- normalization paths are fully reported.

### 17.3 Structural mismatch tests

- one text character changed;
- table cell changed;
- bounding box changed;
- page order changed;
- element added or removed;
- image occurrence changed;
- relationship changed;
- Markdown content changed;
- warning added, removed, changed, or moved to another page.

Each case must produce the expected stable difference kind and exit code.

### 17.4 Warning and queue tests

- known warning classifications;
- unknown warning raw text preservation;
- document-level and page-level warnings;
- repeated warning collection produces one queue entry;
- queue ordering and IDs are deterministic;
- warning disappearance produces comparison evidence without rewriting history.

### 17.5 Determinism tests

- report generation repeated in one root is byte-identical;
- equivalent Windows and POSIX roots produce byte-identical canonical reports;
- finding and difference ordering is stable;
- fresh installed wheels produce the same canonical report SHA-256 for the same fixtures.

### 17.6 Full manual acceptance

From a clean local and remote HEAD:

- documentation integrity report PASS;
- Issue #52 targeted tests PASS;
- full pytest PASS;
- Ruff PASS;
- strict mypy PASS;
- compileall PASS;
- `git diff --check` PASS;
- Python 3.11 wheel build, isolated install, `pip check`, CLI help, and fixture validation PASS;
- Python 3.13 wheel build, isolated install, `pip check`, CLI help, and fixture validation PASS;
- two fresh reports have identical SHA-256;
- final worktree is clean.

GitHub Actions is excluded from the acceptance decision. Local/manual results must not be described as GitHub Actions PASS.

## 18. Error handling and fail-closed behavior

The subsystem must fail closed when:

- source or artifact hashes cannot be computed;
- source identity differs between runs;
- parser identity is missing;
- required JSON or Markdown is absent;
- paths are unsafe;
- JSON is malformed or contains duplicate keys where strict decoding is required;
- page count is inconsistent;
- canonical normalization encounters an unsupported value shape;
- an output already exists;
- a structural difference cannot be classified safely.

An unclassifiable difference is `UNAPPROVED_NONDETERMINISM` and produces `MISMATCH`.

## 19. Security and offline requirements

- No network requests are permitted.
- No command found inside parser artifacts or Markdown is executed.
- Symbolic links escaping the approved roots are rejected.
- ZIP or archive extraction is outside this subsystem; provided artifact directories must already exist.
- Reports must not persist credentials, environment variables, user profile paths, or temporary directory names.
- Warning text is treated as untrusted data and never rendered as executable markup by the validator.

## 20. Integration boundaries

Issue #52 integrates with source-batch identity and parser adapter metadata but does not change source-batch ingestion semantics.

A future source-batch or release integration may consume the reports. Issue #52 itself does not make reproducibility a release gate. It establishes the deterministic contract and CLI required for that future decision.

Warnings may be imported into later review workflows, but this implementation stops at producing the canonical review queue artifact.

## 21. Delivery sequence

Implementation should proceed in this order:

1. strict config and report contracts;
2. safe paths and run manifest construction;
3. OpenDataLoader JSON/Markdown adapter;
4. raw byte comparison;
5. allowlist normalization profile;
6. structural comparison and difference taxonomy;
7. warning extraction and canonical taxonomy;
8. deterministic review queue;
9. create-only CLI;
10. real fixture matrix;
11. full manual acceptance and acceptance ledger;
12. parent Issue #27 status update.

## 22. Acceptance evidence

Issue #52 stores its final acceptance record under:

```text
docs/acceptance/issue-52/README.md
```

The record must include:

- exact implementation and evidence HEADs;
- operating system and Python versions;
- OpenDataLoader parser version;
- source and configuration SHA-256 values;
- raw and canonical artifact SHA-256 values;
- final reproducibility statuses;
- warning and review queue counts;
- targeted and full test results;
- Ruff, mypy, compileall, and diff-check results;
- Python 3.11 and 3.13 wheel hashes and installed-wheel validation results;
- explicit confirmation that GitHub Actions was excluded from acceptance;
- human review and merge state.

## 23. Completion criteria

Issue #52 is complete only when:

1. the approved OpenDataLoader fixture runs are reproducibly classified;
2. meaningful JSON/Markdown changes fail as `MISMATCH`;
3. only approved non-deterministic metadata can produce `SEMANTICALLY_IDENTICAL`;
4. warnings are preserved and deterministic review queue entries are produced without duplication;
5. canonical outputs are byte-identical across repeated runs and equivalent Windows/POSIX roots;
6. all local/manual acceptance gates pass on the exact final HEAD;
7. the acceptance ledger is committed and rechecked;
8. human review passes before Ready transition or merge;
9. Issue #27 is updated with the result and remaining epic closure work.
