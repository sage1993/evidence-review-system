# Drawing Evidence Backend Design

**Date:** 2026-08-02  
**Issue:** #6  
**Depends on:** #15 / PR #16  
**Approved approach:** Contract-first backend before automatic drawing recognition or browser UI

## 1. Purpose

Implement the first backend milestone for case-specific drawing evidence. The system must receive user-provided drawing files, copy them into immutable case storage, evaluate whether they are safe and usable, store extractor or reviewer-created candidates, append reviewer confirmations without overwrite, generate confirmed inputs, and expose only confirmed inputs to deterministic Math and Rule Engine bindings.

This milestone must remain useful even when automatic drawing recognition finds nothing. A reviewer must be able to create a manual annotation, confirm its value or geometry, and produce a traceable engine input.

## 2. Scope

### 2.1 In scope

- Case-specific drawing workspace and manifest
- Immutable source ingest for PDF, PNG, TIFF, and JPEG
- File role preservation using the existing immutable attachment contract
- File size, page count, and pixel-count resource limits
- Symlink, junction-like path indirection, directory, and overwrite rejection
- MIME sniffing based on file signatures rather than extension alone
- Drawing quality assessment using the M0 quality and physical-size-trust contracts
- Candidate persistence using the M0 geometry, origin, and status contracts
- Conversion of existing parser elements into explicit extractor candidates
- Reviewer-created manual candidates with stable annotation IDs
- Append-only confirmation records
- Confirmation hash verification
- Confirmed-input generation and conflict checks
- Engine-binding adapter that accepts only validated confirmed inputs
- Workflow projection for `INPUT_CONFIRMATION_REQUIRED`, `READY_TO_EVALUATE`, `BLOCKED`, or `FAILED`
- Deterministic JSON serialization and golden fixtures
- Unit and integration tests

### 2.2 Out of scope

- OCR implementation
- Automatic title-block interpretation
- Automatic dimension-line recognition
- Automatic table reconstruction
- Automatic site boundary, building outline, road boundary, vehicle entrance, or setback recognition
- Browser drawing viewer or annotation UI
- Calibration arithmetic
- DWG or DXF parsing
- Review Packet HTML rendering changes
- New external model or OpenAI API calls
- Treating case drawings as reusable reference-document evidence in `evidence.sqlite`

## 3. Architectural decision

The backend is split into small deterministic services. Contract objects from `ansim_review.contracts.drawing` remain the only public drawing data model. Parsing modules must consume and produce those contracts rather than define duplicate enums or schemas.

```text
External upload path
  -> Source Intake Policy
  -> Immutable Source Store
  -> Source Manifest
  -> Quality Gate
  -> Candidate Repository
       -> extractor candidate adapter
       -> reviewer manual annotation
  -> Append-only Confirmation Store
  -> Confirmed Input Builder
  -> Engine Binding Adapter
```

No downstream service may reopen or trust the original external upload path after immutable ingest succeeds.

## 4. Case workspace

Each case uses the following structure:

```text
cases/<case_id>/
├─ manifest.json
├─ sources/
│  └─ drawings/
│     └─ <attachment_id>.<canonical_extension>
├─ candidates/
│  └─ <candidate_id>.json
├─ confirmations/
│  └─ <timestamp>-<reviewer>-<confirmation_id>.json
└─ confirmed-inputs.json
```

### 4.1 Case ID and path rules

- `case_id` must be a non-empty safe identifier.
- Generated paths must be relative to the case root.
- `..`, absolute paths, drive-prefixed paths, NUL bytes, and empty path components are rejected.
- Existing files must never be replaced.
- Directories and symbolic links are rejected as source inputs.
- The case root is resolved before any write, and every destination must remain inside that resolved root.

### 4.2 Manifest responsibilities

`manifest.json` records:

- format and version
- case ID
- immutable source attachments
- source-role declarations
- quality assessments
- candidate index entries
- confirmation index entries
- confirmed-input document hash

The manifest is a deterministic projection of canonical records. Operational timestamps remain in append-only envelopes and are not used when computing deterministic payload hashes.

## 5. Source intake

### 5.1 Intake sequence

