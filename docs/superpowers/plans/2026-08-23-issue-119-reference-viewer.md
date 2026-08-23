# Issue #119 Reference Viewer Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing Visual Review Workspace so every visual Finding can display and independently focus its authoritative Text, Table, PDF, Image, Diagram, or Drawing reference while preserving the existing subject viewer, routing, payload, and legal-authority contracts.

**Architecture:** Keep the final review packet unchanged and enrich only the read-only review projection. Resolve safe reference-type metadata while the Evidence DB is open, materialize unique cited reference pages from the existing verified page cache, attach independent reference anchors and subject regions to projected Findings, and render both viewers with separate transform state. In visual mode, omit the hidden legacy PDF viewer so each archival raster is serialized once; preserve protected-server lazy delivery through existing citation provenance.

**Tech Stack:** Python 3.13, pytest, SQLite, pypdfium2/Pillow-produced cached PNGs, server-rendered HTML/CSS/vanilla JavaScript, Node harness tests, Codex in-app Browser QA.

**Spec:** `docs/superpowers/specs/2026-08-23-issue-119-reference-viewer-design.md`

## Global Constraints

- Work from `main@864686b67c80b5a35d0608af5754281a6a38aceb` on `codex/issue-119-reference-viewer`; do not merge to `main`.
- Do not create ReviewPacket v3 or change final packet/human-decision schemas.
- `REFERENCE_DOCUMENT` stays in the reference parser/Evidence DB/page-image pipeline.
- `CASE_DRAWING` and `SUPPORTING_IMAGE` stay in the case-visual pipeline.
- General reference PDF cache remains 2x; CASE PDF cache remains 4x.
- Reference projection is presentation metadata only and cannot create evidence, calculations, rule outcomes, confidence authority, or human decisions.
- Cell-level Table focus requires an explicit parser-provided target; never infer it from Track prose.
- One archival raster data URI may appear only once, and raster data must be absent from `#review-model` JSON.
- Preserve existing Subject wheel zoom, left-drag pan, Fit, page navigation, SVG overlay, and 26%-70% divider behavior.
- 1366x768 uses a Findings drawer; 1440x900 and 1920x1080 keep the three visible regions.
- Tile rendering is out of scope unless measured evidence shows an acceptance-blocking need.
- Every production change follows a witnessed RED -> GREEN cycle.

---

### Task 1: Project safe reference-type metadata from Evidence DB records

**Files:**
- Create: `src/evidence_review/review_packet/reference_projection.py`
- Modify: `src/evidence_review/review_packet/builder.py`
- Modify: `tests/unit/review_packet/test_builder.py`
- Create: `tests/unit/review_packet/test_reference_projection.py`

**Interfaces:**
- Produces: `project_reference_record(*, evidence_type: str, element_type: str | None, element_raw_json: str | None, table_raw_json: str | None, visual_kind: str | None) -> dict[str, object]`.
- Produces citation fields: `document_page_count: int` and `reference: {type, table, visual}`.
- Table projection exposes only bounded `cells` with `row`, `column`, `text`, `row_span`, `column_span`, and `selected`; raw parser JSON is never returned.

- [ ] **Step 1: Write failing builder tests for Text, Table, and Diagram metadata**

Extend `_db()` with page-bound `elements`, `tables`, and `visuals` fixtures and add literal assertions:

```python
assert text_citation["reference"] == {"type": "TEXT", "table": None, "visual": None}
assert table_citation["reference"]["type"] == "TABLE"
assert table_citation["reference"]["table"]["cells"][1] == {
    "row": 1,
    "column": 0,
    "text": "3.0m 이상",
    "row_span": 1,
    "column_span": 1,
    "selected": True,
}
assert diagram_citation["reference"] == {
    "type": "DIAGRAM",
    "table": None,
    "visual": {"kind": "composite_diagram"},
}
assert table_citation["document_page_count"] == 3
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `python -m pytest -q tests/unit/review_packet/test_builder.py tests/unit/review_packet/test_reference_projection.py`

Expected: FAIL because `_resolve_citation()` does not return `reference` or `document_page_count`, and `reference_projection.py` does not exist.

- [ ] **Step 3: Implement bounded record classification and semantic table normalization**

Implement exact type mapping in `reference_projection.py`:

```python
ReferenceType = Literal["TEXT", "TABLE", "PDF_PAGE", "IMAGE", "DIAGRAM", "DRAWING"]

