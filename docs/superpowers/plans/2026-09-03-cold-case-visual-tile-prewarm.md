# Cold Case Visual Tile Prewarm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove first-time large CASE_DRAWING tile materialization from final `view-model-build` so a fresh 17-page review run stays within the 5,000 ms deterministic release budget.

**Architecture:** Keep tile creation as an immutable preprocessing step owned by visual-analysis handoff preparation. Split the current create-or-load tile API into an explicit read-only loader plus the existing materializing ensure API, then make final review projection use only the loader so finalization cannot hide expensive cache creation. Missing large-page tile caches during finalization fail closed instead of being rebuilt.

**Tech Stack:** Python 3.13, Pillow, pytest, existing ERS visual-analysis and review-packet contracts.

**Spec:** Acceptance evidence from `RUN-A9EEAECFF7E6358CEB79`: `deterministic_total_ms=5516`, `view-model-build=5033`, browser handoff `327 ms`, workflow `READY_FOR_REVIEW`.

## Global Constraints

- Preserve the existing `case-page-tiles-v1` on-disk format and SHA-bound manifest validation.
- Preserve `ensure_visual_page_tiles()` for callers/tests that intentionally materialize tiles.
- Final `build_case_visual_projection()` must not create missing tile caches.
- Small visual pages must continue to return no tiles without requiring cache state.
- Do not change visual-analysis identity inputs, Track A/B contracts, publish behavior, or workflow state semantics.
- Release acceptance remains `deterministic_total_ms <= 5000` and `protected-server-start + browser-dispatch <= 2000`.

---

### Task 1: Add regression contracts for explicit tile lifecycle

**Files:**
- Modify: `tests/unit/drawing_review/test_visual_page_tiles.py`
- Modify: `tests/unit/drawing_review/test_visual_handoff.py`
- Modify: `tests/unit/review_packet/test_case_visual_lazy_projection.py`

**Interfaces:**
- Consumes: `VisualPageAsset`, existing `ensure_visual_page_tiles()` and `prepare_visual_analysis_handoff()`.
- Produces: tests requiring `load_visual_page_tiles(workspace: Path, page: VisualPageAsset) -> tuple[VisualPageTile, ...]`, handoff-time prewarming, and read-only final projection.

- [ ] **Step 1: Write the failing loader test**

Add a large-page test that calls `load_visual_page_tiles()` before any cache exists, expects `FileNotFoundError`, and verifies `case-page-tiles-v1/...` was not created.

- [ ] **Step 2: Write the failing handoff prewarm test**

Create a minimal large supporting image just above the existing tile threshold (`4097x3906`), call `prepare_visual_analysis_handoff()`, and assert the corresponding tile manifest exists immediately after handoff preparation.

- [ ] **Step 3: Update the lazy projection contract**

Change the metadata-only projection test to patch `load_visual_page_tiles` rather than `ensure_visual_page_tiles`, proving projection uses a read-only cache loader.

- [ ] **Step 4: Verify RED**

Run:

```powershell
py -3.13 -m pytest -q `
  tests/unit/drawing_review/test_visual_page_tiles.py `
  tests/unit/drawing_review/test_visual_handoff.py `
  tests/unit/review_packet/test_case_visual_lazy_projection.py
```

Expected: FAIL because `load_visual_page_tiles` does not exist and handoff preparation does not prewarm tiles.

- [ ] **Step 5: Commit the regression tests**

```bash
git add tests/unit/drawing_review/test_visual_page_tiles.py tests/unit/drawing_review/test_visual_handoff.py tests/unit/review_packet/test_case_visual_lazy_projection.py
git commit -m "test: cover cold case visual tile lifecycle"
```

---

### Task 2: Prewarm tiles during visual handoff and make projection read-only

**Files:**
- Modify: `src/evidence_review/drawing_review/visual_pages.py`
- Modify: `src/evidence_review/drawing_review/visual_handoff.py`
- Modify: `src/evidence_review/review_packet/case_visual_projection.py`

**Interfaces:**
- Consumes: existing `_tile_required`, `_tile_directory`, `_load_visual_page_tiles`, `ensure_visual_page_tiles`, and `VisualPageAsset`.
- Produces: `load_visual_page_tiles(workspace: Path, page: VisualPageAsset) -> tuple[VisualPageTile, ...]` as a read-only verified loader.

- [ ] **Step 1: Add the read-only tile loader**

Implement `load_visual_page_tiles()` so small pages return `()`, large pages require an existing directory, invalid paths fail closed, and existing manifests/files are verified through `_load_visual_page_tiles()` without creating directories or tiles.

- [ ] **Step 2: Keep materialization explicit**

Retain `ensure_visual_page_tiles()` as the only API that can create tile files. Reuse `load_visual_page_tiles()` when an existing cache is present and after successful atomic materialization.

- [ ] **Step 3: Prewarm at visual handoff**

Immediately after `prepare_visual_page_assets()` returns verified page assets, call `ensure_visual_page_tiles()` for every page. Small pages remain no-op; large pages materialize before the external visual-analysis handoff is emitted.

- [ ] **Step 4: Remove finalization-side materialization**

Change `case_visual_projection._page_tile_documents()` to use `load_visual_page_tiles()`. If a large page's preprocessing cache is absent, finalization must fail rather than create it.

- [ ] **Step 5: Verify GREEN focused tests**

Run the Task 1 command. Expected: all selected tests PASS.

- [ ] **Step 6: Commit implementation**

```bash
git add src/evidence_review/drawing_review/visual_pages.py src/evidence_review/drawing_review/visual_handoff.py src/evidence_review/review_packet/case_visual_projection.py
git commit -m "perf: prewarm case visual tiles before finalization"
```

---

### Task 3: Regression and release verification

**Files:**
- No production changes expected.

**Interfaces:**
- Consumes: Task 2 implementation.
- Produces: release-ready verification evidence.

- [ ] **Step 1: Run focused tests**

```powershell
py -3.13 -m pytest -q `
  tests/unit/drawing_review/test_visual_page_tiles.py `
  tests/unit/drawing_review/test_visual_handoff.py `
  tests/unit/review_packet/test_case_visual_lazy_projection.py
```

- [ ] **Step 2: Run full regression/static checks**

```powershell
py -3.13 -m pytest -q
ruff check .
mypy src
git diff --check
```

- [ ] **Step 3: Run one fresh 17-page acceptance workspace**

Use the same source PDF SHA-256 `4105698c88ec34b3e590e7d93fc7e51e9c942c98ec966b483549b02ad369abc4` through the standard visual-analysis → Track A → Track B → `submit-track-b --open` workflow. Do not copy `case-page-tiles-v1` into the fresh workspace.

- [ ] **Step 4: Verify release metrics**

Require:

```text
workflow next_state                 READY_FOR_REVIEW
TRACK_B_RETRY_MISMATCH              absent
deterministic_total_ms              <= 5000
protected-server-start + dispatch   <= 2000
review.html                         present
final-review-packet.json            present
display_status                      OPENED
```

- [ ] **Step 5: Final review checkpoint**

If the fresh acceptance run passes, close the cold-cache performance blocker. If it fails, preserve the run and inspect stage timings before making any further production change.