1. Validate the external source path without following symbolic links.
2. Reject directories, symlinks, unsupported file types, and policy-limit violations that can be determined before copying.
3. Create a new immutable destination under `sources/drawings/`.
4. Copy bytes without modifying, transcoding, rotating, or resaving the source.
5. Compute SHA-256 and byte size from the copied destination.
6. Sniff MIME from copied bytes.
7. Verify extension, MIME, and declared role compatibility.
8. Record the immutable attachment and source manifest entry.
9. Never use the external path as runtime authority again.

### 5.2 Supported MIME signatures

MVP signature detection supports:

- PDF: `%PDF-`
- PNG: standard 8-byte PNG signature
- TIFF: little-endian and big-endian TIFF signatures
- JPEG: JPEG SOI marker

An extension/MIME mismatch is rejected. Unknown signatures are rejected rather than guessed.

### 5.3 Intake policy

The default versioned policy is:

```text
policy_id: DRAWING-INTAKE-1
max_file_bytes: 262144000
max_pdf_pages: 200
max_image_pixels: 150000000
max_case_image_pixels: 500000000
```

Policy values are explicit data and are included in assessment outputs. Tests may inject smaller limits.

### 5.4 Parser isolation boundary

This milestone defines the parser execution boundary but does not add a new PDF or image parser dependency.

- Page count and pixel metadata may be provided by a trusted adapter result.
- Adapter results must include source SHA-256.
- Adapter results with a mismatched source hash are rejected.
- Parser timeout, memory-limit, or malformed-output failures become quality reason codes rather than unhandled process termination.
- Embedded PDF JavaScript, file attachments, actions, and links are not executed or imported as evidence.

## 6. Drawing quality gate

The quality gate returns the existing `DrawingQualityAssessment` contract.

### 6.1 Quality statuses

- `PASS`: safe and sufficiently trusted for candidate review
- `REVIEW_REQUIRED`: source can be stored and reviewed, but physical size, image quality, or metadata requires reviewer confirmation
- `REJECTED`: unsafe, corrupt, unsupported, or beyond resource limits

### 6.2 Physical-size trust

- `PDF_MEDIABOX_VERIFIED`
- `USER_CONFIRMED`
- `METADATA_ONLY`
- `UNKNOWN`

`METADATA_ONLY` must never automatically produce `PASS`.

### 6.3 Minimum reason codes

- `UNSUPPORTED_MIME`
- `MIME_EXTENSION_MISMATCH`
- `FILE_SIZE_LIMIT_EXCEEDED`
- `PDF_PAGE_LIMIT_EXCEEDED`
- `IMAGE_PIXEL_LIMIT_EXCEEDED`
- `CASE_PIXEL_LIMIT_EXCEEDED`
- `DECOMPRESSION_BOMB_RISK`
- `PARSER_TIMEOUT`
- `PARSER_MEMORY_LIMIT`
- `PARSER_OUTPUT_INVALID`
- `SOURCE_HASH_MISMATCH`
- `UNKNOWN_PHYSICAL_SIZE`
- `METADATA_ONLY_PHYSICAL_SIZE`
- `LOSSY_OR_SCREEN_CAPTURE_SOURCE`
- `DRAWING_CONFIRMATION_REQUIRED`

Reason codes are quality data, not workflow states and not human decisions.

## 7. Candidate repository

### 7.1 Contract reuse

All candidates use `DrawingCandidate` from the M0 contracts. No new candidate status, geometry type, coordinate-system type, or origin enum may be introduced.

### 7.2 Extractor candidates

Existing parser elements may become extractor candidates when they have:

- immutable source SHA-256
- positive page number
- explicit candidate type
- geometry or a valid bbox convertible to `BBOX`
- extractor name and version

The adapter must not infer legal meaning from generic parser content. It may map explicit parser element types to neutral candidate types such as `TEXT_ELEMENT`, `TABLE_ELEMENT`, or `VECTOR_ELEMENT`. Domain-specific types require a dedicated extractor output or reviewer choice.

### 7.3 Manual candidates

A reviewer may create a candidate when automatic detection fails.

Manual candidates must use:

```text
origin: REVIEWER_MANUAL
status: CREATED
annotation_id: required stable identifier
extractor: null
extractor_version: null
```

