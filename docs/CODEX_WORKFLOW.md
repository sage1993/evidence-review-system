# Codex Workflow

## ReviewMatter authority modes

**Evidence Navigation** may inspect finalized evidence without creating a
Planner handoff or conclusion. The Workbench contains **mutable ReviewMatter
work state** only. **Formalization** alone promotes an exact Matter revision
and finalized snapshot to **Formal Review**, where the existing Planner,
Track A/Track B, packet, and Human Decision contracts remain authoritative.

Use local evidence only. Project Python code does not call a model or remote API. Codex supplies the external Question Planner, Track A, and Track B reasoning at deterministic file handoffs; runtime code validates those outputs before the workflow can advance.

Shared status and contract governance is documented in `docs/CONTRACT_GOVERNANCE.md`. Question planning and its trust boundary are documented in `docs/question-planning.md`.

The repository is incrementally migrating toward the ReviewMatter architecture. `ReviewMatter` and `matter_id` are target mutable-work identities, distinct from drawing `CaseManifest` and `case_id`. Do not use a target Matter command or module unless it exists at the exact checked-out HEAD. Until the corresponding migration boundary is merged and verified, the existing `review-question prepare-plan → prepare → Track A → Track B` path remains the current formal workflow. See [`REVIEW_MATTER_ARCHITECTURE.md`](REVIEW_MATTER_ARCHITECTURE.md).

## 0. Prove runtime provenance before business commands

Use the interpreter-pinned module entrypoint before every acceptance or review run. The stdlib-only diagnostic surface runs before heavy runtime imports and reports the checkout HEAD, package source path, and required dependency state.

```powershell
$Workspace = "C:\evidence-review-workspace"
py -3.13 -m evidence_review doctor --repository-root .
py -3.13 -m evidence_review review-question prepare-plan --workspace $Workspace --question "<question>"
```

`SOURCE_MISMATCH` means the active interpreter is importing project modules from a different checkout. Activate the intended interpreter and reinstall this checkout editable with that interpreter:

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

Source preparation owns the immutable evidence boundary. The effective order is:

```text
source-batch ingest
→ deterministic clause/structural-link/reference-link materialization
→ final logical snapshot hash and retrieval-index verification
→ writer close
→ create-only publish
→ exact closed-file SHA-256
→ workspace bind
→ frozen/read-only review
```

The logical snapshot hash identifies canonical evidence rows; the exact file
SHA-256 identifies the closed published `evidence.sqlite` artifact. Separate
rebuilds may have the same logical hash without byte-identical SQLite files,
but the file SHA must remain unchanged after one workspace is bound. Review
readers fail closed on an unfinalized or stale database, reject SQLite WAL,
SHM, and journal sidecars, and never repair it.
Re-prepare an old workspace through `$ERS_PDF` instead of adding a review-time
repair step.

## 2. Formal Review for review questions

The current user-facing workflow is `review-question`. Do not use a separate quick retrieval mode and do not ask the user to hand-author intermediate JSON.

Every natural-language review question follows this authority chain. Explicit
Evidence Navigation and Workbench operations are workspace actions, not answers
to a review question, and do not create a Planner handoff or Formal Review
packet.

```text
question
→ external AI Question Planner
→ fail-closed QuestionPlan validation
→ deterministic local retrieval
→ immutable review request
→ Track A
→ Track B
→ finalizer
→ human review
```

The Python core never calls the planner model. Codex is the external planner at a deterministic file handoff.

### 2.1 Prepare the Question Planner handoff

```powershell
evidence-review review-question prepare-plan `
  --workspace <workspace> `
  --question "<question>"
```

Expected status: `WAITING_QUESTION_PLAN`.

The command creates a deterministic planning directory containing:

```text
question-planner-bundle.json
QUESTION_PLANNER_INSTRUCTIONS.md
question-plan-output.json   # expected external output
```

Codex must read the bundle and instructions before writing `question-plan-output.json`. The planner receives the original question and contract identity, not evidence, and must not answer the question.

The QuestionPlan must:

- preserve the normalized original question;
- preserve user-stated facts, assumptions, numbers, negations, exceptions, names, and explicit citations;
- split issues only when independent evidence is required;
- generate the minimum bounded search requests needed for evidence collection;
- mark citations copied from the question as `source=user` and inferred citations as `source=planner`;
- contain no answer, conclusion, decision, compliance/eligibility judgment, confidence, or rule status.

There is no runtime SIMPLE/COMPOUND/COMPLEX classifier. Small questions should naturally produce small plans; complex questions may contain multiple issues and dependency edges.

Planner-inferred legal anchors are search hypotheses only. They are not legal authority until matching evidence is retrieved and cited.

### 2.2 Validate the Plan, retrieve evidence, and prepare the Run

After Codex writes `question-plan-output.json`:

```powershell
evidence-review review-question prepare `
  --workspace <workspace> `
  --question "<question>" `
  --question-plan-output <question-plan-output.json>
