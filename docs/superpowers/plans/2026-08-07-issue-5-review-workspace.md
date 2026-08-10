# Issue #5 Review Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use \`superpowers:subagent-driven-development\` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Replace the current linear \`review.html\` report with the Issue #5 self-contained local review workspace while preserving v1/v2 packet authority and human-decision separation.

**Architecture:** Keep packet decoding and evidence resolution in a read-only Python view model. Render one self-contained HTML document containing verified page assets, CSS, an inert serialized model, and a small projection-only controller for selection, tabs, navigation, zoom, and decision transport. Serve the same run-local artifact through a token-scoped loopback server and write decisions only through the existing append-only writer.

**Tech Stack:** Python 3.11+, stdlib \`html\`, \`json\`, \`hashlib\`, \`http.server\`, existing SQLite \`EvidenceStore\`, inline HTML/CSS/JavaScript, pytest, Ruff, mypy.

## Global Constraints

- Runtime remains offline; no remote API or model call may be added.
- Machine packets are read-only authority and always keep \`human_decision: null\`.
- v1 packets remain readable; v2 packet contracts and golden fixtures remain authoritative.
- Browser JavaScript may perform only selection, tabs, page navigation, zoom, scrolling, and same-origin decision transport.
- Browser JavaScript must not perform arithmetic, rounding, threshold comparison, rule evaluation, source resolution, or packet mutation.
- Every displayed citation retains document ID, revision ID, page, element/evidence ID, bbox/geometry, and source hash.
- HTML contains no external scripts, stylesheets, fonts, images, network resources, or CDN URLs.
- Original evidence and machine artifacts are never overwritten; human decisions are separate append-only records.
- Server routes bind to \`127.0.0.1\`, use run-scoped URL-safe tokens, exact Host/Origin checks, bounded JSON bodies, safe run roots, and CSP.
- Existing timezone-aware \`reviewed_at\` remains the canonical decision timestamp.

---

### Task 1: Define the reviewer view-model projection

**Files:**
- Modify: \`src/ansim_review/review_packet/builder.py\`
- Test: \`tests/unit/review_packet/test_builder.py\`
- Create: \`tests/integration/review_packet/test_view_model.py\`

**Interfaces:**
- Preserve \`build_review_view_model(packet, evidence_db)\`.
- Add \`metadata\` with run/case/status/hash/manifest fields.
- Add \`summary\` with citation, approved-rule, calculation, missing-input, conflict, and confidence metrics.
- Add \`review_items\` with \`item_id\`, \`claim_id\`, \`evaluation_id\`, status, completeness, citation IDs, calculation IDs, rule IDs, and confirmation requirement.
- Add \`audit\` with Track A/B status, uncited count, confidence factors, exceptions, conflicts, and abstention reasons.
- Add \`decision\` with the four allowed values, \`human_decision: None\`, and exact packet SHA-256.

- [ ] **Step 1: Write the failing tests**

Use real v1/v2 fixtures and an evidence DB:

~~~python
model = build_review_view_model(packet, evidence_db)
assert model["metadata"]["packet_sha256"] == expected_hash
assert model["summary"]["citation_count"] == 1
assert model["review_items"][0]["claim_id"] == "C1"
assert model["decision"]["human_decision"] is None
~~~

Also assert that non-null machine decisions, conflicting citation identity, and unresolved cited evidence raise \`ValueError\`.

- [ ] **Step 2: Verify RED**

Run:

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_view_model.py -q
~~~

Expected: the new projection assertions fail because the new fields do not exist.

- [ ] **Step 3: Implement the minimal projection**

Add deterministic helpers:

~~~python
def _build_review_items(claims, calculations, rules) -> list[dict[str, object]]: ...
def _summary(citations, calculations, rules, confidence, exceptions, conflicts) -> dict[str, object]: ...
~~~

Build counts only from resolved records. Hash the exact packet bytes supplied by the caller, not a re-serialized mapping. Preserve all existing v1/v2 fields.

- [ ] **Step 4: Verify GREEN and regressions**

~~~powershell
python -m pytest tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_view_model.py tests/integration/contracts/test_review_v1_golden.py tests/integration/contracts/test_review_v1_to_v2.py -q
~~~

- [ ] **Step 5: Commit**

~~~powershell
git add src/ansim_review/review_packet/builder.py tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_view_model.py
git commit -m "feat: build issue 5 review workspace model"
~~~

### Task 2: Render the planned workspace and evidence viewer

**Files:**
- Modify: \`src/ansim_review/review_packet/html_renderer.py\`
- Modify: \`src/ansim_review/review_packet/assets/review.css\`
- Create: \`src/ansim_review/review_packet/assets/review.js\`
- Modify: \`tests/integration/review_packet/test_html_renderer.py\`
- Create: \`tests/integration/review_packet/test_review_workspace_ui.py\`

**Interfaces:**
- Preserve \`render_review_html(view_model, page_image_root) -> str\` and \`write_review_html(...) -> Path\`.
- Render hooks \`#review-status\`, \`#review-summary\`, \`#review-items\`, \`#evidence-viewer\`, \`#detail-tabs\`, \`#decision-form\`, and \`#review-model\`.
- Embed each verified page image once per \`(revision_id, page_number, source_hash)\`; citations reference an asset key and draw their own SVG overlay.
- Every selectable item and detail panel carries the matching stable item ID.

- [ ] **Step 1: Write failing renderer tests**

Use two claims sharing one page asset:

~~~python
html = render_review_html(model, page_image_root)
assert 'id="review-summary"' in html
assert 'id="review-items"' in html
assert 'id="evidence-viewer"' in html
assert 'id="detail-tabs"' in html
assert 'id="decision-form"' in html
assert html.count("data:image/png;base64,") == 1
assert "Math." not in html
~~~

Assert escaped user strings, blank decision controls, ready/abstain sections, and no external resources.

- [ ] **Step 2: Verify RED**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_review_workspace_ui.py -q
~~~

Expected: the new hooks and deduplication assertion fail against the linear renderer.

- [ ] **Step 3: Implement semantic HTML and asset deduplication**

Add renderer helpers:

~~~python
def _render_status_band(model: Mapping[str, object]) -> str: ...
def _render_summary(model: Mapping[str, object]) -> str: ...
def _render_review_items(model: Mapping[str, object]) -> str: ...
def _render_evidence_viewer(model: Mapping[str, object], assets: _PageAssets) -> str: ...
def _render_detail_tabs(model: Mapping[str, object]) -> str: ...
def _render_decision_form(model: Mapping[str, object]) -> str: ...
~~~

Create the page-asset map before rendering citations. Serialize only the normalized projection into \`#review-model\`, escaping \`<\`, \`>\`, \`&\`, U+2028, and U+2029.

- [ ] **Step 4: Implement CSS and projection-only controller**

Use CSS grid for desktop, stack columns under 1100px, and add A4 print rules. Add \`review.js\` functions:

~~~javascript
function selectReviewItem(itemId) {}
function activateDetailTab(tabName) {}
function focusEvidence(itemId, evidenceId) {}
function setEvidenceZoom(scale) {}
function submitDecision() {}
function downloadDecisionEnvelope() {}
~~~

The controller only toggles classes/visibility, changes image transform scale, and submits user-entered data. It contains no \`Math\`, domain arithmetic, threshold evaluation, or non-same-origin fetch.

- [ ] **Step 5: Verify GREEN**

~~~powershell
python -m pytest tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_review_workspace_ui.py -q
python -m compileall -q src
~~~

- [ ] **Step 6: Commit**

~~~powershell
git add src/ansim_review/review_packet/html_renderer.py src/ansim_review/review_packet/assets/review.css src/ansim_review/review_packet/assets/review.js tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_review_workspace_ui.py
git commit -m "feat: render issue 5 review workspace"
~~~

### Task 3: Add protected decision transport and server hardening

**Files:**
- Modify: \`web_runtime/review_server.py\`
- Modify: \`src/ansim_review/review_packet/decision_record.py\`
- Modify: \`tests/integration/test_review_routes.py\`
- Modify: \`tests/unit/review_packet/test_decision_record.py\`

**Interfaces:**
- Change \`create_review_server(workspace_root, *, run_tokens: Mapping[str, str], max_body_bytes: int = 65536)\`.
- Keep \`GET /runs/<run_id>/<token>/review\`; add read-only \`GET .../packet\` and \`.../packet/hash\`.
- Add same-origin \`POST .../decision\` accepting exactly \`reviewer_id\`, \`reviewed_at\`, \`packet_hash\`, \`decision\`, and \`notes\`.
- Persist only through \`write_human_decision(...)\` after comparing the submitted hash to exact packet bytes.

- [ ] **Step 1: Write failing security tests**

Cover missing/wrong token, non-loopback bind, wrong Host/Origin, CORS absence, traversal, symlink/reparse roots, oversized/duplicate/unknown JSON, unsupported decision, hash mismatch, missing HTML, and successful append-only record creation with unchanged packet bytes.

- [ ] **Step 2: Verify RED**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/integration/test_review_routes.py tests/unit/review_packet/test_decision_record.py -q
~~~

Expected: tokenized routes and POST tests fail against the current GET-only server.

- [ ] **Step 3: Implement the protected server**

Validate IDs and tokens, reject query/fragment and path separators, resolve only regular paths under the workspace, bind to \`("127.0.0.1", 0)\`, set no-store/nosniff/no-referrer/CSP headers, require exact Host and POST Origin, compare tokens with \`secrets.compare_digest\`, and use append-only creation.

- [ ] **Step 4: Verify GREEN**

~~~powershell
python -m pytest tests/integration/test_review_routes.py tests/unit/review_packet/test_decision_record.py -q
~~~

- [ ] **Step 5: Commit**

~~~powershell
git add web_runtime/review_server.py src/ansim_review/review_packet/decision_record.py tests/integration/test_review_routes.py tests/unit/review_packet/test_decision_record.py
git commit -m "feat: protect issue 5 review decisions"
~~~

### Task 4: Connect finalization and \`--open\` to the real route

**Files:**
- Modify: \`src/ansim_review/review_run.py\`
- Modify: \`src/ansim_review/cli.py\`
- Modify: \`src/ansim_review/cli_parser.py\`
- Create: \`src/ansim_review/review_packet/browser_launcher.py\`
- Create: \`tests/integration/review_packet/test_local_server.py\`
- Modify: \`tests/integration/review_run/test_review_run.py\`

**Interfaces:**
- Preserve \`finalize_review_run(...) -> FinalizedReviewRun\`.
- Add \`open_review_run(workspace_root: Path, run_id: str, *, browser: Callable[[str], bool] = webbrowser.open) -> str\`.
- \`review-run finalize --open\` prints only \`status\`, \`run_id\`, and the protected URL.
- Finalization creates packet and HTML before server startup or browser launch.

- [ ] **Step 1: Write failing CLI/launcher tests**

Assert that \`--open\` calls the browser with a tokenized localhost URL, the URL serves the exact run HTML, missing artifacts never open a final route, and packet bytes remain unchanged.

- [ ] **Step 2: Verify RED**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/integration/review_run/test_review_run.py tests/integration/review_packet/test_local_server.py -q
~~~

Expected: current \`--open\` emits a \`file:\` URI and the server has no tokenized launcher.

- [ ] **Step 3: Implement the launcher lifecycle**

Generate a cryptographically random run token only after \`review.html\` exists, retain the server handle for the browser session, and open \`/runs/<run_id>/<token>/review\`. Keep direct archival \`review.html\` generation unchanged.

- [ ] **Step 4: Verify GREEN and commit**

~~~powershell
python -m pytest tests/integration/review_run/test_review_run.py tests/integration/review_packet/test_local_server.py -q
git add src/ansim_review/review_run.py src/ansim_review/cli.py src/ansim_review/cli_parser.py src/ansim_review/review_packet/browser_launcher.py tests/integration/review_run/test_review_run.py tests/integration/review_packet/test_local_server.py
git commit -m "feat: open protected review workspace"
~~~

### Task 5: Add performance, responsive, and readiness coverage

**Files:**
- Create: \`tests/integration/review_packet/test_review_workspace_performance.py\`
- Modify: \`tests/integration/review_packet/test_html_renderer.py\`
- Modify: \`docs/CODEX_WORKFLOW.md\`
- Modify: \`docs/REVIEWER_WORKFLOW.md\`

- [ ] **Step 1: Write bounded fixture tests**

Generate deterministic 20-page/100-citation input with shared page assets. Assert image URI count equals unique pages, every item ID is present, render completes within a fixed local budget, and ready/abstain states show reasons without preselected decisions.

- [ ] **Step 2: Verify RED and implement only exposed projection defects**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/integration/review_packet/test_review_workspace_performance.py -q
~~~

Use the page-asset registry from Task 2; do not weaken evidence validation or remove sections to meet size limits.

- [ ] **Step 3: Update workflow documentation**

Document the tokenized route, archival \`file:\` behavior, decision endpoint fields, status domains, and the distinction between \`READY_FOR_HUMAN_REVIEW\` and approval.

- [ ] **Step 4: Verify and commit**

~~~powershell
python -m pytest tests/unit/review_packet tests/integration/review_packet tests/integration/review_run tests/integration/test_review_routes.py -q
git add tests/integration/review_packet docs/CODEX_WORKFLOW.md docs/REVIEWER_WORKFLOW.md
git commit -m "test: verify issue 5 review workspace readiness"
~~~

### Task 6: Full verification and browser QA

**Files:**
- Create: \`build/issue-5-review-workspace-qa.json\`

- [ ] **Step 1: Run fresh repository gates**

~~~powershell
$env:PYTHONPATH='src'
python -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output build/issue-5-review-workspace-qa.json
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
~~~

- [ ] **Step 2: Create deterministic ready and abstain runs**

Use existing golden packet/evidence helpers to create two run directories containing exact packet, HTML, verified page assets, and hashes. Do not use previous \`RUN-001\` or \`RUN-AD...\` fixtures as completion evidence.

- [ ] **Step 3: Inspect protected routes**

Open ready and abstain routes at 1366×768, 1920×1080, and 4K. Verify status, summary cards, selected claim, quote, page overlay, all detail tabs, exceptions/conflicts, and decision form. Verify POST creates a separate record and leaves packet bytes unchanged.

- [ ] **Step 4: Inspect print and archival output**

Stop the server, open the generated \`review.html\` directly, inspect print preview, and verify no external resource is required.

- [ ] **Step 5: Record QA**

Record exact commit, platform, Python version, commands, exit codes, viewport checks, artifact hashes, and remaining human-review requirements in \`build/issue-5-review-workspace-qa.json\` and the SDD ledger.