Manual candidates still require source SHA-256, page, candidate type, and one of the approved geometry types.

### 7.4 Candidate persistence

- One canonical JSON file per candidate
- Candidate ID is stable and deterministic from case/source/page/origin sequence inputs
- Duplicate candidate IDs are rejected
- Existing candidate files are immutable
- A status-changing reviewer action is represented in a confirmation record, not by rewriting the original candidate file

## 8. Confirmation store

### 8.1 Append-only rule

Every reviewer action is stored as a new canonical JSON document under `confirmations/`. Existing confirmation files are never changed or replaced.

### 8.2 Validation

Before a confirmation is accepted:

- candidate exists
- candidate ID matches
- source SHA-256 matches the immutable case source
- action is allowed by the M0 contract
- reviewer is non-empty
- timestamp is explicit and parseable
- `EDITED` or `CREATED` includes a confirmed value, replacement geometry, or both
- `REJECTED` cannot produce a confirmed input
- referenced geometry remains on the same source page and coordinate system

### 8.3 Confirmation hash

The canonical confirmation payload is SHA-256 hashed. Confirmed inputs store both the relative confirmation path and confirmation SHA-256. Any later mismatch blocks binding.

## 9. Confirmed input builder

### 9.1 Bindable candidate statuses

Only:

- `ACCEPTED`
- `EDITED`
- `CREATED`

may produce a `ConfirmedInput`.

`UNCONFIRMED`, `REJECTED`, and `CONFLICT` always fail.

### 9.2 Build requirements

The builder verifies:

- candidate and confirmation source hashes match the immutable source
- candidate ID or annotation ID matches the confirmation target
- candidate status is bindable
- confirmation action and effective candidate status are consistent
- value is a finite decimal string
- unit is non-empty
- page and geometry are present
- confirmation file exists inside `confirmations/`
- confirmation hash matches
- input ID and field are non-empty

### 9.3 Conflict policy

A confirmed-input set is invalid when the same field has multiple active confirmed values with different value/unit pairs or incompatible geometries.

Conflict output must not choose a winner. It returns a deterministic error set and projects:

```text
workflow_state: INPUT_CONFIRMATION_REQUIRED
reason_code: SOURCE_CONFLICT or DRAWING_CONFIRMATION_REQUIRED
```

## 10. Engine binding adapter

The adapter accepts only decoded `ConfirmedInput` objects whose evidence files and hashes have been reverified.

Output is a deterministic mapping from field name to decimal string and unit metadata. It does not calculate derived values.

```text
DrawingCandidate
  -> DrawingConfirmation
  -> ConfirmedInput
  -> engine input mapping
```

Direct candidate-to-engine binding is prohibited.

## 11. Workflow projection

- No drawing source: `PENDING_DRAWING_INGESTION`
- Source rejected: `BLOCKED` with quality reason codes when resumable, otherwise `FAILED`
- Candidates exist but required inputs are not confirmed: `INPUT_CONFIRMATION_REQUIRED`
- Conflicting confirmations: `INPUT_CONFIRMATION_REQUIRED`
- All required confirmed inputs validate: `READY_TO_EVALUATE`

This milestone writes only workflow state documents. It does not produce a human decision or finalizer result.

## 12. Determinism

Deterministic artifacts:

- immutable source hash and manifest entry
- quality assessment for identical source metadata and policy
- candidate JSON
- confirmation payload excluding operational filename
- confirmed-input JSON
- engine-binding mapping
- validation error ordering

Operational data kept separate:

- reviewer timestamp
- confirmation filename timestamp
- temporary intake path
- process ID
- parser worker timing

All deterministic JSON uses the existing canonical JSON utilities.

## 13. Error handling

Expected validation errors use structured codes and do not leave partial files.

- Intake copies to a temporary file inside the case root and atomically publishes only after validation.
- Failed source intake removes the unpublished temporary file.
- Candidate and confirmation writes use create-only semantics.
- Confirmed-input generation writes only after all inputs validate as a set.
- Parser errors are captured into quality assessment records.
- Hash mismatch, path escape, and overwrite attempts fail closed.

## 14. Security requirements

