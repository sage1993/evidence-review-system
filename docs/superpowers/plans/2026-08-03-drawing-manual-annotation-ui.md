# Drawing Manual Annotation Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a secure localhost browser workspace that projects verified drawing candidates and records reviewer manual annotations through the existing append-only drawing backend.

**Architecture:** Add a pure deterministic view-model layer first, then an SVG renderer, then a strict browser action decoder and localhost server. All persistence is delegated to existing candidate and confirmation functions; the browser never computes calibration, dimensions, area, rule results, or confidence.

**Tech Stack:** Python 3.11/3.13, standard-library HTTP server, existing `ansim_review.contracts.drawing` contracts, HTML/SVG/CSS/vanilla JavaScript, pytest.

## Global Constraints

- No OpenAI API or external model API calls.
- No new runtime dependency.
- Reuse the M0 drawing contracts and M1 backend; do not create duplicate status or geometry enums.
- All source, candidate, and confirmation writes remain create-only or append-only.
- Browser-supplied paths, hashes, candidate IDs for manual creation, and confirmation IDs are not authoritative.
- Calibration arithmetic and automatic extraction are out of scope.

---

### Task 1: Deterministic drawing review view model

**Files:**
- Create: `src/ansim_review/drawing_review/__init__.py`
- Create: `src/ansim_review/drawing_review/view_model.py`
- Test: `tests/unit/drawing_review/test_view_model.py`

**Interfaces:**
- Consumes: `DrawingCandidate`, `Geometry`, `geometry_document()` from `ansim_review.contracts.drawing`.
- Produces: `DrawingPage`, `build_drawing_review_view_model(page: DrawingPage, candidates: Sequence[DrawingCandidate]) -> dict[str, object]`.

- [ ] **Step 1: Write the failing deterministic-order test**

```python
def test_build_view_model_sorts_candidates_by_stable_id() -> None:
    model = build_drawing_review_view_model(page, (candidate_b, candidate_a))
    assert [item["candidate_id"] for item in model["candidates"]] == [
        "CAND-A",
        "CAND-B",
    ]
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
pytest tests/unit/drawing_review/test_view_model.py -q
```

Expected: FAIL because `ansim_review.drawing_review.view_model` does not exist.

- [ ] **Step 3: Implement the minimal view model**

```python
@dataclass(frozen=True, slots=True)
class DrawingPage:
    source_sha256: str
    page: int
    coordinate_system: CoordinateSystem
    width: float
    height: float


def build_drawing_review_view_model(
    page: DrawingPage,
    candidates: Sequence[DrawingCandidate],
) -> dict[str, object]:
    validated = [_candidate_document(page, item) for item in candidates]
    validated.sort(key=lambda item: cast(str, item["candidate_id"]))
    return {
        "format": "evidence-review/drawing-review-view",
        "version": 1,
        "source_sha256": page.source_sha256,
        "page": page.page,
        "coordinate_system": page.coordinate_system,
        "page_width": page.width,
        "page_height": page.height,
        "candidates": validated,
    }
```

- [ ] **Step 4: Add source, page, coordinate-system, and page-bound rejection tests**

- [ ] **Step 5: Run focused tests and full unit drawing tests**

```bash
pytest tests/unit/drawing_review/test_view_model.py -q
pytest tests/unit/parsing/test_drawing_candidates.py tests/unit/parsing/test_drawing_confirmation.py -q
```

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/drawing_review tests/unit/drawing_review

