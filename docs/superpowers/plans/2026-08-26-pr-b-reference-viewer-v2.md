# PR-B Reference Viewer v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the valid Reference Viewer capabilities from PR #121 on top of the merged PR-A + PR #122 `main`, without changing evidence authority or machine review outcomes.

**Architecture:** PR-B is presentation-only. It enriches validated direct citations and current #122 related-reference records with bounded reference type metadata, verified page assets, and independent reference anchors, then binds those anchors to semantic Findings. PR #122's `related_reference_routing`, `visual_findings`, subject HQ/tile rendering, `not_comparable`, selected-only behavior, Decision Drawer, and Track B immutability remain source of truth. PR #121 HEAD `efb8b54cc4b46cf3ca3a68f4f6680b387b2f723c` is reference material only; do not merge or cherry-pick it wholesale.

**Tech Stack:** Python 3.13, pytest, SQLite, verified PNG page cache, protected loopback lazy asset delivery, server-rendered HTML/CSS/vanilla JavaScript, existing Review Workspace.

**Spec:** `docs/superpowers/specs/2026-08-26-integrated-correctness-reference-viewer-design.md`

## Global Constraints

- Do not begin until PR-A has merged and Issue #116 real-corpus acceptance is PASS.
- Create PR-B from exact post-PR-A `origin/main`; record that SHA before edits.
- Preserve PR #122 as the Visual Review regression baseline.
- Reference projection cannot create or upgrade evidence, deterministic results, confidence, final status, or human decisions.
- Direct references remain deterministic Track A claim citations only.
- Related references remain retrieval-lineage-derived related material only; display/focus never promotes them to direct authority.
- Supported types are exactly `TEXT`, `TABLE`, `PDF_PAGE`, `IMAGE`, `DIAGRAM`, `DRAWING`.
- Table cell focus requires explicit validated parser metadata.
- Reference pages come only from verified page-image cache artifacts; no per-question source re-render.
- Reference raster bytes must not be duplicated in `#review-model` JSON.
- Preserve current Subject hooks and behavior: `data-case-page`, `data-case-finding`, `data-case-page-key`, `data-case-focus-bbox`, HQ/tile rendering, lazy delivery, zoom/pan/fit.
- Preserve 26%–70% resizable divider, selected-only, click-only Decision Drawer, ABSTAIN summary, and black-overlay protections.
- Browser QA at 1920×1080, 1440×900, and 1366×768 is mandatory.
- Python 3.13 is the acceptance runtime.

---

### Task 1: Create the Post-PR-A Worktree and Inventory #121-Only Behavior

**Files:**
- Read: `docs/superpowers/specs/2026-08-26-integrated-correctness-reference-viewer-design.md`
- Create: `docs/plans/2026-08-26-reference-viewer-v2-port-inventory.md`

**Interfaces:**
- Consumes: exact post-PR-A main and PR #121 HEAD.
- Produces: branch `agent/reference-viewer-v2` and a `PORT / KEEP_CURRENT_MAIN / DO_NOT_RESTORE_FROM_121` inventory.

- [ ] **Step 1: Create a fresh worktree from post-PR-A main**

```powershell
git fetch origin main codex/issue-119-reference-viewer
$base = git rev-parse origin/main
git worktree add F:\2026-PJ\evidence-review-system-reference-viewer-v2 -b agent/reference-viewer-v2 $base
Set-Location F:\2026-PJ\evidence-review-system-reference-viewer-v2
git status --short
git rev-parse HEAD
```

Expected: clean worktree and HEAD equal to `$base`.

- [ ] **Step 2: Run the post-PR-A baseline**

```powershell
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
```

Expected: PASS.

- [ ] **Step 3: Inventory PR #121 against current main**

```powershell
git diff --name-status origin/main efb8b54cc4b46cf3ca3a68f4f6680b387b2f723c -- `
  src/evidence_review/review_packet tests/unit/review_packet tests/integration/review_packet
