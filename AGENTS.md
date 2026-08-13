# Evidence Review System Agent Instructions

## 1. Authority model

This repository implements an offline, evidence-first review runtime for user-provided PDFs and immutable parser artifacts.

The authority order is:

1. preserved source bytes and source hash;
2. deterministic parser/evidence records;
3. deterministic retrieval, Math Engine results, and approved Rule Engine results;
4. independently produced Track A and Track B outputs after runtime validation;
5. immutable final review packet and HTML projection;
6. separate append-only human decision.

The system never makes the final human decision. `READY_FOR_HUMAN_REVIEW` means ready to inspect, not approved. Machine packet `human_decision` remains null.

## 2. Mandatory rules

- Preserve original PDF and raw parser output. Never overwrite them.
- Retain document, revision, page, source hash, bbox/geometry provenance.
- Never calculate in prose when an approved Math Engine result is required.
- Never invent or alter Rule Engine outcomes.
- Fail closed for missing parser output, invalid authority, hash mismatch, stale artifacts, unsafe paths, or failed validation.
- Project runtime remains offline except for loopback communication used by the protected local review server.
- All user questions use the formal `review-question` flow. There is no quick mode.
- Users do not hand-author query bundles, review-run requests, Track handoff metadata, packet hashes, or timestamps.

## 3. PDF preparation

The user-facing `$ERS_PDF` flow prepares immutable source evidence, source-batch v2, `evidence.sqlite`, and verified revision page image cache.

Current source-batch commands:

```powershell
evidence-review source-batch prepare `
  --root <workspace> `
  --manifest <workspace>\manifests\source-batch.json

evidence-review source-batch ingest `
  --root <workspace> `
  --manifest <workspace>\manifests\source-batch.json `
  --output <workspace>\evidence\evidence.sqlite
```

Only parser-ready reference/table sources enter the searchable evidence DB. Drawing inputs that require confirmation remain outside evaluation until confirmed and hash-verified.

Verified page images are revision-scoped reusable cache artifacts under:

```text
<workspace>/page-images/<REVISION-ID>/page-NNNN.png
<workspace>/page-images/<REVISION-ID>/page-NNNN.json
```

Review rendering verifies the cached image hash and PDF geometry. It must not re-render the same source page for every question.

## 4. Mandatory formal question flow

### 4.1 Prepare the question

```powershell
evidence-review review-question prepare `
  --workspace <workspace> `
  --question "<question>"
```

Optional `--expansion` is only for a user-supplied search expansion. Deterministic calculation/rule outputs may be attached with `--calculation-result`, `--rule-result`, and `--approved-rule-result-id`.

The runtime creates the canonical retrieval bundle, review request, Track A bundle, next-action artifact, and append-only workflow events. The same deterministic request resumes the same Run ID.

### 4.2 Track A

Codex reads `track-a-bundle.json` and `TRACK_A_INSTRUCTIONS.md`, writes Track A, then immediately validates it:

```powershell
evidence-review review-question submit-track-a `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-a-output <track-a-output.json>
```

Do not start Track B before this succeeds. Track A may explain supplied evidence and engine results but cannot create evidence, calculations, rule outcomes, confidence authority, or a human decision.

### 4.3 Track B

Track B independently audits every Track A claim exactly once. Then submit it:

```powershell
evidence-review review-question submit-track-b `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-b-output <track-b-output.json> `
  --publish
```

Track B validation precedes finalization. A failed or incomplete Track B cannot produce a ready packet.

`review-run prepare` and `review-run finalize` are lower-level compatibility/test interfaces. They are not the current `$ERS_REVIEW` user path.

## 5. Runtime observability

Each run has append-only metrics events under `run-metrics-events/` and a derived `run-metrics.json` projection.

Metrics cover request normalization, retrieval, request construction, preparation, Track A/B external wait and validation, finalizer, view-model build, page-image verification, HTML render/write, protected server start, and browser dispatch.

Metrics are non-authoritative telemetry. They do not participate in Run ID, run manifest, final packet, or evidence hashes.

Hard acceptance budgets:

- deterministic non-model total: at most 5 seconds;
- protected server start + browser dispatch after packet/HTML: at most 2 seconds.

