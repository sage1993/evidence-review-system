# Drawing Browser Handoff Design

## Goal

Add browser-visible calibration handoff and read-only Review Packet v2 rendering to the existing localhost drawing annotation workspace so Issue #6 can be reviewed as one traceable flow.

## Scope and authority

The existing annotation server persists candidates and append-only confirmations. The existing calibration module owns validation and Decimal Math Engine calculations. The existing Review Packet v2 renderer owns self-contained drawing HTML. This change connects those authorities without adding OCR, rule evaluation, JavaScript arithmetic, or a human final decision.

The server remains loopback-only and run-scoped. It does not promise to rebuild its in-memory artifact indexes after restart; a new server run starts in deterministic pending state until it creates/binds new confirmations and calibrations.

## Routes and exact contracts

All routes use the server token and exact `Host: 127.0.0.1:<assigned-port>`. Successful GET responses are `200 text/html; charset=utf-8`; successful POST responses are `201 application/json; charset=utf-8`. All responses include `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and:

```text
Content-Security-Policy: default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'
```

All non-success responses are JSON `{"error":"CODE"}` with the same headers and no paths or exception text. `GET` does not require `Origin`; the new calibration POST requires `Origin` equal to the exact server origin and `Content-Type: application/json` without parameters. The existing annotation action POST retains its current compatibility behavior and accepts `application/json` with optional media-type parameters.

| Method/path | Request | Success | Defined failures |
|---|---|---|---|
| `GET /annotation/<token>` | none | Existing annotation HTML | `403 FORBIDDEN`, `404 NOT_FOUND` |
| `POST /annotation/<token>/actions` | Existing action JSON | Existing `{candidate,confirmation}` entry response | Existing action errors; response uses `confirmation`, never `confirmation_entry` |
| `GET /calibration/<token>` | Optional `candidate_id` and `confirmation_id`; each may occur once | Calibration form HTML | `400 INVALID_QUERY`, `403 FORBIDDEN`, `404 NOT_FOUND` |
| `POST /calibration/<token>` | Exact JSON schema below | `201 {calibration:{artifact_id,relative_path,sha256},packet_url}` | `400 INVALID_CALIBRATION`, `403 FORBIDDEN`, `404 NOT_FOUND`, `409 ALREADY_EXISTS`/`BINDING_MISMATCH`/`ARTIFACT_HASH_MISMATCH`, `411 CONTENT_LENGTH_REQUIRED`, `413 BODY_TOO_LARGE`, `415 UNSUPPORTED_MEDIA_TYPE` |
| `GET /review-packet/<token>` | No query, `calibration_id` only, or all three IDs | Packet HTML or pending HTML | `400 INVALID_QUERY`, `403 FORBIDDEN`, `404 NOT_FOUND`/`ARTIFACT_MISSING`, `409 BINDING_MISMATCH`/`ARTIFACT_HASH_MISMATCH`, `500 RENDER_FAILED` |

The calibration POST schema is:

```json
{
  "candidate_id": "CAND-...",
  "confirmation_id": "CONF-...",
  "reviewer": "ksh",
  "confirmed_at": "2026-08-06T12:00:00+09:00",
  "axis": "x",
  "pixel_points": [[1200, 900], [8400, 900]],
  "real_length": "35.0",
  "unit": "m"
}
```

All fields are required. `axis` is exactly `x` or `y`; `pixel_points` is exactly two finite numeric pairs; strings are non-empty; `confirmed_at` is offset-aware ISO-8601; and `real_length` is a positive finite decimal string. The form creates one hidden `confirmed_at` at page load and reuses it on replay; the server validates it and never replaces it.

The browser route extends the existing calibration model as follows. `CalibrationRecord` gains `candidate_id: str | None = None` and `confirmation_id: str | None = None` as trailing defaulted dataclass fields. `calibration_document()` emits each identifier when non-null and omits it for legacy records; the canonical decoder accepts absent identifiers as `None` and validates present identifiers with the existing identifier grammar. There is no migration or restart scan of legacy files. The browser route rejects a record without both identifiers. The route constructs the record from the validated request, invokes the existing Math Engine-backed builder, then persists the canonical document with those two identifiers; it does not calculate scale in browser code.

The timestamp is normalized to its UTC instant for ordering and duplicate comparison, while the persisted canonical value retains the original offset-aware ISO-8601 spelling. The selected confirmation's persisted `confirmed_at` must parse successfully and the calibration `confirmed_at` must be equal to or later than that instant. The hidden form timestamp is created once when the form is rendered and is not refreshed on submit.

The body limit is exactly 65,536 bytes from one valid `Content-Length` header before decoding. Missing `Content-Length` or `Transfer-Encoding: chunked` returns `411 CONTENT_LENGTH_REQUIRED`; multiple `Content-Length` values, malformed UTF-8/JSON, or unknown fields return `400 INVALID_CALIBRATION`; oversized bodies return `413 BODY_TOO_LARGE`; unsupported methods return `405 METHOD_NOT_ALLOWED` with the correct `Allow` header.

The method matrix is fixed: `/annotation/<token>` allows `GET`; `/annotation/<token>/actions` allows `POST`; `/calibration/<token>` allows `GET, POST`; and `/review-packet/<token>` allows `GET`. A method rejected by this matrix returns `405 METHOD_NOT_ALLOWED` and an `Allow` header containing exactly the methods for that path. Calibration binding failures are `409 BINDING_MISMATCH` when the candidate/confirmation relationship or source/page identity is wrong, and `409 ARTIFACT_HASH_MISMATCH` when a referenced verified artifact's bytes no longer match its manifest hash; `409 ALREADY_EXISTS` is reserved for the exact create-only replay or an occupied calibration ID with different content.

## Identifier, query, and artifact rules

Artifact IDs use the existing grammar exactly: `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`. Query values are percent-decoded once. Unknown keys, blank values, malformed percent escapes, duplicate keys, or raw `+` values are rejected with `400 INVALID_QUERY`.

The server maintains these run-scoped indexes:

```text
candidate_entries: dict[str, CaseManifestEntry]
confirmation_records: dict[str, (DrawingConfirmation, CaseManifestEntry, candidate_id)]
calibration_records: dict[str, (CalibrationRecord, CaseManifestEntry)]
```

The server initializes `candidate_entries` from the prepared case manifest at startup and initializes the other two indexes empty. A successful annotation POST appends its existing confirmation result and immediately adds the verified confirmation tuple to `confirmation_records`. A successful calibration POST immediately adds the persisted calibration tuple to `calibration_records`. Existing confirmation/calibration files are not scanned or trusted on restart; after restart the browser routes therefore return pending or `NOT_FOUND` until the current process creates new verified records. A run-scoped server instance owns all three indexes and serializes writes under one lock.

Calibration records persist `candidate_id` and `confirmation_id` in their canonical JSON. The core builder accepts those fields optionally for backward compatibility; the browser route requires them. `persist_calibration` remains atomic and create-only. An exact replay of the same POST produces the same content-derived calibration ID and returns `409 ALREADY_EXISTS` rather than overwriting. Hashes are always computed from canonical `dump_bytes` output or verified artifact bytes; client paths are never trusted.

The calibration POST accepts a candidate only when its source hash/page match the server page, and a confirmation only when its indexed candidate ID, source hash, bindable action, and reviewer match. The calibration binds the selected candidate and confirmation in the persisted record.

Review Packet query shapes are exactly:

1. no IDs: choose the verified calibration with greatest `confirmed_at`, then greatest `calibration_id`; derive candidate/confirmation from it;
2. `calibration_id` only: derive candidate/confirmation from that calibration;
3. all three IDs: require exact binding match.

Any other partial combination returns `400 INVALID_QUERY`. No calibration available with no IDs returns pending-state HTML; an explicit unknown calibration returns `404 NOT_FOUND`; missing selected files return `404 ARTIFACT_MISSING`; hash mismatches return `409 ARTIFACT_HASH_MISMATCH`; binding mismatches return `409 BINDING_MISMATCH`.

For a selected calibration, the route constructs a valid existing `ReviewPacketV2` mapping with exactly its required keys: `format` is `evidence-review/review-packet`, `version` is `2`, `run_id`/`case_id` come from the prepared workspace, `question` is the fixed browser handoff question, `finalizer_status` is `READY_FOR_HUMAN_REVIEW`, `snapshot_sha256` is the verified source hash, `rule_manifest_sha256` and `formula_manifest_sha256` are the verified SHA-256 values supplied in the prepared workspace authority metadata, `claims`, `evidence`, `rule_evaluations`, `exceptions`, `conflicts`, and `abstention_reasons` are empty arrays, `confidence` and `compatibility_source_version` are null, `drawing_evidence` contains the selected candidate, `confirmed_inputs` contains the selected confirmed input, and `calculations` contains the calibration Math Engine result. The server refuses to start with `STARTUP_FAILED` if either authority hash is absent or not a valid SHA-256; it never substitutes a source hash or a fabricated zero hash. `human_decision` is forcibly JSON null. No `source_document` or free-form `calibration` key is added to the strict packet contract.

The drawing renderer is extended with an optional keyword-only `display_metadata` mapping; existing callers may omit it. The browser route supplies exactly this shape and the renderer validates it before rendering:

```json
{
  "source_document": {"document_id":"...","revision_id":"...","page":17,"source_sha256":"..."},
  "candidate_id":"CAND-...",
  "confirmation_id":"CONF-...",
  "calibration_id":"CAL-...",
  "reviewer":"ksh",
  "confirmed_at":"2026-08-06T12:00:00+09:00",
  "calibration": {"axis":"x","pixel_points":[[1200,900],[8400,900]],"real_length":"35.0","unit":"m","scale_x":"...","scale_y":"...","formula_id":"DRAWING_SCALE","formula_version":"...","calculation_result_hash":"..."},
  "artifact_paths": {"candidate":"candidates/...json","confirmation":"confirmations/...json","calibration":"calibrations/...json"}
}
```

The renderer displays those fields alongside the valid packet. Confirmation and calibration paths are displayed as relative artifact paths from their verified manifest entries, never as client-supplied paths.

## UI and launcher behavior

The annotation page enables a calibration link only after the existing POST response contains a verified `confirmation.artifact_id`. The existing annotation action endpoint continues to accept `Content-Type: application/json` with optional parameters after `;` for compatibility; the stricter parameter-free rule applies only to the new calibration POST. The calibration page shows source hash, page, reviewer, axis, endpoints, real length, unit, hidden timestamp, verified candidate/confirmation, result calibration ID/scale/formula metadata, and a packet link. The deterministic QA values are reviewer `ksh`, axis `x`, points `[[1200,900],[8400,900]]`, real length `35.0`, unit `m`.

The Review Packet page is read-only. It shows embedded drawing/overlay, candidate and confirmation metadata, calibration metadata, source hash, and `human_decision: null`. The server forces this null value and exposes no decision control. No external resources are allowed.

After startup, the launcher flushes exactly these three lines, even before confirmation/calibration exists:

```text
Annotation workspace URL: http://127.0.0.1:<port>/annotation/<token>
Calibration workspace URL: http://127.0.0.1:<port>/calibration/<token>
Review Packet URL: http://127.0.0.1:<port>/review-packet/<token>
```

After successful calibration POST, `packet_url` uses `urllib.parse.urlencode` and contains all three bound IDs. Startup failure prints `error: STARTUP_FAILED` to stderr and exits 2.

## Packet rendering and evidence

The packet route verifies selected artifact bytes, builds a Review Packet v2 mapping with `human_decision` forced to JSON null, and calls `render_drawing_evidence`. The page image is embedded as a verified `data:image/...;base64,...` URI. The generated HTML is per-request and not a new machine-authoritative artifact.

Browser evidence is created relative to the repository root at exactly `tmp/pdfs/pr58-sample/browser-evidence.json`, once per run, with no extra keys:

```json
{
  "candidate_confirmation": true,
  "calibration_handoff": true,
  "review_packet_rendering": true
}
```

The operator associates it with the exact PR HEAD, source hash, case directory, and browser server URL in the manual report. The runner consumes the three booleans for compatibility and does not infer them from tests.

## Test-first acceptance

Before implementation, add focused tests for:

- calibration GET form, hidden timestamp, exact input schema, valid POST, canonical hash, create-only replay, binding mismatch, and no-write-on-failure;
- malformed query/body, duplicate query keys, wrong Host/Origin, unsupported method/content type, body limit, and exact security/error headers;
- packet no-ID pending state, calibration-only derivation, all-ID binding, missing/tampered artifact, renderer failure, embedded image, calibration metadata, null human decision, and no external URLs;
- annotation response field `confirmation` and calibration-link enablement;
- launcher's exact three-line startup output and bound `packet_url` after calibration POST.

After the red-green cycle, run the full repository gates, sample-PDF browser flow, and manual evidence runner against the exact committed PR HEAD.

## Non-goals

No OCR, automatic geometry interpretation, JavaScript arithmetic, rules, remote APIs, external assets, Review Packet v1 rewrite, or human final decision.