def project_reference_record(...: str | None) -> dict[str, object]:
    # table/table element -> TABLE
    # visual/figure/image/diagram/drawing -> parser-kind mapping
    # clause/text/paragraph -> TEXT
    # remaining page-bound evidence -> PDF_PAGE
```

Accept a table `cells` array only when every exposed cell has non-negative integer row/column, string text, positive spans, and boolean `selected`. Cap output at 200 cells and each text value at 1,000 characters; return `table=None` for malformed or oversized structures.

- [ ] **Step 4: Enrich `_resolve_citation()` without changing identity validation**

Join `revisions`, `elements`, `tables`, and `visuals` by the already-resolved retrieval record identity. Add only `document_page_count` and the safe `reference` result. Keep `_citation_identity()` unchanged so packet authority remains the existing citation fields.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python -m pytest -q tests/unit/review_packet/test_builder.py tests/unit/review_packet/test_reference_projection.py`

Expected: all selected tests PASS.

- [ ] **Step 6: Commit the completed TDD slice**

```powershell
git add src/evidence_review/review_packet/reference_projection.py src/evidence_review/review_packet/builder.py tests/unit/review_packet/test_builder.py tests/unit/review_packet/test_reference_projection.py
git commit -m "feat: project safe reference viewer metadata"
```

### Task 2: Materialize unique verified reference pages and PDF-coordinate anchors

**Files:**
- Modify: `src/evidence_review/review_packet/reference_projection.py`
- Modify: `tests/unit/review_packet/test_reference_projection.py`

**Interfaces:**
- Produces: `build_reference_projection(citations: Sequence[Mapping[str, object]], *, page_root: Path) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, dict[str, object]]]`.
- Tuple members are `reference_documents`, unique `reference_pages`, and `anchor_by_citation_id`.
- Consumes: `read_verified_page_image()` and citation page geometry.

- [ ] **Step 1: Write failing verified-page and anchor tests**

Create two page cache fixtures under `page-images/REV-TEXT/page-0005.*` and `page-images/REV-TABLE/page-0002.*`. Assert:

```python
assert [page["page"] for page in pages] == [5, 2]
assert len(pages) == 2
assert pages[0]["data_uri"].startswith("data:image/png;base64,")
assert anchors["CIT-TEXT"]["bbox"] == {
    "coordinate_system": "PDF_BOTTOM_LEFT_POINTS",
    "coordinates": [72.0, 420.0, 510.0, 460.0],
}
assert anchors["CIT-TEXT"]["page_asset_key"] == pages[0]["asset_key"]
assert documents[0]["page_asset_keys"] == [pages[0]["asset_key"]]
```

Add a duplicate-citation-on-one-page case and assert one raster page with two anchors. Add hash and geometry mismatch cases that raise existing verification errors.

- [ ] **Step 2: Run the reference projection tests and verify RED**

Run: `python -m pytest -q tests/unit/review_packet/test_reference_projection.py`

Expected: FAIL because `build_reference_projection()` is absent.

- [ ] **Step 3: Implement unique page materialization and anchor construction**

