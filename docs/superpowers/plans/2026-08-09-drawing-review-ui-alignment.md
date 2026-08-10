# Drawing Review UI Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the drawing annotation workspace faithfully match the approved issue-comment prototype without weakening evidence provenance or append-only confirmation behavior.

**Architecture:** Keep `DrawingPage`, `build_drawing_review_view_model`, the protected local server, and the action service unchanged. Recompose the existing server-rendered HTML and restyle its packaged CSS, then extend only presentation behavior in the packaged JavaScript while preserving the current action payload functions.

**Tech Stack:** Python 3.13, server-rendered HTML, packaged CSS/vanilla JavaScript, pytest, Codex in-app Browser.

## Global Constraints

- The browser is a projection and must not calculate domain values, evaluate rules, or confirm candidates automatically.
- Machine packets retain `human_decision: null`; reviewer actions remain separate append-only records.
- Source image, hash, page, coordinate system, and geometry come only from verified runtime data.
- No external assets, network calls, browser storage, or inline event handlers.
- Existing POINT, BBOX, LINESTRING, and POLYGON editing and `/actions` submission must remain compatible.

---

### Task 1: Freeze the approved visual structure

**Files:**
- Modify: `tests/integration/drawing_review/test_html_renderer.py`
- Modify: `tests/integration/drawing_review/test_browser_contract.py`

**Interfaces:**
- Consumes: `render_annotation_html(view_model, page_image, mime) -> str`
- Produces: failing assertions for the reference landmarks, tabs, metrics, display modes, and existing action hooks

- [ ] Add a renderer test asserting the top status, four metrics, three-column landmarks, three display modes, three detail tabs, reviewer action area, and status strip.
- [ ] Add a browser-contract test asserting the new tab/mode selectors while retaining all existing payload and forbidden-JavaScript assertions.
- [ ] Run the two new tests and verify they fail because the approved structure is absent.

### Task 2: Recompose the HTML projection

**Files:**
- Modify: `src/ansim_review/drawing_review/html_renderer.py`

**Interfaces:**
- Consumes: the existing version-1 drawing review view model
- Produces: the approved reference structure with escaped candidate and provenance data

- [ ] Add small rendering helpers for metrics, candidate cards, viewer metadata, tabs, and the reviewer-action section.
- [ ] Keep the existing geometry SVG and action form data attributes unchanged.
- [ ] Render the verified source image once and retain coordinate projection metadata only on the SVG.
- [ ] Run `pytest -q tests/integration/drawing_review/test_html_renderer.py` and make it pass.

### Task 3: Apply the reference design and presentation interactions

**Files:**
- Modify: `src/ansim_review/drawing_review/assets/annotation.css`
- Modify: `src/ansim_review/drawing_review/assets/annotation.js`

**Interfaces:**
- Consumes: the new semantic landmarks and all existing action data attributes
- Produces: dark responsive layout, candidate synchronization, layer modes, detail tabs, and unchanged action submission

- [ ] Replace the visual tokens and layout with the reference dark theme and responsive grid.
- [ ] Add display-mode and detail-tab presentation handlers without adding browser-side domain calculations.
- [ ] Synchronize selected candidate text, geometry, and status using `textContent` only.
- [ ] Keep `existingActionPayload`, `manualCreatePayload`, coordinate conversion, and protected `/actions` POST behavior intact.
- [ ] Run all `tests/integration/drawing_review` tests and make them pass.

### Task 4: Verify and hand off the rendered workspace

**Files:**
- Modify only if a verified P0/P1/P2 mismatch requires a source correction.

**Interfaces:**
- Consumes: the drawing annotation launcher and a verified drawing fixture
- Produces: a live local annotation URL and browser QA evidence

- [ ] Run Ruff, mypy, compileall, documentation validation, and the full pytest suite.
- [ ] Launch the local drawing annotation workspace with a verified source and candidate fixture.
- [ ] Inspect desktop and mobile layouts in the in-app Browser.
- [ ] Exercise candidate selection, mode switching, tab switching, and one append-only action submission.
- [ ] Compare the rendered result against the reference HTML and fix all P0/P1/P2 differences.
- [ ] Leave the verified local workspace open and report remaining release gates separately.

