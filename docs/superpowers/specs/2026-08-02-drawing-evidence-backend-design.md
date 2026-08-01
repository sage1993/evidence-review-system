# Drawing Evidence Backend Design

**Date:** 2026-08-02  
**Issue:** #6  
**Depends on:** #15 / PR #16  
**Approved approach:** Contract-first backend before automatic drawing recognition or browser UI

## 1. Purpose

Implement the first backend milestone for case-specific drawing evidence. The system receives user-provided drawing files, copies them into immutable case storage, evaluates safety and usability, stores extractor or reviewer-created candidates, appends reviewer confirmations without overwrite, generates confirmed inputs, and exposes only confirmed inputs to deterministic Math and Rule Engine bindings.

The milestone must remain useful when automatic drawing recognition finds nothing. A reviewer must be able to create a manual annotation, confirm its value or geometry, and produce a traceable engine input.

## 2. Scope

### 2.1 In scope

- Case-specific drawing workspace and versioned manifest
- Immutable source ingest for PDF, PNG, TIFF, and JPEG
- File role preservation through the existing immutable attachment contract
- File-size, PDF-page, per-image-pixel, and per-case-pixel limits
- Directory, symlink, Windows reparse-point, path-escape, and overwrite rejection
- MIME sniffing from file signatures instead of extension alone
- Drawing quality assessment through the M0 quality and physical-size-trust contracts
- Candidate persistence through the M0 geometry, origin, and status contracts
- Neutral conversion of existing parser elements into extractor candidates
- Reviewer-created manual candidates with stable annotation IDs
- Append-only confirmation records and confirmation hash verification
- Confirmed-input generation, set-level conflict detection, and engine binding
- Workflow projection using only M0 workflow states and reason codes
- Deterministic canonical JSON and golden fixtures
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

## 3. Architecture

Contract objects from `ansim_review.contracts.drawing` remain the only public drawing data model. Parsing modules consume and produce those contracts and must not define duplicate drawing enums or schemas.

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

No downstream service may reopen or trust the original upload path after immutable ingest succeeds.

## 4. Case workspace

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

### 4.1 Identifier and path rules

- `case_id`, attachment IDs, candidate IDs, annotation IDs, confirmation IDs, and reviewer filename tokens must match `[A-Za-z0-9][A-Za-z0-9_-]{0,127}`.
- User-facing reviewer names may remain Unicode inside JSON, but filename tokens use a separately validated ASCII identifier.
- Generated artifact paths are relative to the resolved case root.
- Absolute paths, drive-prefixed paths, `..`, NUL bytes, empty components, and backslash-based alternate paths are rejected.
- Source inputs that are directories, symbolic links, or Windows reparse points are rejected before opening.
- Every destination is resolved or constructed from validated components and must remain under the case root.
- Existing artifacts are never replaced.

### 4.2 Manifest responsibilities

`manifest.json` records:

- `format` and `version`
- case ID
- immutable source attachments
- declared source roles
- source metadata and intake policy ID
- quality assessments
- candidate index entries
- confirmation index entries
- confirmed-input document hash

The manifest is a deterministic projection of canonical records. Reviewer timestamps and operational filenames remain in append-only envelopes and do not affect deterministic payload identities.

## 5. Source intake

### 5.1 Intake sequence

1. Validate the source path without following links.
2. Reject directories, symlinks, Windows reparse points, unsupported extensions, and known pre-copy policy violations.
3. Stream bytes into a private temporary file inside the case root while enforcing `max_file_bytes`.
4. Compute SHA-256 and byte size from the temporary copy.
5. Sniff MIME from the copied bytes.
6. Validate MIME, extension, declared role, and trusted metadata.
7. Open the final destination with create-only semantics equivalent to `O_CREAT | O_EXCL` and copy the validated bytes.
8. Flush and close the final destination before publishing its manifest entry.
9. Delete the temporary file.
10. Never use the external path as runtime authority again.

The final path is not considered published until the manifest entry is written. On an expected failure, unpublished temporary or final files are removed. A process crash may leave an unreferenced file; recovery treats any unreferenced artifact as incomplete and never as authoritative evidence.

### 5.2 Supported signatures and canonical extensions