```

Required inventory:

```text
PORT
- safe reference type projection
- verified reference page materialization
- independent reference anchor model
- typed TEXT/TABLE/PDF_PAGE/IMAGE/DIAGRAM/DRAWING rendering

KEEP_CURRENT_MAIN
- related_reference_routing.py eligibility/ranking
- visual_findings.py semantic grouping
- subject HQ/tile asset serving
- not_comparable status
- selected-only / click Decision Drawer / ABSTAIN summary
- Track B immutable evidence support

DO_NOT_RESTORE_FROM_121
- direct-only finding routing predating #122 related references
- old renderer markup that removes #122 interactions
- eager raster embedding that defeats current lazy delivery
```

- [ ] **Step 4: Commit the inventory**

```powershell
git add docs/plans/2026-08-26-reference-viewer-v2-port-inventory.md
git commit -m "docs: inventory reference viewer v2 port"
```

---

### Task 2: Add Safe Reference Type Metadata to Citation Resolution

**Files:**
- Create: `src/evidence_review/review_packet/reference_projection.py`
- Modify: `src/evidence_review/review_packet/builder.py`
- Create/port: `tests/unit/review_packet/test_reference_projection.py`
- Modify/port: `tests/unit/review_packet/test_builder.py`

**Interfaces:**
- `ReferenceType = Literal["TEXT", "TABLE", "PDF_PAGE", "IMAGE", "DIAGRAM", "DRAWING"]`.
- `project_reference_record(*, evidence_type: str, element_type: str | None, element_raw_json: str | None, table_raw_json: str | None, visual_kind: str | None) -> dict[str, object]`.
- Resolved citations gain `document_page_count` and `reference={type, table, visual}`.
- `_citation_identity()` remains unchanged.

- [ ] **Step 1: Add type-classification RED tests**

```python
assert project_reference_record(
    evidence_type="clause", element_type="paragraph",
    element_raw_json=None, table_raw_json=None, visual_kind=None,
)["type"] == "TEXT"
assert project_reference_record(
    evidence_type="table", element_type="table", element_raw_json=None,
    table_raw_json='{"cells":[{"row":1,"column":0,"text":"3.0m 이상","selected":true}]}',
    visual_kind=None,
)["type"] == "TABLE"
assert project_reference_record(
    evidence_type="visual", element_type="image", element_raw_json=None,
    table_raw_json=None, visual_kind="composite_diagram",
)["type"] == "DIAGRAM"
```

Add literal cases for `PDF_PAGE`, `IMAGE`, and `DRAWING`.

- [ ] **Step 2: Add bounded-table RED tests**

Projection returns `table=None` when cells exceed 200, cell text exceeds 1,000 characters, row/column is negative, span is non-positive, or `selected` is not boolean. Raw parser JSON is never exposed.

- [ ] **Step 3: Run RED tests**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_reference_projection.py tests/unit/review_packet/test_builder.py
```

- [ ] **Step 4: Implement allowlisted type projection**

```python
ReferenceType = Literal["TEXT", "TABLE", "PDF_PAGE", "IMAGE", "DIAGRAM", "DRAWING"]
_MAX_TABLE_CELLS = 200
_MAX_CELL_TEXT = 1_000
```

Classification order: table → drawing → diagram → image → text → PDF page fallback.

- [ ] **Step 5: Enrich `_resolve_citation()` without changing authority identity**

Join page-bound element/table/visual metadata using the already-resolved retrieval record identity. Add:

```python
resolved["document_page_count"] = page_count
resolved["reference"] = project_reference_record(
    evidence_type=evidence_type,
    element_type=element_type,
    element_raw_json=element_raw_json,
    table_raw_json=table_raw_json,
    visual_kind=visual_kind,
)
```

Do not add either presentation field to `_citation_identity()`.

