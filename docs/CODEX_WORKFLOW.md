# Codex Workflow

Use local evidence only. Project Python code does not call a model or remote API. Codex supplies the external Track A/Track B reasoning at deterministic file handoffs; runtime code validates those outputs before the workflow can advance.

Shared status and contract governance is documented in `docs/CONTRACT_GOVERNANCE.md`.
## 0. Prove runtime provenance before business commands

Use the interpreter-pinned module entrypoint before every acceptance or review run. The
stdlib-only diagnostic surface runs before heavy runtime imports and reports the
checkout HEAD, package source path, and required dependency state.

```powershell
$Workspace = "C:\evidence-review-workspace"
py -3.13 -m evidence_review doctor --repository-root .
py -3.13 -m evidence_review review-question prepare --workspace $Workspace --question "<question>"
```

`SOURCE_MISMATCH` means the active interpreter is importing project modules from a
different checkout. Activate the intended interpreter and reinstall this checkout
editable with that interpreter:

```powershell
py -3.13 -m pip install -e ".[dev]"
```

## 1. Prepare source evidence

Every PDF is registered in a source-batch v2 manifest. Filename and display title are not authority for document role, identity, page identity, or legal meaning.

```powershell
evidence-review source-batch prepare `
  --root <workspace> `
  --manifest <workspace>\manifests\source-batch.json

evidence-review source-batch ingest `
  --root <workspace> `
  --manifest <workspace>\manifests\source-batch.json `
  --output <workspace>\evidence\evidence.sqlite
```

Only parser-ready reference/table sources enter the searchable evidence DB. Parserless drawings remain in their declared pending/confirmation state and cannot silently become reference evidence or engine inputs.

The PDF preparation flow also establishes reusable verified page image cache artifacts under `page-images/<REVISION-ID>/`. Review rendering verifies those cache artifacts instead of rasterizing the same PDF page again for every question.

## 2. One formal review for every question

The current user-facing workflow is `review-question`. Do not use a separate quick retrieval mode and do not ask the user to hand-author intermediate JSON.

### 2.1 Prepare

```powershell
evidence-review review-question prepare `
  --workspace <workspace> `
  --question "<question>"
```

Optional inputs:

```text
--expansion <explicit-user-search-term>
--calculation-result <CalculationResult.json>
--rule-result <RuleResult.json>
--approved-rule-result-id <rule-result-id>
```

`--expansion` is not a model-generated query rewrite. Calculation and RuleResult artifacts must already be authoritative deterministic outputs.

Preparation performs request normalization, local retrieval, canonical review-request construction, immutable run preparation, and Track A handoff creation. It writes an append-only workflow event journal. Repeating an identical deterministic request resumes the same Run ID from its last valid state.

### 2.2 Produce and validate Track A immediately

Read only the run's `track-a-bundle.json` and `TRACK_A_INSTRUCTIONS.md`. Track A explains provided evidence, approved calculation results, and rule results. It cannot create evidence, alter numeric tokens, change rule status, assign a human decision, or bypass citations.

After writing `track-a-output.json`, validate it before doing any Track B work:

```powershell
evidence-review review-question submit-track-a `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-a-output <track-a-output.json>
```

A failed validation keeps the workflow at Track A. Correct Track A and retry. Do not spend a Track B pass auditing a Track A output that has not passed this gate.

### 2.3 Produce Track B exactly once over the validated claims

Track B independently audits every validated Track A claim. It may accept/reject claims according to its contract but does not rewrite Track A or make the human decision.

```powershell
evidence-review review-question submit-track-b `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-b-output <track-b-output.json> `
  --publish
```

The runtime validates Track B before finalization. Finalization creates the run-specific `final-review-packet.json` and `review.html` only after all deterministic and Track gates pass.

Lower-level `review-run prepare` / `review-run finalize` remain compatibility and controlled-test interfaces. They are not the normal `$ERS_REVIEW` path.

## 3. Workflow journal and recovery

The event journal is the state authority for the formal question flow. It preserves ordered transitions through Track A, Track B, finalization, and ready-for-review states. Immutable artifacts are revalidated on resume. Interrupted or partially written restartable outputs are cleaned only when they can be safely regenerated; differing immutable artifacts fail closed.

A resume must never silently roll a completed Track A validation back to an earlier stage. Tampered artifacts or mismatching retry input stop the run.

## 4. Performance telemetry

Each run records create-only timing events under:

```text
runs/<RUN-ID>/run-metrics-events/
```

`run-metrics.json` is a derived projection. Telemetry covers:

- request normalization;
- retrieval;
- review-request build;
- prepare;
- Track A external wait and validation;
- Track B external wait and validation;
- finalizer;
- view-model build;
- page-image verification;
- HTML render/write;
- protected server start;
- browser dispatch.

Telemetry is intentionally non-authoritative: it is excluded from Run ID, run manifest, final packet, and evidence hashes.

`deterministic_total_ms` excludes Track A/B external wait. `retry_count` counts a new attempt only when the preceding attempt of the same stage failed. Failed stages retain a reason code.

Acceptance budgets:

- deterministic non-model work: `<= 5000 ms`;
- protected server start + browser dispatch after packet/HTML: `<= 2000 ms`.

Actual performance acceptance requires three Windows runs and recorded p50/p95. Do not infer the budget from unit tests alone.

## 5. Final Review Workspace

The default Review Workspace is a reviewer surface, not a developer dashboard. Its normal information order is:

1. 검토 결과 — Korean status and concise conclusion;
2. 판단 근거 — source quote, page, and bbox with verified page image;
3. 추가 확인 — rendered only when missing/conflict/exception/abstention items exist;
4. 검토자 의견 — decision and notes.

Single-claim runs do not show redundant claim navigation. Rule/calculation UI is absent when there are no applicable records. run/citation/evidence/revision IDs, hashes, confidence factor details, and raw audit data stay in collapsed audit details.

The citation bbox and traceable source location remain visible because they are reviewer evidence, not developer decoration.

## 6. Protected browser handoff

Start the finalized review with an expected reviewer when known:

```powershell
evidence-review review-run serve `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --reviewer-id <REVIEWER-ID> `
  --detach `
  --idle-timeout-seconds 5
```

The detached server defaults to a 1800-second monotonic idle timeout. Only valid tokenized protected requests refresh the deadline.

Protected URLs use a run-scoped token on loopback:

```text
http://127.0.0.1:<port>/runs/<RUN-ID>/<TOKEN>/review
```

The companion endpoints use the same protected prefix:

```text
/runs/<RUN-ID>/<TOKEN>/packet
/runs/<RUN-ID>/<TOKEN>/packet/hash
/runs/<RUN-ID>/<TOKEN>/decision
/runs/<RUN-ID>/<TOKEN>/decision/status
```

The final review route is unavailable until both final packet and HTML exist.

The browser decision request v2 has exactly four string fields:

```json
{
  "reviewer_id": "reviewer-01",
  "packet_hash": "<sha256>",
  "decision": "SATISFIED",
  "notes": "review notes"
}
```

When `--reviewer-id` is configured, the browser receives it as read-only session context and a different submitted reviewer ID is rejected. The status endpoint also supplies the current immutable packet hash. The server rechecks that hash at POST time and generates `reviewed_at` itself as an offset-aware ISO-8601 timestamp.

A successful decision creates a new append-only JSON record under `human-decisions/`. It does not modify `final-review-packet.json`, `review.html`, finalizer status, or evidence. A valid decision may cause the UI to project `REVIEW_COMPLETED`.

Allowed decisions:

- `SATISFIED` — 내용 확인 완료
- `NOT_SATISFIED` — 내용에 오류 있음
- `CONDITIONAL` — 조건부 확인
- `ADDITIONAL_REVIEW_REQUIRED` — 추가 자료 필요

## 7. Archival HTML decision handoff

`review.html` is also a self-contained archival artifact. When opened with `file:`, it cannot call the protected decision endpoint.

The **결정 JSON 다운로드** control validates decision, notes, reviewer ID, and packet hash locally, then creates a five-field envelope containing `reviewed_at: new Date().toISOString()`.

Import the envelope through the approved validator path:

```powershell
evidence-review review-run import-decision `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --envelope <human-decision-envelope.json>
```

Import hashes the current run packet again, rejects stale/tampered packet bindings, validates the envelope, and creates a new append-only decision record. HTML file saving is not decision persistence.

## 8. Server lifecycle

Use run-scoped management commands:

```powershell
evidence-review review-run serve-status --workspace <workspace> --run-id <RUN-ID>
evidence-review review-run serve-stop --workspace <workspace> --run-id <RUN-ID>
```

The detached process uses a 2-second startup timeout. Stale state cleanup and process identity checks protect management operations from acting on an unrelated reused PID.

Windows lifecycle behavior must be manually accepted on the target commit. Do not infer Windows PASS from POSIX process identity tests. Issue #92 remains the lifecycle acceptance authority for this lifecycle contract.

## 9. Drawing evidence boundary

Drawing candidates remain separate from reusable reference evidence. A drawing requiring confirmation cannot become Math/Rule input until its immutable source and reviewer confirmation are hash-verified. The final review route must not appear while required drawing confirmation is incomplete.

Browser annotation may transform pointer coordinates into declared page coordinates, but it is not a calculation engine: it cannot infer scale, real-world length, area, ratio, threshold result, rule status, or confidence.

## 10. Acceptance verification

Run from a clean checkout at the exact HEAD with Python 3.13:

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output <fresh-output>
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
```

Focused suites:

```powershell
py -3.13 -m pytest -v tests/integration/review_question
py -3.13 -m pytest -v tests/integration/review_packet
py -3.13 -m pytest -v tests/integration/review_run
py -3.13 -m pytest -v tests/unit/review_packet
```

Current release acceptance uses Python 3.13 only. It requires three simple-question timing samples with p50/p95, browser QA at 1366×768 / 1920×1080 / 3840×2160, protected decision, archival envelope/import, browser-open failure, and server status/stop evidence.

Record unexecuted gates as `NOT_RUN`. GitHub Actions must be reported separately as its actual observed state; it is not replaced by local validation.