Deduplicate by `(revision_id, page_number, source_hash)`, preserve first citation order, validate `page_width`, `page_height`, origin, rotation, and box kind against `VerifiedPageImage`, and encode each verified `image_bytes` once. Use sequential asset keys `reference-page-1`, `reference-page-2` so internal document IDs do not appear in visible labels.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest -q tests/unit/review_packet/test_reference_projection.py`

Expected: PASS.

- [ ] **Step 5: Commit the completed TDD slice**

```powershell
git add src/evidence_review/review_packet/reference_projection.py tests/unit/review_packet/test_reference_projection.py
git commit -m "feat: materialize verified reference anchors"
```

### Task 3: Bind independent reference anchors and subject regions to Findings

**Files:**
- Modify: `src/evidence_review/review_packet/case_visual_projection.py`
- Modify: `tests/unit/review_packet/test_case_visual_projection.py`

**Interfaces:**
- Consumes: `build_reference_projection()` and existing candidate -> claim -> citation lineage.
- Produces: `case_visual_review.reference_documents`, `reference_pages`, and `findings`.
- Each Finding contains `finding_id`, `reference_anchors`, and `subject_region` with independent asset/page/geometry fields.

- [ ] **Step 1: Extend the fixture with a verified reference page and resolved citation**

Add `view_model["claims"]` citation data and a `page-images/REV-REF/page-0012.*` fixture. Write literal assertions:

```python
finding = result["findings"][0]
assert finding["reference_anchors"][0]["page"] == 12
assert finding["reference_anchors"][0]["page_asset_key"].startswith("reference-page-")
assert finding["subject_region"] == {
    "page_asset_key": "ATT-VISUAL-1-p1",
    "attachment_id": "ATT-VISUAL-1",
    "page": 1,
    "geometry": candidate["geometry"],
}
assert finding["reference_anchors"][0]["bbox"]["coordinate_system"] != finding["subject_region"]["geometry"]["coordinate_system"]
```

Add a citation-free visual observation test asserting an empty `reference_anchors` array without inventing evidence.

- [ ] **Step 2: Run projection tests and verify RED**

Run: `python -m pytest -q tests/unit/review_packet/test_case_visual_projection.py`

Expected: FAIL because the projection has no `reference_pages` or `findings`.

- [ ] **Step 3: Implement Finding projection with stable lineage order**

Collect only citations referenced by claims linked to a candidate. Build the global reference projection once, then copy the corresponding safe anchor documents into each Finding. Preserve the current candidate objects under subject pages for overlay compatibility.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest -q tests/unit/review_packet/test_case_visual_projection.py`

Expected: PASS.

- [ ] **Step 5: Commit the completed TDD slice**

```powershell
git add src/evidence_review/review_packet/case_visual_projection.py tests/unit/review_packet/test_case_visual_projection.py
git commit -m "feat: bind dual anchors to visual findings"
```

### Task 4: Render Text, Table, PDF, Image, Diagram, and Drawing references

**Files:**
- Modify: `src/evidence_review/review_packet/render_case_visual.py`
- Modify: `tests/unit/review_packet/test_case_visual_renderer.py`

**Interfaces:**
- Consumes: projection collections from Task 3.
- Produces: Reference toolbar/stage/page/detail DOM with `data-reference-*` hooks.
- Reference page `<img>` uses `data-page-image-source` and each detail uses existing exact `<article class="citation" ...>` provenance attributes.

- [ ] **Step 1: Write failing renderer tests for all semantic types**

Expand `_model()` with six anchors and assert actual renderer output rather than source text:

```python
assert 'data-reference-page="reference-page-1"' in html
assert 'data-page-image-source="reference-page-1"' in html
assert 'data-reference-type="TEXT"' in html
assert '<mark class="reference-quote-highlight">' in html
assert 'data-table-cell="1:0"' in html
assert 'class="reference-table-cell is-target"' in html
assert 'data-reference-type="DIAGRAM"' in html
assert 'class="reference-overlay"' in html
assert '<rect class="reference-anchor-shape"' in html
assert 'data-reference-prev' in html and 'data-reference-next' in html
assert 'data-reference-zoom-in' in html and 'data-reference-fit' in html
```

Assert a citation-free Finding still renders the explicit no-reference state. Assert no raw confidence, raw bbox coordinates, or internal IDs appear in visible text.

- [ ] **Step 2: Run renderer tests and verify RED**

Run: `python -m pytest -q tests/unit/review_packet/test_case_visual_renderer.py`

Expected: FAIL because Reference remains a text-card fallback.

- [ ] **Step 3: Add page, overlay, and semantic detail render helpers**

Implement private helpers with exact responsibilities:

```python
def _reference_page(page: Mapping[str, object], anchors: Sequence[Mapping[str, object]]) -> str: ...
def _reference_overlay(anchor: Mapping[str, object], page: Mapping[str, object]) -> str: ...
def _reference_detail(anchor: Mapping[str, object], *, active: bool) -> str: ...
def _reference_table(table: Mapping[str, object]) -> str: ...
```

Reuse the existing PDF rotation equations from `_citation_render()` when converting bottom-left PDF bbox coordinates to SVG top-left coordinates. Escape every text value through `_text()`.

- [ ] **Step 4: Replace reference-card-only markup with the common document renderer**

Render the Reference toolbar, page stage, SVG overlay, and detail sheet. Keep the Subject markup and all existing Subject data hooks unchanged until Task 5.

- [ ] **Step 5: Strip reference and subject raster payloads after `<img>` emission**

Replace `_strip_case_raster_payload()` with a projection payload stripper that removes `data_uri` from both `pages` and `reference_pages` only after HTML fragments are built.

- [ ] **Step 6: Run renderer tests and verify GREEN**

Run: `python -m pytest -q tests/unit/review_packet/test_case_visual_renderer.py`

Expected: PASS.

- [ ] **Step 7: Commit the completed TDD slice**

```powershell
git add src/evidence_review/review_packet/render_case_visual.py tests/unit/review_packet/test_case_visual_renderer.py
git commit -m "feat: render reference documents in visual workspace"
```

### Task 5: Implement independent Reference and Subject focus/interaction controllers

**Files:**
- Modify: `src/evidence_review/review_packet/render_case_visual.py`
- Modify: `tests/unit/review_packet/test_case_visual_renderer.py`
- Modify: `tests/integration/review_packet/test_review_workspace_ui.py`

**Interfaces:**
- Produces JavaScript functions `showReferencePage`, `showSubjectPage`, `focusStage`, `fitStage`, `activateFinding`, and independent per-stage `WeakMap` state.
- Both viewers support wheel, pointer pan, double-click Fit, buttons, and page navigation.

- [ ] **Step 1: Write failing Node-harness interaction tests**

Extract `CASE_VISUAL_SCRIPT`, evaluate it with minimal real selector/state doubles, and prove these observable behaviors:

```text
activate second Finding -> reference page 12 active
activate second Finding -> subject page 3 active
reference transform changes using reference bbox
subject transform changes using subject geometry
reference zoom button changes only reference transform/label
subject wheel changes only subject transform/label
left pointer drag changes the targeted stage x/y
double click resets only the targeted stage
```

Retain explicit source assertions for pointer capture, passive-false wheel handling, 0.5-5.0 clamp, and subject page controls.

- [ ] **Step 2: Run interaction tests and verify RED**

Run: `python -m pytest -q tests/unit/review_packet/test_case_visual_renderer.py tests/integration/review_packet/test_review_workspace_ui.py`

Expected: FAIL because Reference has no controller and Finding activation does not focus either bbox.

- [ ] **Step 3: Implement shared mechanics with separate stage instances**

Use one `WeakMap` keyed by the actual stage node. `focusStage()` receives the selected viewer's content width/height and top-left focus box, calculates the contained content rectangle, centers the focus box, and clamps scale to `[0.5, 5]`. Never read transform state from the other viewer.

- [ ] **Step 4: Bind Finding activation and both control groups**

On activation, toggle the Finding, reference detail, reference overlay, and subject overlay; select the independent pages; then focus each visible stage through `requestAnimationFrame`. Bind previous/next, wheel, pan, double-click, `+`, `-`, and Fit for each viewer.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `python -m pytest -q tests/unit/review_packet/test_case_visual_renderer.py tests/integration/review_packet/test_review_workspace_ui.py`

Expected: PASS.

- [ ] **Step 6: Commit the completed TDD slice**

```powershell
git add src/evidence_review/review_packet/render_case_visual.py tests/unit/review_packet/test_case_visual_renderer.py tests/integration/review_packet/test_review_workspace_ui.py
git commit -m "feat: focus reference and subject independently"
```

### Task 6: Add the 1366 Findings drawer without regressing wider layouts