| MIME | Signature | Canonical extension |
|---|---|---|
| `application/pdf` | `%PDF-` | `.pdf` |
| `image/png` | standard PNG 8-byte signature | `.png` |
| `image/tiff` | little- or big-endian TIFF signature | `.tif` |
| `image/jpeg` | JPEG SOI marker | `.jpg` |

Input extensions are compared case-insensitively. `.tiff` and `.jpeg` are accepted aliases but stored with the canonical extension. An extension/MIME mismatch or unknown signature is rejected rather than guessed.

### 5.3 Versioned intake policy

```text
policy_id: DRAWING-INTAKE-1
max_file_bytes: 262144000
max_pdf_pages: 200
max_image_pixels: 150000000
max_case_image_pixels: 500000000
```

Policy values are explicit immutable input data and are included in assessment output. Tests inject smaller policies rather than patch global constants.

### 5.4 Trusted metadata boundary

This milestone does not add a PDF or image parser dependency. Page count, image dimensions, page MediaBox, and parser failure data arrive through a trusted adapter-result contract.

The adapter result must include:

- source SHA-256
- adapter name and version
- page count for PDF, when available
- width and height for images, when available
- page physical-size metadata, when available
- explicit parser outcome and failure code

A source-hash mismatch rejects the adapter result. Unknown dimensions or page counts do not silently bypass limits; they produce `REVIEW_REQUIRED` unless another trusted source verifies them. Parser timeout, memory-limit, malformed-output, and unsupported-feature failures become detailed quality reasons instead of uncaught process failures.

Embedded PDF JavaScript, file attachments, actions, and links are never executed or imported as evidence.

## 6. Drawing quality gate

The gate returns the existing `DrawingQualityAssessment` contract.

### 6.1 Quality statuses

- `PASS`: safe and sufficiently trusted for candidate review
- `REVIEW_REQUIRED`: stored and reviewable, but physical size, source quality, or metadata needs reviewer confirmation
- `REJECTED`: unsupported, unsafe, corrupt, or beyond resource limits

### 6.2 Physical-size trust

- `PDF_MEDIABOX_VERIFIED`
- `USER_CONFIRMED`
- `METADATA_ONLY`
- `UNKNOWN`

`METADATA_ONLY` cannot produce `PASS`. JPEG, screenshots, and lossily recompressed sources default to at least `REVIEW_REQUIRED`.

### 6.3 Detailed quality reasons

Detailed quality reasons remain inside the quality assessment and are not inserted directly into `WorkflowStateRecord.reason_codes`.

Minimum detailed reasons:

```text
UNSUPPORTED_MIME
MIME_EXTENSION_MISMATCH
FILE_SIZE_LIMIT_EXCEEDED
PDF_PAGE_LIMIT_EXCEEDED
IMAGE_PIXEL_LIMIT_EXCEEDED
CASE_PIXEL_LIMIT_EXCEEDED
DECOMPRESSION_BOMB_RISK
PARSER_TIMEOUT
PARSER_MEMORY_LIMIT
PARSER_OUTPUT_INVALID
SOURCE_HASH_MISMATCH
UNKNOWN_PHYSICAL_SIZE
METADATA_ONLY_PHYSICAL_SIZE
LOSSY_OR_SCREEN_CAPTURE_SOURCE
DRAWING_CONFIRMATION_REQUIRED
```

### 6.4 Mapping to M0 workflow reason codes

Workflow documents use only the M0 reason-code namespace:

| Detailed condition | M0 workflow reason code |
|---|---|
| source hash mismatch | `SOURCE_HASH_MISMATCH` |
| rejected drawing quality or resource/security rejection | `DRAWING_QUALITY_REJECTED` |
| missing reviewer confirmation or unknown physical size needed for binding | `DRAWING_CONFIRMATION_REQUIRED` |
| conflicting confirmed values | `SOURCE_CONFLICT` |

The quality assessment preserves the detailed reason list for diagnosis.

## 7. Candidate repository

### 7.1 Contract reuse

All candidates use `DrawingCandidate`. No new candidate status, geometry type, coordinate-system type, or origin enum is introduced.

### 7.2 Extractor candidates

A parser element may become an extractor candidate only when it has:

- immutable source SHA-256
- positive page number
- explicit neutral candidate type
- approved geometry or a bbox convertible to `BBOX`
- extractor name and version