- [ ] **Step 6: Run GREEN tests and commit**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_reference_projection.py tests/unit/review_packet/test_builder.py
git add src/evidence_review/review_packet/reference_projection.py src/evidence_review/review_packet/builder.py tests/unit/review_packet/test_reference_projection.py tests/unit/review_packet/test_builder.py
git commit -m "feat: project safe reference viewer metadata"
```

---

### Task 3: Materialize Verified Reference Pages and PDF Anchors

**Files:**
- Create: `src/evidence_review/review_packet/reference_pages.py`
- Create/port: `tests/unit/review_packet/test_reference_page_projection.py`

**Interfaces:**
- `build_reference_projection(citations: Sequence[Mapping[str, object]], *, page_root: Path) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, dict[str, object]]]`.
- Returns reference documents, deduplicated reference pages, and `anchor_by_citation_id`.
- Anchor coordinate system is `PDF_BOTTOM_LEFT_POINTS`.

- [ ] **Step 1: Add verified-page RED tests**

```python
documents, pages, anchors = build_reference_projection(citations, page_root=page_root)
assert len(pages) == 2
assert anchors["CIT-TEXT"]["bbox"]["coordinate_system"] == "PDF_BOTTOM_LEFT_POINTS"
assert anchors["CIT-TEXT"]["page_asset_key"] == pages[0]["asset_key"]
assert documents[0]["page_asset_keys"] == [pages[0]["asset_key"]]
```

Add two citations sharing `(revision_id, page_number, source_hash)` and assert one page asset with two anchors.

- [ ] **Step 2: Add fail-closed geometry/hash RED tests**

Source hash mismatch follows existing verified-page failure behavior. Width/height/origin/rotation/box mismatch raises `PAGE_RENDER_GEOMETRY_MISMATCH`. Bbox outside page bounds raises `ValueError`.

- [ ] **Step 3: Run RED tests**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_reference_page_projection.py
```

- [ ] **Step 4: Implement materialization through existing page verifier**

Use `read_verified_page_image(page_root, revision_id, page_number, source_hash)`. Deduplicate by `(revision_id, page_number, source_hash)` and use:

```python
"asset_key": f"reference-page-{len(pages) + 1}"
```

Validate page geometry before constructing anchors.

- [ ] **Step 5: Verify each raster is represented once**

The helper may carry one internal `data_uri` per unique page for archival compatibility, but duplicate citations on one page must not duplicate raster content. Task 6 removes raster bytes from protected model serialization.

- [ ] **Step 6: Run GREEN tests and commit**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_reference_page_projection.py
git add src/evidence_review/review_packet/reference_pages.py tests/unit/review_packet/test_reference_page_projection.py
git commit -m "feat: materialize verified reference pages"
```

---

### Task 4: Bind Direct and Related Reference Anchors to Existing Findings

**Files:**
- Modify: `src/evidence_review/review_packet/case_visual_projection.py`
- Modify only if citation-shape exposure is required: `src/evidence_review/review_packet/related_reference_routing.py`
- Modify/port: `tests/unit/review_packet/test_case_visual_projection.py`
- Regression: `tests/unit/review_packet/test_issue_119_related_reference_routing.py`
- Regression: `tests/unit/review_packet/test_issue_119_related_reference_formal_shape.py`

**Interfaces:**
- `case_visual_review.reference_documents`.
- `case_visual_review.reference_pages`.
- Finding fields `direct_reference_anchors` and `related_reference_anchors`.
- Existing `direct_claim_ids`, `related_claim_ids`, `related_evidence_ids`, `status`, `finding_id`, `page_asset_key`, `focus_bbox` remain unchanged.
- Anchor copies add presentation-only `reference_role` equal to `direct` or `related`.

- [ ] **Step 1: Add direct-anchor RED test**

```python
finding = result["findings"][0]
assert finding["direct_reference_anchors"][0]["reference_role"] == "direct"
assert finding["direct_reference_anchors"][0]["page"] == 12
assert finding["related_reference_anchors"] == []
```

- [ ] **Step 2: Add related-anchor RED test using current #122 routing**

Use the existing `REF-001` relevant / `REF-002` unrelated fixture. Assert only `REF-001` becomes a `reference_role="related"` anchor. With no Track A citation, `direct_reference_anchors` stays empty and status stays `not_comparable`.

- [ ] **Step 3: Run RED tests**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_case_visual_projection.py tests/unit/review_packet/test_issue_119_related_reference_routing.py tests/unit/review_packet/test_issue_119_related_reference_formal_shape.py
```