```

Optional inputs:

```text
--expansion <explicit-user-search-term>
--calculation-result <CalculationResult.json>
--rule-result <RuleResult.json>
--approved-rule-result-id <rule-result-id>
```

`--expansion` is reserved for an explicit user search term. Do not duplicate planner search requests through `--expansion`. If a user expansion normalizes to a planner term, user origin remains higher priority while planner issue/search lineage is retained.

Calculation and RuleResult artifacts must already be authoritative deterministic outputs.

The runtime validates the external Plan **before retrieval**. Invalid/missing planner output produces `PLANNER_FAILED`; it must not create a retrieval run and must not be reported as `RETRIEVAL_NO_EVIDENCE` or final `ABSTAIN`.

A valid Plan is converted to bounded `origin=llm` retrieval terms. Preparation writes or binds:

```text
question-plan.json
evidence-query.json
review-request.json
track-a-bundle.json
next-action-track-a.json
```

The review request includes `question_plan_sha256`, canonical plan context, and evidence-level retrieval lineage. `issue → search_request → evidence` lineage is diagnostic context only; it does not add retrieval score or citation authority.

The deterministic replay boundary is:

```text
same validated QuestionPlan
+ same evidence snapshot
+ same deterministic rule/math inputs
=> same deterministic retrieval/review preparation result
```

Do not claim that repeated external AI planning of the same question necessarily produces the same Plan.

If a valid Plan produces zero authoritative hits, preparation reports `RETRIEVAL_NO_EVIDENCE` and writes retrieval guidance. Do not broaden the query arbitrarily. Continue only through the formal next-action boundary so the existing finalizer can determine whether the run must end as `ABSTAIN`.

### 2.3 Produce and validate Track A immediately

Read only the run's `track-a-bundle.json` and `TRACK_A_INSTRUCTIONS.md`. Track A explains provided evidence, approved calculation results, and rule results. It cannot create evidence, alter numeric tokens, change rule status, assign a human decision, or bypass citations.

When `inputs.question_plan` is present, Track A must organize the explanation against validated issues while preserving facts, assumptions, and dependency structure. `inputs.retrieval_lineage` explains why an evidence item was retrieved; it does not authorize new evidence or make planner-inferred legal anchors authoritative.

After writing `track-a-output.json`, validate it before doing any Track B work:

```powershell
evidence-review review-question submit-track-a `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-a-output <track-a-output.json>
```

A failed validation keeps the workflow at Track A. Correct Track A and retry. Do not spend a Track B pass auditing a Track A output that has not passed this gate.

### 2.4 Produce Track B exactly once over the validated claims

Track B independently audits every validated Track A claim. It may accept/reject claims according to its contract but does not rewrite Track A or make the human decision.

```powershell
evidence-review review-question submit-track-b `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-b-output <track-b-output.json> `
  --publish
```

The runtime validates Track B before finalization. Finalization creates the run-specific `final-review-packet.json` and `review.html` only after all deterministic and Track gates pass. The legacy `--publish` compatibility flag reports that same run-local packet in the `packet` and `published_packet` CLI status fields, including on an idempotent terminal retry; it never creates a workspace-global packet copy.

Lower-level `review-run prepare` / `review-run finalize` remain compatibility and controlled-test interfaces. They are not the normal `$ERS_REVIEW` path.

## 3. Workflow journal and recovery

The event journal is the state authority for the formal question flow. It preserves ordered transitions through Track A, Track B, finalization, and ready-for-review states. Immutable artifacts are revalidated on resume. Interrupted or partially written restartable outputs are cleaned only when they can be safely regenerated; differing immutable artifacts fail closed.

A resume must never silently roll a completed Track A validation back to an earlier stage. Tampered artifacts or mismatching retry input stop the run.

The exact validated `question-plan.json` is part of the reproducibility boundary for planned question runs. A retry must not silently substitute a different Plan for an existing immutable run.

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

Planner generation occurs outside the deterministic runtime. Planner/Track A/Track B external wait is excluded from deterministic runtime totals.

Telemetry is intentionally non-authoritative: it is excluded from Run ID, run manifest, final packet, and evidence hashes.

`deterministic_total_ms` excludes external model waits. `retry_count` counts a new attempt only when the preceding attempt of the same stage failed. Failed stages retain a reason code.

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

Windows lifecycle behavior must be manually accepted on the exact target commit. Do not infer Windows PASS from POSIX process identity tests.

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

Focused suites for Question Planner and formal review:

```powershell
py -3.13 -m pytest -v tests/unit/llm_layer/test_question_planner.py
py -3.13 -m pytest -v tests/unit/llm_layer/test_question_planner_cli.py
py -3.13 -m pytest -v tests/unit/llm_layer/test_question_planner_safety.py
py -3.13 -m pytest -v tests/unit/retrieval tests/integration/retrieval
py -3.13 -m pytest -v tests/integration/review_question/test_planned_question_flow.py
py -3.13 -m pytest -v tests/integration/review_question/test_question_planner_cli_flow.py
py -3.13 -m pytest -v tests/integration/review_question
py -3.13 -m pytest -v tests/integration/review_packet
py -3.13 -m pytest -v tests/integration/review_run
py -3.13 -m pytest -v tests/unit/review_packet
```

Packaging/release acceptance additionally requires a Python 3.13 wheel/runtime smoke test and confirmation that `evidence_review.llm_layer/templates/question-planner.md` is included as package data.

Current release acceptance uses Python 3.13 only. It requires three simple-question timing samples with p50/p95, browser QA at 1366×768 / 1920×1080 / 3840×2160, protected decision, archival envelope/import, browser-open failure, and server status/stop evidence.

Record unexecuted gates as `NOT_RUN`. GitHub Actions must be reported separately as its actual observed state; it is not replaced by local validation.