The adapter may map explicit parser element types to neutral types such as `TEXT_ELEMENT`, `TABLE_ELEMENT`, or `VECTOR_ELEMENT`. It must not infer legal meaning or domain-specific drawing semantics from generic text.

### 7.3 Manual candidates

A reviewer may create a candidate when extraction fails.

```text
origin: REVIEWER_MANUAL
status: CREATED
annotation_id: required
extractor: null
extractor_version: null
```

Manual candidates require immutable source SHA-256, page, candidate type, and `POINT`, `BBOX`, `LINESTRING`, or `POLYGON` geometry.

### 7.4 Stable IDs and persistence

- Extractor candidate IDs derive from case ID, source SHA-256, page, extractor identity, and stable parser element identity.
- Manual candidate IDs derive from case ID plus the reviewer-supplied stable annotation ID.
- Arrival order, wall-clock time, and filesystem enumeration order are not ID inputs.
- One canonical JSON file is written per candidate.
- Duplicate IDs are rejected.
- Candidate files are immutable.
- Reviewer actions never rewrite candidates; they create confirmation records.

## 8. Confirmation store

### 8.1 Append-only rule

Each reviewer action creates a new canonical JSON document under `confirmations/`. Existing confirmation files are never updated or replaced.

### 8.2 Validation

Before persistence:

- candidate exists
- candidate and source SHA-256 match the immutable case source
- action is allowed by M0
- reviewer and reviewer filename token are valid
- timestamp is an ISO-8601 datetime with an explicit offset
- `EDITED` or `CREATED` contains a confirmed value, replacement geometry, or both
- `REJECTED` cannot produce a confirmed input
- geometry retains the candidate page and coordinate system
- confirmation ID and destination path are create-only

### 8.3 Confirmation hash

The canonical confirmation payload is SHA-256 hashed. `ConfirmedInput` stores the relative confirmation path and confirmation SHA-256. A later mismatch blocks input building or engine binding.

## 9. Confirmed input builder

### 9.1 Bindable statuses

Only `ACCEPTED`, `EDITED`, and `CREATED` may produce a `ConfirmedInput`. `UNCONFIRMED`, `REJECTED`, and `CONFLICT` always fail.

### 9.2 Build requirements

The builder verifies:

- candidate and confirmation source hashes match the immutable source
- candidate ID or annotation ID matches the confirmation target
- confirmation action resolves to a bindable effective status
- value is a finite decimal string
- unit is non-empty
- page and geometry are present
- confirmation path remains under `confirmations/`
- confirmation file exists and its SHA-256 matches
- input ID and field are valid identifiers

### 9.3 Set-level conflict policy

A confirmed-input set is invalid when the same field has multiple active confirmations with different value/unit pairs or incompatible geometries. The builder returns a deterministically sorted error set and does not choose a winner.

The workflow projection is:

```text
workflow_state: INPUT_CONFIRMATION_REQUIRED
reason_codes: [SOURCE_CONFLICT]
resumable: false
```

`resumable` remains `false` because the current M0 workflow contract permits `resumable: true` only for `BLOCKED`; the workflow can still progress after a later confirmation event creates a new state document.

## 10. Engine binding adapter

The adapter accepts decoded `ConfirmedInput` objects only after source and confirmation hashes are reverified.

```text
DrawingCandidate
  -> DrawingConfirmation
  -> ConfirmedInput
  -> engine input mapping
```

Output is a deterministic mapping from field name to decimal-string value and unit metadata. It performs no derived calculation. Direct candidate-to-engine binding is prohibited.

## 11. Workflow projection

Workflow documents follow the M0 relationship rules exactly:

- no drawing source: `PENDING_DRAWING_INGESTION`, no reason codes
- source stored but required confirmations missing: `INPUT_CONFIRMATION_REQUIRED`, no reason codes
- conflicting confirmations: `INPUT_CONFIRMATION_REQUIRED`, no reason codes; conflict details remain in the drawing validation result
- accepted confirmed-input set: `READY_TO_EVALUATE`, no reason codes
- resumable source rejection: `BLOCKED`, `reason_codes: [DRAWING_QUALITY_REJECTED]`, `resumable: true`
- terminal source integrity failure: `FAILED`, one or more M0 reason codes, `resumable: false`