Only an attempt following a failed attempt of the same stage counts as a retry. External Track wait is reported separately from deterministic runtime.

## 6. Non-developer Review Workspace

The default HTML surface is intentionally simple:

1. result and concise conclusion;
2. evidence with page and bbox;
3. additional-review section only when an issue exists;
4. human decision.

A single claim has no redundant item navigator. Empty rule/calculation sections do not render. Internal IDs, hashes, confidence factors/weights, and raw audit data remain available under collapsed audit details rather than the default surface.

The reviewer decision panel is sticky on desktop and stacks below 1100 px. Browser QA, 200% zoom, keyboard focus, and print behavior must be manually checked for acceptance; static tests do not substitute for visual QA.

## 7. Protected browser and human decision

Open a finalized run through the tokenized loopback server:

```powershell
evidence-review review-run serve `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --reviewer-id <REVIEWER-ID>
```

The protected route is:

```text
http://127.0.0.1:<port>/runs/<RUN-ID>/<TOKEN>/review
```

Decision request v2 contains exactly:

```json
{
  "reviewer_id": "reviewer-01",
  "packet_hash": "<current-packet-sha256>",
  "decision": "SATISFIED",
  "notes": "review notes"
}
```

The server verifies the current packet hash, binds an expected reviewer ID when configured, and generates `reviewed_at` as an offset-aware server timestamp. It appends a new file under `human-decisions/`; it never mutates the machine packet or HTML.

Allowed decisions are `SATISFIED`, `NOT_SATISFIED`, `CONDITIONAL`, and `ADDITIONAL_REVIEW_REQUIRED`.

A valid decision may project `REVIEW_COMPLETED` in the browser. That projection is not a stored machine finalizer state.

### Archival HTML

Opening `review.html` with `file:` cannot persist through the protected endpoint. The **결정 JSON 다운로드** control creates a five-field archival envelope only after local validation. Import it through the approved path:

```powershell
evidence-review review-run import-decision `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --envelope <human-decision-envelope.json>
```

Import must reject packet-hash mismatch and existing create-only filename collisions.

## 8. Server lifecycle

Current lifecycle commands:

```powershell
evidence-review review-run serve-status --workspace <workspace> --run-id <RUN-ID>
evidence-review review-run serve-stop --workspace <workspace> --run-id <RUN-ID>
```

Detached-server startup timeout is 2 seconds. Stale state must be removed and management operations must not signal an unrelated reused PID.

Do not claim Windows lifecycle acceptance until it has been exercised on the exact target commit. Issue #92 remains the authority for any unresolved lifecycle acceptance work.

## 9. Documentation and verification

Current repository guidance must match executable commands. Before claiming acceptance, run from a clean checkout at the exact HEAD:

```bash
evidence-review documentation validate --repository-root . --config documentation-integrity.json --output <fresh-output>
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

Focused review suites:

```bash
pytest -v tests/integration/review_question
pytest -v tests/integration/review_packet
pytest -v tests/integration/review_run
pytest -v tests/unit/review_packet
```

For issue #87 acceptance, additionally execute the Windows Python 3.11/3.13 E2E matrix, browser viewport/zoom matrix, protected/archival decision paths, server lifecycle tests, and three simple-question timing runs. Record exact artifact hashes.

GitHub Actions is not the default acceptance dependency. Report its actual state precisely as `ACTIONS_NOT_RUN`, `ACTIONS_UNAVAILABLE`, `ACTIONS_BILLING_BLOCKED`, or an observed PASS. Never convert local/manual PASS into Actions PASS.

## 10. Legacy and release boundaries

Grist remains a legacy compatibility path. Do not describe removed repair/export wrappers as current commands. Release process attestation, release ZIP validation, and offline assurance remain separate gates documented in `docs/OFFLINE_EXECUTION.md` and `docs/MANUAL_ACCEPTANCE_POLICY.md`.

## 11. Prohibited completion claims

Do not close an issue, merge acceptance work, or report PASS merely because code was written. Completion requires the issue's explicit automated and manual gates. If a gate was not executed, record `NOT_RUN` rather than inferring success.