- No network access
- No execution of embedded PDF actions or scripts
- No archive extraction
- No image allocation from untrusted dimensions before pixel-limit validation
- No following symbolic links
- No external-path authority after immutable ingest
- No overwrite of source, candidate, confirmation, or confirmed-input artifacts
- No model-generated confirmation or engine input
- No source role inferred as authoritative without user-declared role

## 15. Testing strategy

### 15.1 Unit tests

- safe case IDs and paths
- symlink and directory rejection
- overwrite refusal
- signature-based MIME detection
- extension/MIME mismatch
- file size, page, image-pixel, and case-pixel limits
- `METADATA_ONLY + PASS` rejection
- parser failure reason-code mapping
- extractor/manual candidate separation
- all four geometry types
- candidate create-only persistence
- append-only confirmation persistence
- candidate/source/confirmation hash mismatch
- action/status consistency
- confirmed-input decimal validation
- conflict detection
- unconfirmed/conflict engine-binding rejection

### 15.2 Integration tests

Primary success path:

```text
PNG or PDF received
  -> immutable source stored
  -> quality assessment produced
  -> no useful automatic candidate
  -> reviewer creates manual LINESTRING or POLYGON
  -> reviewer confirms value or geometry
  -> confirmed-inputs.json generated
  -> engine binding succeeds
```

Primary blocked path:

```text
source stored
  -> candidate remains UNCONFIRMED
  -> engine binding rejected
  -> INPUT_CONFIRMATION_REQUIRED
```

Tamper path:

```text
confirmation file modified after confirmed input generation
  -> confirmation hash mismatch
  -> binding rejected
```

### 15.3 Regression and quality checks

- Existing 158-test baseline remains green
- New deterministic fixtures are byte-equivalent across repeated runs
- `pytest -v`
- `ruff check src tests`
- `mypy src`
- `python -m compileall -q src scripts web_runtime tests`

## 16. Planned modules

```text
src/ansim_review/parsing/drawing_source.py
src/ansim_review/parsing/drawing_quality.py
src/ansim_review/parsing/drawing_candidates.py
src/ansim_review/parsing/drawing_confirmation.py
src/ansim_review/parsing/drawing_inputs.py
src/ansim_review/parsing/drawing_binding.py
src/ansim_review/parsing/drawing_workflow.py
```

Tests:

```text
tests/unit/parsing/test_drawing_source.py
tests/unit/parsing/test_drawing_quality.py
tests/unit/parsing/test_drawing_candidates.py
tests/unit/parsing/test_drawing_confirmation.py
tests/unit/parsing/test_drawing_inputs.py
tests/unit/parsing/test_drawing_binding.py
tests/integration/drawing/test_manual_annotation_flow.py
tests/integration/drawing/test_drawing_tamper_detection.py
```

Schemas must reuse the M0 schema documents. A new case-manifest schema may be added, but drawing candidate, confirmation, geometry, quality, and confirmed-input schemas must not be duplicated.

## 17. Acceptance criteria

- A supported drawing is copied to immutable case storage before processing.
- The runtime never uses the external upload path after ingest.
- Unsafe or over-limit inputs fail without partial published artifacts.
- Quality results use only M0 quality and trust enums.
- Automatic parser failure does not prevent manual annotation.
- Manual `CREATED` candidates support `POINT`, `BBOX`, `LINESTRING`, and `POLYGON`.
- Confirmation records are append-only and hash-bound.
- Only validated `ACCEPTED`, `EDITED`, or `CREATED` values become confirmed inputs.
- Conflicts and unconfirmed values cannot bind to engines.
- The complete manual-annotation success path passes without OCR or automatic boundary detection.
- Existing tests and all new checks pass.

## 18. Follow-up milestones

After this backend is merged:

1. Add browser drawing review and manual annotation UI.
2. Add calibration workflows and Math Engine formulas.
3. Add staged automatic candidate extractors:
   - stage 1: title block, drawing number, revision, scale text, dimension text, area table, room/zone label
   - stage 2: dimension line, road-width text, north arrow
   - stage 3: site boundary, road boundary, building outline, vehicle entrance, setback line
4. Integrate confirmed drawing evidence into Review Packet v2 rendering.