Because M0 permits reason codes only on `BLOCKED` and `FAILED`, nonterminal workflow states carry detailed drawing conditions in their companion validation/quality artifact rather than `WorkflowStateRecord.reason_codes`.

This milestone never produces a human decision or finalizer result.

## 12. Determinism

Deterministic artifacts:

- immutable source hash and manifest entry
- quality assessment for identical source metadata and policy
- candidate JSON and IDs
- confirmation payload excluding its operational filename
- confirmed-input JSON
- engine-binding mapping
- validation-error ordering

Operational data kept separate:

- reviewer timestamp
- confirmation filename timestamp
- temporary intake path
- process ID
- parser worker timing

All deterministic JSON uses existing canonical JSON utilities.

## 13. Error handling and create-only writes

- Source bytes are copied to an internal temporary file before validation.
- Final destinations are opened create-only; overwrite attempts fail.
- A manifest entry is written only after the final source is complete and closed.
- Recovery ignores unreferenced source files and may report them as incomplete artifacts.
- Candidate and confirmation writes use create-only semantics.
- `confirmed-inputs.json` is generated only after the complete set validates; an existing file is not replaced in this milestone.
- Parser failures become quality assessment data.
- Hash mismatch, path escape, and overwrite attempts fail closed.

## 14. Security requirements

- no network access
- no execution of embedded PDF actions or scripts
- no archive extraction
- no allocation from untrusted image dimensions before policy validation
- no following symlinks or Windows reparse points
- no external-path authority after immutable ingest
- no overwrite of source, candidate, confirmation, or confirmed-input artifacts
- no model-generated confirmation or engine input
- no authoritative source role inferred without the user-declared role

## 15. Testing strategy

### 15.1 Unit tests

- identifier and path validation
- symlink, reparse-point, and directory rejection
- create-only source writes and recovery of unreferenced files
- signature-based MIME detection and alias normalization
- extension/MIME mismatch
- file, page, image-pixel, and case-pixel limits
- `METADATA_ONLY + PASS` rejection
- detailed quality reason to M0 workflow reason mapping
- parser failure mapping
- extractor/manual candidate separation
- all four geometry types
- stable ID independence from arrival order
- candidate create-only persistence
- append-only confirmation persistence
- source and confirmation hash mismatch
- action/status consistency
- finite decimal validation
- conflict detection
- unconfirmed/conflict engine-binding rejection
- M0 workflow relationship validation

### 15.2 Integration tests

Primary success path:

```text
PDF or PNG received
  -> immutable source stored
  -> quality assessment produced
  -> no useful automatic candidate
  -> reviewer creates manual LINESTRING or POLYGON
  -> reviewer creates append-only confirmation
  -> confirmed-inputs.json generated
  -> engine binding succeeds
  -> READY_TO_EVALUATE
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
confirmation file modified after confirmed-input generation
  -> confirmation hash mismatch
  -> binding rejected
```

Resource rejection path:

```text
over-limit trusted metadata
  -> quality REJECTED
  -> no candidate extraction
  -> BLOCKED or FAILED using M0 reason codes
```

### 15.3 Regression checks

- current baseline tests remain green
- new deterministic fixtures are byte-equivalent across repeated runs
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

A new case-manifest schema may be added. Drawing geometry, candidate, confirmation, quality, and confirmed-input schemas reuse M0 documents and are not duplicated.

## 17. Acceptance criteria

- A supported drawing is copied to immutable case storage before processing.
- The runtime never uses the external upload path after ingest.
- Unsafe or over-limit inputs fail without a published manifest entry.
- Quality results use only M0 quality and trust enums.
- Detailed drawing reasons never violate the M0 workflow reason-code namespace.
- Automatic parser failure does not prevent manual annotation.
- Manual `CREATED` candidates support all four approved geometry types.
- Candidate IDs do not depend on timestamps or arrival order.
- Confirmation records are append-only and hash-bound.
- Only validated `ACCEPTED`, `EDITED`, or `CREATED` values become confirmed inputs.
- Conflicts and unconfirmed values cannot bind to engines.
- The manual-annotation success path passes without OCR or automatic boundary detection.
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
