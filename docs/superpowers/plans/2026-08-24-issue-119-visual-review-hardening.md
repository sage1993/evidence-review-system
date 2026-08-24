# Issue #119 Visual Review Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the approved Reference ↔ Subject ↔ Findings Visual Review workspace so it presents trustworthy direct/related reference relationships, semantic findings, reliable focus/navigation, safe SVG overlays, explicit reviewer controls, and scalable large-PDF rendering.

**Architecture:** Keep immutable visual observations and raw DrawingCandidate provenance unchanged, then add a deterministic semantic-finding projection between raw observations and the HTML renderer. Direct references are restricted to rule-bound claims; unbound cited claims remain related references. The browser renders one active raster page at a time, uses SVG only for annotation, and lazily decodes pre-generated large-page tiles.

**Tech Stack:** Python 3.13, dataclasses/stdlib, Pillow, existing pypdfium2 page cache, self-contained HTML/CSS/vanilla JS, pytest.

**Spec:** GitHub Issue #119 — Visual Review UI 초안 확정: 기준 근거 ↔ 사용자 파일 대조 Workspace

## Global Constraints

- Preserve source bytes, hashes, page provenance, and raw DrawingCandidate records.
- Do not turn visual analysis into legal/compliance authority; fail closed when direct comparability is absent.
- `비교 불가` is distinct from `확인 필요`.
- Original PDF/image renderer remains raster/PDF-backed; marker/bbox/icon annotation remains SVG.
- No default full-page vertical scrolling in Visual Review.
- Reviewer decision remains separate from the machine packet and opens only through explicit user action.
- Python 3.13 is the release verification baseline.

---

### Task 1: Lock regression contracts before implementation

**Files:**
- Modify: `tests/unit/review_packet/test_case_visual_projection.py`
- Modify: `tests/unit/review_packet/test_case_visual_renderer.py`
- Create: `tests/unit/review_packet/test_visual_findings.py`
- Create: `tests/unit/drawing_review/test_visual_page_tiles.py`

**Interfaces:**
- Consumes: existing `build_case_visual_projection`, `render_case_visual_review`, `render_additional_review`.
- Produces: failing tests for reference classification, semantic grouping, SVG fill safety, auto-focus, selected-only mode, explicit decision drawer, ABSTAIN summary, lazy page/tile rendering, and HQ-cache resolution.

- [ ] Add failing tests for `direct` versus `related` claim relations and `not_comparable` findings.
- [ ] Add failing tests that raw OCR-like candidates are grouped into semantic findings without repeating the QuestionPlan question.
- [ ] Add failing renderer tests that every helper SVG geometry has explicit non-opaque fill, empty reference states render correctly, and `비교 불가` remains a distinct status/filter.
- [ ] Add failing interaction-contract tests for Finding auto-focus, `선택 항목만`, click-only decision drawer, and lazy image/tile source activation.
- [ ] Add failing tile-cache tests for large raster pages and verified cache reuse.

### Task 2: Add deterministic semantic finding projection

**Files:**
- Create: `src/evidence_review/review_packet/visual_findings.py`
- Modify: `src/evidence_review/review_packet/case_visual_projection.py`
- Modify: `src/evidence_review/llm_layer/templates/visual-analysis.md`

**Interfaces:**
- Produces: `build_semantic_visual_findings(pages) -> list[dict[str, object]]`.
- Finding fields: `finding_id`, `title`, `category`, `status`, `page_asset_key`, `candidate_ids`, `issue_ids`, `subject_value`, `focus_bbox`, `direct_claim_ids`, `related_claim_ids`.

- [ ] Classify claim links as `direct` only when their claim is bound to deterministic rule status; otherwise `related`.
- [ ] Group candidates by page, issue lineage and semantic category (`space_program`, `area`, `dimension`, `level`, `building_identity`, fallback observation), unioning their geometry bounds while preserving candidate IDs.
- [ ] Resolve status conservatively: no direct claim => `not_comparable`; otherwise mismatch > needs_check > match.
- [ ] Update the visual-analysis instructions to request semantic reviewable observations instead of standalone OCR fragments while preserving neutral/non-conclusive behavior.

### Task 3: Fix reference/subject rendering and UX

**Files:**
- Modify: `src/evidence_review/review_packet/render_case_visual.py`
- Modify: `src/evidence_review/review_packet/render_summary.py`

**Interfaces:**
- Consumes: top-level `case_visual_review.findings` and candidate claim relation metadata.
- Produces: Reference Viewer with direct/related separation, Subject Viewer, Findings pagination/filtering, explicit decision drawer, and Finding focus.

- [ ] Make SVG helper geometry self-safe with explicit `fill="none"` and keep selected bbox highlighting in SVG; no unstyled SVG rect may cover source content.
- [ ] Render direct references in the primary reference pane and related references under a secondary disclosure; when no direct reference exists, show a clear empty state instead of a blank viewer.
- [ ] Render compact ABSTAIN/no-direct-reference summary inside the Visual Review workspace.
- [ ] Render semantic finding title/value only; do not repeat the full issue question in every card.
- [ ] Implement status filters including distinct `비교 불가`, semantic finding pagination, and actual `선택 항목만` overlay filtering.
- [ ] On Finding selection, show the corresponding page, focus the subject bbox to a useful viewport fraction, and scroll/focus the direct reference block independently.
- [ ] Replace hover-open reviewer panel behavior with an explicit `검토 판정` button, backdrop/close control, and Escape handling.

### Task 4: Harden large-PDF raster resolution and lazy tiles

**Files:**
- Modify: `src/evidence_review/drawing_review/visual_pages.py`
- Modify: `src/evidence_review/review_packet/case_visual_projection.py`
- Modify: `src/evidence_review/review_packet/render_case_visual.py`

**Interfaces:**
- Produces sidecar tile cache under `case-page-tiles-v1/<attachment>/page-NNNN/` for large pages.
- Projection resolves raster from both current high-resolution PDF cache and normalized image cache by exact expected image hash.

- [ ] Resolve case PDF page rasters from `case-page-images-hq-v1` before the normal image cache; verify hashes and reject ambiguity/mismatch.
- [ ] Keep the existing 4x PDF raster as the high-resolution source.
- [ ] Generate deterministic 2048px tiles only for large pages, with a hash-bound manifest and create/reuse validation.
- [ ] Embed page/tile bytes as lazy `data-*` sources rather than eager `src` for inactive pages.
- [ ] In JS, decode only the active page and load tiles intersecting the current viewport plus a bounded preload margin; schedule reloads with `requestAnimationFrame` during pan/zoom.

### Task 5: Verification and issue/PR handoff

**Files:**
- No production file changes unless a verification failure exposes a defect.

- [ ] Run focused Visual Review unit suites.
- [ ] Run full `pytest`, Ruff, mypy, compileall and documentation validation on Python 3.13 when the environment permits.
- [ ] Verify generated HTML at supported viewport sizes and inspect SVG overlays for opaque helper shapes.
- [ ] Record unexecuted gates as `NOT_RUN` and Actions state exactly as observed.
- [ ] Open a PR referencing #119; keep the issue open until its acceptance gates are actually executed.