- [ ] **Step 4: Build one global page projection and bind by existing authority lineage**

Direct citation records come from current direct claim citations. Related citation records come only from already-selected `case_visual_review.related_references`; do not rerun ranking and do not convert related references into direct claims. Deduplicate all citation pages before copying anchors into Findings.

- [ ] **Step 5: Keep Subject coordinates untouched**

Continue using #122 `page_asset_key` and `focus_bbox`/candidate geometry. Do not add a replacement Subject page identity or synchronize Subject offsets to reference PDF coordinates.

- [ ] **Step 6: Run GREEN tests and commit**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_case_visual_projection.py tests/unit/review_packet/test_issue_119_related_reference_routing.py tests/unit/review_packet/test_issue_119_related_reference_formal_shape.py
git add src/evidence_review/review_packet/case_visual_projection.py tests/unit/review_packet/test_case_visual_projection.py tests/unit/review_packet/test_issue_119_related_reference_routing.py tests/unit/review_packet/test_issue_119_related_reference_formal_shape.py
```

If `related_reference_routing.py` changed only to expose existing citation shape, add it explicitly, then commit:

```powershell
git commit -m "feat: bind reference anchors to visual findings"
```

---

### Task 5: Render All Six Reference Types While Preserving #122 Layout

**Files:**
- Modify: `src/evidence_review/review_packet/render_case_visual.py`
- Modify/port: `tests/unit/review_packet/test_case_visual_renderer.py`
- Regression: `tests/unit/review_packet/test_issue_119_visual_hardening.py`

**Interfaces:**
- New Reference page/type nodes use `data-reference-page` and `data-reference-type`.
- Existing Subject nodes continue using `data-case-page`.
- Existing Finding buttons continue using `data-case-finding`, `data-case-page-key`, and `data-case-focus-bbox`.
- Table cells use `data-table-cell="<row>:<column>"`; only explicit `selected=true` cells receive `is-target` styling.

- [ ] **Step 1: Add six-type renderer RED assertions**

```python
assert 'data-reference-type="TEXT"' in html
assert 'data-reference-type="TABLE"' in html
assert 'data-reference-type="PDF_PAGE"' in html
assert 'data-reference-type="IMAGE"' in html
assert 'data-reference-type="DIAGRAM"' in html
assert 'data-reference-type="DRAWING"' in html
assert 'data-reference-page="reference-page-1"' in html
```

- [ ] **Step 2: Add table rendering RED assertions**

```python
assert 'data-table-cell="1:0"' in html
assert 'reference-table-cell is-target' in html
```

For a table without an explicit selected cell, assert no `is-target` token is emitted for that table.

- [ ] **Step 3: Add #122 contract assertions**

```python
assert 'data-case-page=' in html
assert 'data-case-finding=' in html
assert 'data-case-page-key=' in html
assert 'data-case-focus-bbox=' in html
```

Keep `data-direct-reference` for direct material; related material stays separately labeled. Related-only Finding remains `not_comparable` and renders `비교 불가`.

- [ ] **Step 4: Run RED tests**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_case_visual_renderer.py tests/unit/review_packet/test_issue_119_visual_hardening.py
```

- [ ] **Step 5: Implement typed rendering additively**

`TEXT`: quote/detail with page context. `TABLE`: bounded table plus page context. `PDF_PAGE`, `IMAGE`, `DIAGRAM`, `DRAWING`: verified reference page stage plus SVG anchor overlay. Preserve current Subject stage, Findings pagination, divider, selected-only control, and Decision Drawer.