**Files:**
- Modify: `src/evidence_review/review_packet/render_case_visual.py`
- Modify: `tests/unit/review_packet/test_case_visual_renderer.py`
- Modify: `tests/integration/review_packet/test_review_visual_contract.py`

**Interfaces:**
- Produces: `data-findings-toggle`, `data-findings-close`, `data-findings-backdrop`, and root `data-findings-open` state.
- CSS breakpoint: `@media(max-width:1366px)` drawer; three columns remain above 1366px.

- [ ] **Step 1: Write failing responsive DOM/CSS contract tests**

Assert literal behavioral hooks and breakpoint rules:

```python
assert 'data-findings-toggle' in html
assert 'data-findings-close' in html
assert '@media(max-width:1366px)' in html
assert '.findings-panel{position:absolute' in media_1366
assert 'transform:translateX(100%)' in media_1366
assert '[data-findings-open="true"] .findings-panel' in media_1366
assert '@media(max-width:1439px)' not in html
```

Keep the existing viewport-workspace, divider, and no-body-scroll assertions.

- [ ] **Step 2: Run responsive tests and verify RED**

Run: `python -m pytest -q tests/unit/review_packet/test_case_visual_renderer.py tests/integration/review_packet/test_review_visual_contract.py`

Expected: FAIL because no 1366 drawer contract exists.

- [ ] **Step 3: Implement drawer markup, state, focus return, and compact toolbars**

At 1366px and below, remove Findings from grid width, position it off-canvas, display its backdrop only while open, close on Escape/backdrop/close button, and return focus to the toggle. Keep Reference and Subject split visible. At 1440px and above, hide the toggle and render all three regions.

- [ ] **Step 4: Run responsive tests and verify GREEN**

Run: `python -m pytest -q tests/unit/review_packet/test_case_visual_renderer.py tests/integration/review_packet/test_review_visual_contract.py`

Expected: PASS.

- [ ] **Step 5: Commit the completed TDD slice**

```powershell
git add src/evidence_review/review_packet/render_case_visual.py tests/unit/review_packet/test_case_visual_renderer.py tests/integration/review_packet/test_review_visual_contract.py
git commit -m "feat: add findings drawer at 1366 viewport"
```

### Task 7: Remove visual-mode raster duplication and preserve protected lazy delivery

**Files:**
- Modify: `src/evidence_review/review_packet/html_renderer.py`
- Modify: `src/evidence_review/review_packet/local_server.py`
- Modify: `tests/integration/review_packet/test_html_renderer.py`
- Modify: `tests/integration/review_packet/test_protected_image_delivery.py`
- Modify: `tests/integration/review_packet/test_review_workspace_performance.py`

**Interfaces:**
- Visual mode omits `_render_evidence_viewer()` and does not call `_page_assets()` for a second reference copy.
- Existing non-visual rendering remains byte-for-byte behaviorally compatible.
- Protected Reference images continue to become tokenized `data-page-src` URLs.

- [ ] **Step 1: Write failing archival payload regression tests**

Build a visual model containing one Subject raster and one Reference raster and assert:

```python
assert html.count(reference_data_uri) == 1
assert html.count(subject_data_uri) == 1
embedded_model = json.loads(review_model_match.group("model"))
assert "data_uri" not in embedded_model["case_visual_review"]["reference_pages"][0]
assert "data_uri" not in embedded_model["case_visual_review"]["pages"][0]
assert 'id="evidence-viewer"' not in html
```

Add a non-visual test proving the existing evidence viewer still embeds its page once.

- [ ] **Step 2: Write a failing protected Reference lazy-delivery test**

Serve a visual archival HTML and assert the protected response contains the Subject presentation plus:

```python
assert reference_data_uri.encode() not in protected
assert b'data-page-src="./page-images/REV1/3/' in protected
assert delivered_reference_bytes == reference_page_bytes
```

The test must also assert that no reference page identity can be served with a wrong revision/page/hash.

- [ ] **Step 3: Run payload/server tests and verify RED**

Run: `python -m pytest -q tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_protected_image_delivery.py tests/integration/review_packet/test_review_workspace_performance.py`