git commit -m "feat: build deterministic drawing review model"
```

### Task 2: Self-contained SVG annotation renderer

**Files:**
- Create: `src/ansim_review/drawing_review/html_renderer.py`
- Create: `src/ansim_review/drawing_review/assets/annotation.css`
- Create: `src/ansim_review/drawing_review/assets/annotation.js`
- Test: `tests/integration/drawing_review/test_html_renderer.py`

**Interfaces:**
- Consumes: Task 1 view-model dictionary and verified page-image bytes.
- Produces: `render_annotation_html(model: Mapping[str, object], page_image: bytes, mime: str) -> str`.

- [ ] **Step 1: Write a failing test proving all four geometry types produce SVG elements**
- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Render POINT as `circle`, BBOX as `rect`, LINESTRING as `polyline`, and POLYGON as `polygon`**
- [ ] **Step 4: Add external-resource and escaping tests**
- [ ] **Step 5: Add candidate/list synchronization attributes and no-default-action test**
- [ ] **Step 6: Run renderer tests and commit**

### Task 3: Strict browser action contract

**Files:**
- Create: `src/ansim_review/drawing_review/actions.py`
- Test: `tests/unit/drawing_review/test_actions.py`

**Interfaces:**
- Produces: `ExistingCandidateAction`, `ManualCreateAction`, and `decode_annotation_action(value: object)`.
- Manual creation accepts an annotation ID and geometry but derives the candidate ID in backend code.

- [ ] **Step 1: Write failing action decoder tests**
- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement exact-field decoding and identifier length limits**
- [ ] **Step 4: Reject browser-supplied source hash, output path, candidate ID for manual creation, and confirmation ID**
- [ ] **Step 5: Run focused tests and commit**

### Task 4: Append-only action service

**Files:**
- Create: `src/ansim_review/drawing_review/service.py`
- Test: `tests/integration/drawing_review/test_action_service.py`

**Interfaces:**
- Consumes: Task 3 actions and existing drawing candidate/confirmation repositories.
- Produces: `record_annotation_action(case_dir: Path, page: DrawingPage, action: AnnotationAction) -> CaseManifestEntry`.

- [ ] **Step 1: Write failing acceptance, rejection, edit, and manual-create tests**
- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Route existing actions through `validate_confirmation_for_candidate()` and `persist_confirmation()`**
- [ ] **Step 4: Route manual creation through `create_manual_candidate()`, `persist_candidate()`, and `persist_confirmation()`**
- [ ] **Step 5: Add stale-source, tamper, duplicate-write, and coordinate mismatch tests**
- [ ] **Step 6: Run integration tests and commit**

### Task 5: Secure localhost server

**Files:**
- Create: `src/ansim_review/drawing_review/local_server.py`
- Test: `tests/integration/drawing_review/test_local_server.py`

**Interfaces:**
- Produces: `serve_annotation_workspace(...) -> AnnotationServer` and routes `GET /annotation/<token>` and `POST /annotation/<token>/actions`.

- [ ] **Step 1: Write failing localhost-only and token tests**
- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement exact Host/Origin checks, no CORS, and body limits**
- [ ] **Step 4: Connect POST actions to Task 4 service**
- [ ] **Step 5: Add traversal, symlink/junction, malformed JSON, and filesystem-disclosure tests**
- [ ] **Step 6: Run integration tests and commit**

### Task 6: Manual annotation browser interaction

**Files:**
- Modify: `src/ansim_review/drawing_review/assets/annotation.js`
- Modify: `src/ansim_review/drawing_review/assets/annotation.css`
- Test: `tests/integration/drawing_review/test_browser_contract.py`

**Interfaces:**
- Uses SVG pointer coordinates only for annotation geometry capture and viewport transforms.
- Does not calculate real-world length, scale, area, rule results, or confidence.

- [ ] **Step 1: Write static contract tests for supported tools and forbidden arithmetic**
- [ ] **Step 2: Implement POINT, BBOX, LINESTRING, and POLYGON capture**
- [ ] **Step 3: Implement accept, reject, edit, and create request generation**
- [ ] **Step 4: Keep all actions initially unselected**
- [ ] **Step 5: Run tests and commit**

### Task 7: End-to-end acceptance and documentation

**Files:**
- Create: `tests/integration/drawing_review/test_manual_annotation_browser_flow.py`
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `docs/superpowers/plans/2026-08-01-evidence-review-system-master-roadmap.md`

- [ ] **Step 1: Add one raster source fixture with extractor and manual candidates**
- [ ] **Step 2: Verify existing candidate acceptance reaches an append-only confirmation**
- [ ] **Step 3: Verify manual annotation creates candidate and confirmation artifacts**
- [ ] **Step 4: Verify unconfirmed candidates remain unavailable to engine binding**
- [ ] **Step 5: Run repository verification**

```bash
pytest -q
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

- [ ] **Step 6: Perform human browser QA at 100%, 200%, and fit-to-page zoom**
- [ ] **Step 7: Record exact HEAD, clean worktree, test counts, browser, OS, and PASS/FAIL evidence**
- [ ] **Step 8: Commit documentation and acceptance evidence**