- [ ] **Step 6: Run GREEN tests and commit**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_case_visual_renderer.py tests/unit/review_packet/test_issue_119_visual_hardening.py
git add src/evidence_review/review_packet/render_case_visual.py tests/unit/review_packet/test_case_visual_renderer.py tests/unit/review_packet/test_issue_119_visual_hardening.py
git commit -m "feat: render typed visual references"
```

---

### Task 6: Deliver Reference Assets Through the Existing Protected Lazy Path

**Files:**
- Modify: `src/evidence_review/review_packet/case_visual_asset_server.py`
- Modify: `src/evidence_review/review_packet/render_case_visual_lazy.py`
- Modify only if existing route registration requires it: `src/evidence_review/review_packet/server_process.py`
- Modify: `src/evidence_review/review_packet/render_case_visual.py`
- Modify/port: `tests/unit/review_packet/test_case_visual_asset_server.py`
- Regression: `tests/unit/review_packet/test_issue_119_visual_performance.py`
- Regression: `tests/integration/review_packet/test_protected_image_delivery.py`

**Interfaces:**
- Reference assets use the existing run token/protected loopback server.
- `#review-model` keeps reference identity/geometry/hash but no `data_uri` raster bytes.
- One unique reference page produces one delivered asset.

- [ ] **Step 1: Add model-stripping RED test**

```python
reference_pages = review_model["case_visual_review"]["reference_pages"]
assert all("data_uri" not in page for page in reference_pages)
```

Also assert duplicate citations do not create duplicate image routes/payloads.

- [ ] **Step 2: Add protected reference asset RED test**

Use the current protected-server harness: valid run token returns HTTP 200, image content type, expected SHA-256; invalid/missing token fails exactly as current Subject asset delivery.

- [ ] **Step 3: Run RED tests**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_case_visual_asset_server.py tests/unit/review_packet/test_issue_119_visual_performance.py tests/integration/review_packet/test_protected_image_delivery.py
```

- [ ] **Step 4: Extend the current asset map**

Register Reference asset keys in the same process/token lifecycle as Subject pages/tiles. Do not create another daemon, port, or token format.

- [ ] **Step 5: Strip Reference raster bytes before model serialization**

Apply the existing Subject page/tile byte-removal boundary to `case_visual_review.reference_pages`.

- [ ] **Step 6: Run GREEN tests and commit**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_case_visual_asset_server.py tests/unit/review_packet/test_issue_119_visual_performance.py tests/integration/review_packet/test_protected_image_delivery.py
git add src/evidence_review/review_packet/case_visual_asset_server.py src/evidence_review/review_packet/render_case_visual_lazy.py src/evidence_review/review_packet/render_case_visual.py tests/unit/review_packet/test_case_visual_asset_server.py tests/unit/review_packet/test_issue_119_visual_performance.py tests/integration/review_packet/test_protected_image_delivery.py
```

Add `server_process.py` only if it actually changed, then commit:

```powershell
git commit -m "perf: lazily deliver reference page assets"
```

---

### Task 7: Add Independent Reference Focus Without Replacing Subject Hooks

**Files:**
- Modify: `src/evidence_review/review_packet/render_case_visual.py`
- Modify/port: `tests/unit/review_packet/test_case_visual_renderer.py`
- Modify/port: `tests/integration/review_packet/test_review_workspace_ui.py`
- Modify/port: `tests/integration/review_packet/test_review_visual_contract.py`

**Interfaces:**
- New Reference pages use `data-reference-page` and Reference-specific transform state.
- Existing Subject pages remain `<figure ... data-case-page="...">`.
- Existing Finding buttons remain `data-case-finding`, `data-case-page-key`, `data-case-focus-bbox`.
- Finding selection focuses direct Reference first; if absent, may focus related Reference while retaining related authority label.
- Reference and Subject transforms are independent.

- [ ] **Step 1: Add DOM contract RED assertions**

```python
assert 'data-reference-page="reference-page-1"' in html
assert 'data-case-page="' in html
assert 'data-case-finding="' in html
assert 'data-case-page-key="' in html
assert 'data-case-focus-bbox="' in html
```

- [ ] **Step 2: Add interaction-harness RED assertions using existing Finding metadata**

Click the button selected by `data-case-finding`. Read its `data-case-page-key` and `data-case-focus-bbox`. Assert Subject activation still selects `.case-visual-page[data-case-page="<page-key>"]` and focuses the same bbox. Separately assert Reference activation selects the element whose `data-reference-page` equals the selected anchor page key and focuses its PDF bbox.