Expected: FAIL because visual mode still creates the hidden legacy viewer and protected HTML does not recognize the new Reference page markup.

- [ ] **Step 4: Make visual-mode HTML composition explicit**

In `render_review_html()`, branch on `case_visual_review` before `_page_assets()`. Render the Visual Workspace, decision form, and audit surface without the legacy evidence list/viewer/detail fragments. Leave the non-visual branch unchanged.

- [ ] **Step 5: Extend protected presentation handling only for tagged Reference pages**

Keep `_asset_page_identities()` citation-based. Ensure new Reference citation articles supply the mapping. Replace only `img[data-page-image-source]` archival base64 with the existing protected route. If Subject base64 remains, do not treat it as a failed Reference lazy conversion; continue enforcing that no tagged Reference image retains embedded bytes.

- [ ] **Step 6: Run tests and verify GREEN**

Run: `python -m pytest -q tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_protected_image_delivery.py tests/integration/review_packet/test_review_workspace_performance.py`

Expected: PASS.

- [ ] **Step 7: Commit the completed TDD slice**

```powershell
git add src/evidence_review/review_packet/html_renderer.py src/evidence_review/review_packet/local_server.py tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_protected_image_delivery.py tests/integration/review_packet/test_review_workspace_performance.py
git commit -m "fix: serialize visual reference rasters once"
```

### Task 8: Lock routing and performance regressions

**Files:**
- Modify: `tests/unit/review_question/test_case_visual_routing.py`
- Modify: `tests/unit/workflow/test_reference_backend.py`
- Modify: `tests/integration/test_case_visual_formal_review.py`
- Modify: `tests/integration/review_packet/test_review_workspace_performance.py`

**Interfaces:**
- No production interface changes are expected in this task.
- Performance evidence records unique raster count, HTML bytes, render seconds, and bounded process memory delta when available.

- [ ] **Step 1: Add routing assertions that would fail on role crossover**

Assert `REFERENCE_DOCUMENT` reaches `SourceBatchReferenceBackend` and never appears in `case_visual_context`; assert `CASE_DRAWING` remains parser-metadata-free and visual-bound. Use real request/attachment objects, not mocks of the behavior under test.

- [ ] **Step 2: Add a 20-page/100-citation visual performance fixture**

Create 20 small valid reference page assets, 100 citation anchors, and one Subject page. Assert 20 unique reference data URIs, no duplicate model payload, HTML size equal to one encoding per page plus bounded markup overhead, and local render time at or below the existing 5-second deterministic budget.

- [ ] **Step 3: Run the focused regression group and witness its initial result**

Run: `python -m pytest -q tests/unit/review_question/test_case_visual_routing.py tests/unit/workflow/test_reference_backend.py tests/integration/test_case_visual_formal_review.py tests/integration/review_packet/test_review_workspace_performance.py`

Expected: new assertions PASS if Tasks 1-7 preserved routing; any failure is treated as a regression and fixed only after adding or retaining the failing test.

- [ ] **Step 4: Fix only observed regressions and rerun until GREEN**

Do not alter role validation or page cache scale policies to satisfy tests. Re-run the exact command and require exit code 0.

- [ ] **Step 5: Commit the completed regression slice**

```powershell
git add tests/unit/review_question/test_case_visual_routing.py tests/unit/workflow/test_reference_backend.py tests/integration/test_case_visual_formal_review.py tests/integration/review_packet/test_review_workspace_performance.py
git commit -m "test: lock reference viewer routing and performance"
```

### Task 9: Generate actual review HTML and complete Browser QA

**Files:**
- Do not commit screenshots, traces, temporary Browser scripts, or generated run artifacts.
- Record durable measurements in the final report and Issue #119 comment.

**Interfaces:**
- Uses an existing valid workspace/run where possible; otherwise creates a temporary workspace outside tracked source from test fixtures.
- Uses the in-app Browser plugin, not shell-launched Chrome.

- [ ] **Step 1: Read and follow the Browser control skill**

Load `browser:control-in-app-browser` before the first Browser action. Define the flow:

