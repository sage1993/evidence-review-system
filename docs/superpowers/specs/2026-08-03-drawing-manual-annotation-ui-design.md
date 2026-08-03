# Drawing Manual Annotation Workspace Design

> Document status: CURRENT

## Goal

Add a local browser workspace for issue #6 where a reviewer can inspect drawing candidates, select or create drawing geometry, and record append-only `ACCEPTED`, `REJECTED`, `EDITED`, or `CREATED` confirmations using the existing drawing backend contracts.

This design covers manual annotation only. Calibration arithmetic, OCR, automatic semantic extraction, DWG/DXF parsing, final Review Packet v2 rendering, and full issue #7 orchestration are separate follow-up work.

## Existing Authority

The implementation must reuse the current authoritative backend without defining parallel contracts:

- `contracts.drawing.Geometry`, `DrawingCandidate`, and `DrawingConfirmation`
- `parsing.drawing_candidates.create_manual_candidate()` and `persist_candidate()`
- `parsing.drawing_confirmation.validate_confirmation_for_candidate()` and `persist_confirmation()`
- `parsing.drawing_inputs.build_confirmed_input()`
- `parsing.drawing_case.CaseManifestEntry` and create-only artifact rules

The browser is a projection and input surface. It does not calculate scale, length, area, ratio, rule status, or confidence.

## Architecture

### 1. Deterministic view model

`src/ansim_review/drawing_review/view_model.py` converts validated drawing candidates and verified page metadata into a JSON-compatible model.

Responsibilities:

- require one immutable source SHA-256 and one page
- reject candidate source, page, or coordinate-system mismatch
- reject geometry outside the declared page bounds
- preserve all four M0 geometry types: `POINT`, `BBOX`, `LINESTRING`, `POLYGON`
- sort candidates by stable `candidate_id`
- expose candidate origin, status, raw value, normalized value, and geometry without mutation

It does not read unverified LLM text or infer candidate semantics.

### 2. Self-contained annotation renderer

`src/ansim_review/drawing_review/html_renderer.py` renders the deterministic model with embedded CSS and JavaScript.

- one verified page asset per page
- SVG overlay for all geometry types
- candidate selection and focus synchronization
- accept, reject, edit, and manual-create controls
- no preselected reviewer decision
- user-entered numeric text remains text until the backend validates and records it

### 3. Local confirmation server

`src/ansim_review/drawing_review/local_server.py` serves the page and receives reviewer actions.

Security boundary:

- bind only to `127.0.0.1`
- random run-scoped access token
- exact `Host` and `Origin` validation
- no CORS
- request body and identifier length limits
- no path supplied by the browser is trusted
- case artifacts are resolved through `case_artifact_path()`
- candidate and confirmation writes remain create-only and append-only

The server maps browser actions to existing backend functions. It does not write a candidate or confirmation directly.

### 4. Browser action contract

The browser submits a strict action object:

```json
{
  "action": "ACCEPTED",
  "candidate_id": "CAND-...",
  "reviewer": "kim-sh",
  "confirmed_at": "2026-08-03T21:30:00+09:00",
  "confirmed_value": null,
  "unit": null,
  "geometry": null
}
```

Manual creation uses:

```json
{
  "action": "CREATED",
  "annotation_id": "ANN-...",
  "candidate_type": "ROAD_WIDTH_TEXT",
  "reviewer": "kim-sh",
  "confirmed_at": "2026-08-03T21:30:00+09:00",
  "confirmed_value": "8.0",
  "unit": "m",
  "geometry": {
    "type": "LINESTRING",
    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
    "coordinates": [[100.0, 200.0], [900.0, 200.0]]
  }
}
```

The server derives source hash, page, candidate ID, confirmation ID, output path, and artifact hashes. Browser-supplied values cannot override these authorities.

## Data Flow

```text
verified source/page metadata + candidates
  -> deterministic drawing review view model
  -> self-contained HTML + SVG overlay
  -> reviewer action
  -> strict action decoder
  -> existing candidate/confirmation validators
  -> create-only candidate or append-only confirmation
  -> refreshed projection
```

## Error Handling

- mismatched source/page/coordinate system: fail before HTML generation
- out-of-page geometry: fail before HTML generation
- stale candidate or source hash: reject action without writing
- duplicate annotation or confirmation ID: preserve existing file and return conflict
- malformed body or unsupported action: HTTP 400
- invalid token, Host, or Origin: HTTP 403
- missing immutable source or candidate: HTTP 404
- unexpected server failure: HTTP 500 with no filesystem path disclosure

## Testing

### Unit

- deterministic candidate ordering
- all geometry types round-trip into the view model
- source/page/coordinate mismatch rejection
- page-bound rejection
- action contract validation
- server-derived identifiers and paths

### Integration

- extractor candidate acceptance
- candidate rejection
- edited value and geometry
- reviewer-manual `CREATED` annotation
- duplicate write refusal
- stale source or candidate tamper rejection
- HTML contains no external URL and no rule/calculation code

### Manual QA

- source and candidate overlay align at 100%, 200%, and fit-to-page zoom
- selected list item and SVG geometry remain synchronized
- reviewer can create POINT, BBOX, LINESTRING, and POLYGON annotations
- no action is selected by default
- unconfirmed values cannot reach Math or Rule Engine binding

## Completion Boundary

This subproject is complete when one verified raster drawing can be opened locally, a reviewer can accept/reject/edit an existing candidate or create a manual annotation, and the existing backend stores the resulting immutable candidate and append-only confirmation with full source and geometry provenance.

PDF page rendering, calibration, automatic extraction, final review packet rendering, and Codex resume remain separate tasks.