- [ ] **Step 3: Assert transform independence**

After Finding focus, zoom/pan the Reference stage and assert current Subject transform values are unchanged. Then zoom/pan Subject through existing controls and assert Reference transform values are unchanged.

- [ ] **Step 4: Run RED tests**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_case_visual_renderer.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/review_packet/test_review_visual_contract.py
```

- [ ] **Step 5: Implement separate Reference state without rewriting Subject state**

Add a Reference-only state object and helper path, for example:

```javascript
const referenceState = { pageKey: null, scale: 1, x: 0, y: 0 };
```

Reuse the current #122 Subject state/handlers unchanged. Finding selection calls `focusReference(anchor)` in addition to the existing Subject focus path. Do not synchronize raw offsets.

- [ ] **Step 6: Preserve divider/responsive behavior**

Keep 26%–70% divider bounds, reset behavior, desktop three-region layout, and 1366×768 Findings drawer fallback.

- [ ] **Step 7: Run GREEN tests and commit**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_case_visual_renderer.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/review_packet/test_review_visual_contract.py
git add src/evidence_review/review_packet/render_case_visual.py tests/unit/review_packet/test_case_visual_renderer.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/review_packet/test_review_visual_contract.py
git commit -m "feat: focus reference and subject independently"
```

---

### Task 8: Prove Presentation Authority Invariance

**Files:**
- Create: `tests/unit/review_packet/test_reference_viewer_authority_invariance.py`
- Regression: `tests/unit/review_packet/test_issue_119_related_reference_formal_shape.py`
- Regression: `tests/unit/review_question/test_track_b_handoff_support.py`

**Interfaces:**
- View-model/HTML construction cannot mutate machine authority fields.
- Related `RELATED-*` presentation records never become Track A claims audited by Track B.

- [ ] **Step 1: Add machine-packet invariance test**

Deep-copy the packet, build view model and HTML, then for v2 assert:

```python
for field in (
    "claims",
    "issue_results",
    "confidence",
    "finalizer_status",
    "human_decision",
):
    assert packet_after[field] == packet_before[field]
```

For legacy packet status, use the existing version-aware helper rather than altering schema.

- [ ] **Step 2: Add Track B input invariant**

Assert each Track A claim appears exactly once in Track B handoff and no `RELATED-*` presentation record is added to the audited Track A claim list.

- [ ] **Step 3: Run and commit**

```powershell
py -3.13 -m pytest -q tests/unit/review_packet/test_reference_viewer_authority_invariance.py tests/unit/review_packet/test_issue_119_related_reference_formal_shape.py tests/unit/review_question/test_track_b_handoff_support.py
git add tests/unit/review_packet/test_reference_viewer_authority_invariance.py tests/unit/review_packet/test_issue_119_related_reference_formal_shape.py tests/unit/review_question/test_track_b_handoff_support.py
git commit -m "test: prove reference viewer authority invariance"
```

---

### Task 9: Run Reference Viewer, #122, and Repository-Wide Gates

**Files:**
- No planned production edits.

**Interfaces:**
- Produces exact-HEAD automated acceptance evidence.

- [ ] **Step 1: Run focused Reference Viewer suite**

```powershell
py -3.13 -m pytest -q `
  tests/unit/review_packet/test_reference_projection.py `
  tests/unit/review_packet/test_reference_page_projection.py `
  tests/unit/review_packet/test_builder.py `
  tests/unit/review_packet/test_case_visual_projection.py `
  tests/unit/review_packet/test_case_visual_renderer.py `
  tests/unit/review_packet/test_reference_viewer_authority_invariance.py `
  tests/unit/review_packet/test_case_visual_asset_server.py `
  tests/integration/review_packet/test_protected_image_delivery.py `
  tests/integration/review_packet/test_review_workspace_ui.py `
  tests/integration/review_packet/test_review_visual_contract.py
```