```text
protected review route -> select Finding -> both Reference and Subject focus -> resize/focus controls -> responsive Findings drawer -> human-decision panel remains available
```

- [ ] **Step 2: Generate a fresh review HTML with actual cached Reference and Subject rasters**

Prefer Scenario A (`REFERENCE_DOCUMENT PDF <-> CASE_DRAWING PDF`) and include Text, Table, and visual anchors in separate Findings when the available evidence permits. Record run ID, source identities, raster dimensions/bytes, generated HTML bytes, render duration, and process memory delta.

- [ ] **Step 3: Validate 1920x1080**

Check page identity, nonblank DOM, no framework overlay, console errors/warnings, screenshot, Finding navigation, independent focus, both viewers' wheel/pan/Fit/page controls, divider drag/reset, pagination, no body vertical scroll, and decision off-canvas access.

- [ ] **Step 4: Validate 1440x900**

Repeat the interaction loop and verify all three regions remain visible and readable with compact controls.

- [ ] **Step 5: Validate 1366x768**

Verify Reference and Subject remain readable, Findings is closed by default as a drawer, toggle/open/close/Escape/backdrop work, focus returns to the toggle, and the page body does not become the main scroll surface.

- [ ] **Step 6: Record unavailable manual scenarios precisely**

If Scenario B, C, or D cannot be created from authoritative local inputs, record `NOT_EXECUTED` with the missing input. Do not synthesize legal evidence to force a PASS.

### Task 10: Run complete verification and report Issue #119 status

**Files:**
- Modify only files required by failures reproduced during verification, always with a failing regression test first.

**Interfaces:**
- Produces fresh command evidence for completion claims.
- Posts one evidence-backed GitHub Issue #119 comment; does not close the issue unless every explicit automated and manual gate is actually complete and the user separately authorizes closure.

- [ ] **Step 1: Run focused tests**

```powershell
python -m pytest -q tests/unit/review_packet/test_reference_projection.py tests/unit/review_packet/test_builder.py tests/unit/review_packet/test_case_visual_projection.py tests/unit/review_packet/test_case_visual_renderer.py tests/unit/review_question/test_case_visual_routing.py tests/unit/workflow/test_reference_backend.py tests/integration/test_case_visual_formal_review.py tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_protected_image_delivery.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/review_packet/test_review_visual_contract.py tests/integration/review_packet/test_review_workspace_performance.py
```

Require exit code 0 and report the exact passed/skipped count.

- [ ] **Step 2: Run required static verification**

```powershell
python -m ruff check src tests
python -m mypy src/evidence_review
python -m compileall -q src
```

Require exit code 0 for each command.

- [ ] **Step 3: Run the complete regression suite**

Run: `python -m pytest -q tests`

Require exit code 0. Record the exact count; it must be greater than the `1640 passed, 1 skipped` baseline unless tests were deliberately consolidated with equivalent coverage.

- [ ] **Step 4: Inspect final diff and branch relationship**

```powershell
git diff --check main...HEAD
git status --short --branch
git rev-list --left-right --count main...HEAD
git diff --name-status main...HEAD
```

Confirm unrelated untracked user artifacts remain untouched.

- [ ] **Step 5: Use `superpowers:verification-before-completion` and `superpowers:finishing-a-development-branch`**

Re-read both skill files, map every Issue #119 acceptance item to fresh evidence, and mark unexecuted items `NOT_EXECUTED` rather than inferring PASS.

- [ ] **Step 6: Post the verified Issue #119 comment**

Write the verified comment body to `$env:TEMP\evidence-review-issue-119-comment.md`, then use `gh issue comment 119 --repo sage1993/evidence-review-system --body-file "$env:TEMP\evidence-review-issue-119-comment.md"` only after all report facts are backed by the current command/browser outputs. Include branch/HEAD, tests, viewport QA, payload/performance measurements, and remaining risks. Do not close or merge.

- [ ] **Step 7: Deliver the requested final report and wait for merge approval**

Report sections exactly as requested: 구현 결과, Issue #119 Acceptance table, 테스트, 실제 QA, 성능, 남은 항목, Git. State that `main` was not modified or merged.