- [ ] **Step 2: Run PR #122 regression set**

```powershell
py -3.13 -m pytest -q `
  tests/unit/review_packet/test_issue_119_related_reference_formal_shape.py `
  tests/unit/review_packet/test_issue_119_related_reference_routing.py `
  tests/unit/review_packet/test_issue_119_visual_hardening.py `
  tests/unit/review_packet/test_issue_119_visual_performance.py `
  tests/unit/review_packet/test_pr122_acceptance_regressions.py `
  tests/unit/review_packet/test_related_reference_render_fallback.py `
  tests/unit/review_question/test_track_b_handoff_support.py
```

- [ ] **Step 3: Run repository-wide gate**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output .tmp-doc-validation
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
```

Expected: all PASS and documentation errors=0.

- [ ] **Step 4: Record exact HEAD and clean state**

```powershell
git rev-parse HEAD
git status --short
```

---

### Task 10: Run Browser, Type, Viewport, and Large-PDF Acceptance

**Files:**
- Runtime acceptance artifacts only; do not commit source PDFs, evidence DBs, page caches, or run ZIPs.

**Interfaces:**
- Type matrix: `TEXT`, `TABLE`, `PDF_PAGE`, `IMAGE`, `DIAGRAM`, `DRAWING`.
- Viewports: 1920×1080, 1440×900, 1366×768.
- Large-PDF/zoom/lazy baseline remains at least PR #122 quality.

- [ ] **Step 1: Prepare sanitized acceptance runs covering all six types**

Every type must be backed by validated citation/page-cache data. TABLE uses cell focus only when fixture/parser metadata explicitly marks a selected cell.

- [ ] **Step 2: Verify each type in the protected browser**

For each type verify:

```text
correct type/page context
correct direct or related label
Reference focus lands on expected anchor
Subject focus lands on expected region
Reference and Subject zoom/pan remain independent
no black overlay/box
no raw hash/bbox/internal ID on default surface
```

- [ ] **Step 3: Verify viewport behavior**

At 1920×1080 and 1440×900, three-region review remains usable. At 1366×768, current Findings drawer fallback remains usable and Reference controls remain accessible.

- [ ] **Step 4: Verify large-PDF high zoom and lazy delivery**

Use the same large-PDF acceptance shape as #122. Confirm Subject HQ rendering still passes, Reference assets are not all eagerly loaded, and no new full-document tile subsystem was introduced.

- [ ] **Step 5: Verify generated artifact authority invariance**

Track A claims, Track B audit, issue results, confidence, finalizer status, and `human_decision:null` match the machine packet before rendering.

- [ ] **Step 6: Post sanitized PR-B acceptance results**

Include exact HEAD, six-type matrix, viewport matrix, large-PDF result, lazy asset result, authority invariance, and explicit `NOT_RUN` for any browser action not executed.

---

### Task 11: Merge PR-B and Supersede PR #121

**Files:**
- PR metadata only.

**Interfaces:**
- PR #121 remains open until PR-B demonstrably replaces its unique valid behavior.

- [ ] **Step 1: Update PR-B body after acceptance**

State that PR-B selectively replaced #121 safe reference projection/page/focus capabilities while retaining #122 authority/routing/interaction contracts. Keep `Refs #121` until acceptance is complete.

- [ ] **Step 2: Mark PR-B ready only when automated and browser gates pass**

Focus, viewport, and large-PDF acceptance cannot be `NOT_RUN` at ready-for-review time.

- [ ] **Step 3: Merge with expected HEAD protection**

Verify PR HEAD has not moved since acceptance and merge using the repository's normal method.

- [ ] **Step 4: Close PR #121 as superseded**

Comment that its unique capabilities were replaced on current architecture and that its old renderer/routing was intentionally not merged because it predates #122.

- [ ] **Step 5: Verify final repository state**

```text
#116 CLOSED
#117 CLOSED — superseded by PR-A
#119 CLOSED
#121 CLOSED — superseded by PR-B
#122 MERGED
main = correctness convergence + PR #122 Visual Review + Reference Viewer v2
```
