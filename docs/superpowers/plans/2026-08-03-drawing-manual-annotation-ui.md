# Drawing Manual Annotation Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a secure localhost browser workspace that projects verified drawing candidates and records reviewer manual annotations through the existing append-only drawing backend.

**Architecture:** A deterministic view-model feeds a self-contained SVG renderer. A strict browser-action decoder and loopback-only server route all writes through the existing create-only candidate and append-only confirmation repositories. The browser performs viewport-to-page coordinate conversion only; calibration, dimensions, area, rules, and confidence remain outside this subsystem.

**Tech Stack:** Python 3.11/3.13, standard-library HTTP server, existing `ansim_review.contracts.drawing` contracts, HTML/SVG/CSS/vanilla JavaScript, pytest.

## Global Constraints

- No OpenAI API or external model API calls.
- No new runtime dependency.
- Reuse the M0 drawing contracts and M1 backend; do not define duplicate status, geometry, coordinate-system, or confirmation contracts.
- Source, candidate, and confirmation writes remain immutable, create-only, or append-only.
- Browser-supplied paths, hashes, manual candidate IDs, and confirmation IDs are never authoritative.
- Calibration arithmetic, OCR, automatic semantic extraction, DWG/DXF parsing, final Review Packet v2 rendering, and issue #7 orchestration are out of scope.

## Execution Status

Implementation and test contracts are present in Draft PR #54 for Tasks 1–7.

- [x] Deterministic drawing review view model implemented.
- [x] Self-contained SVG renderer and package assets implemented.
- [x] Strict existing-candidate and manual-create action contracts implemented.
- [x] Append-only action service implemented with candidate manifest hash verification.
- [x] Loopback-only tokenized HTTP server implemented.
- [x] POINT, BBOX, LINESTRING, and POLYGON browser capture implemented.
- [x] Browser-to-confirmation-to-confirmed-input-to-engine-binding E2E test contract added.
- [x] Workflow, roadmap, package-data, and documentation-integrity configuration updated.
- [ ] Focused tests executed on the exact PR HEAD.
- [ ] Repository-wide pytest, Ruff, strict mypy, and compileall passed.
- [ ] Python 3.11 and 3.13 wheel installation and asset access passed.
- [ ] Windows and Ubuntu verification passed.
- [ ] Human browser QA at 100%, 200%, and fit-to-page zoom passed.
- [ ] Exact HEAD, clean worktree, test counts, browser, OS, and acceptance evidence recorded.

GitHub Actions runs that terminate before executing job steps are `ACTIONS_UNAVAILABLE`; they do not satisfy any verification checkbox.

---

### Task 1: Deterministic drawing review view model

**Files:**
- Create: `src/ansim_review/drawing_review/__init__.py`
- Create: `src/ansim_review/drawing_review/view_model.py`
- Test: `tests/unit/drawing_review/test_view_model.py`

**Interfaces:**
- Consumes: `CoordinateSystem`, `DrawingCandidate`, `Geometry`, and `geometry_document()` from `ansim_review.contracts.drawing`.
- Produces: `DrawingPage` and `build_drawing_review_view_model(page: DrawingPage, candidates: Sequence[DrawingCandidate]) -> dict[str, object]`.

Required behavior:

- validate immutable source SHA-256, positive page, coordinate system, and finite page bounds;
- reject candidate source, page, or coordinate-system mismatch;
- reject POINT, BBOX, LINESTRING, or POLYGON geometry outside page bounds;
- sort projection candidates by stable candidate ID;
- expose no mutable path or browser-owned authority field.

Focused verification:

```bash
pytest tests/unit/drawing_review/test_view_model.py -q
```

### Task 2: Self-contained SVG annotation renderer

**Files:**
- Create: `src/ansim_review/drawing_review/html_renderer.py`
- Create: `src/ansim_review/drawing_review/assets/annotation.css`
- Create: `src/ansim_review/drawing_review/assets/annotation.js`
- Test: `tests/integration/drawing_review/test_html_renderer.py`

**Interface:**

```python
render_annotation_html(
    view_model: Mapping[str, object],
    page_image: bytes,
    mime: str,
) -> str
```

Required behavior:

- embed one verified page image and all CSS/JavaScript without external resources;
- render POINT as `circle`, BBOX as `rect`, LINESTRING as `polyline`, and POLYGON as `polygon`;
- escape candidate text;
- keep candidate list and geometry selection synchronized;
- leave every reviewer action unselected by default;
- include drawing-review CSS and JavaScript in wheel package data.

Focused verification:

```bash
pytest tests/integration/drawing_review/test_html_renderer.py -q
```

### Task 3: Strict browser action contract

**Files:**
- Create: `src/ansim_review/drawing_review/actions.py`
- Test: `tests/unit/drawing_review/test_actions.py`

**Interfaces:**

```python
ExistingCandidateAction
ManualCreateAction
decode_annotation_action(value: object) -> AnnotationAction
```

Required behavior:

- accept exact fields only;
- enforce path-safe identifiers and explicit-offset timestamps;
- require confirmed value and unit together;
- reject confirmed replacement data for ACCEPTED and REJECTED;
- require a value or geometry for EDITED;
- require geometry for CREATED;
- reject browser-supplied source hash, output path, confirmation ID, artifact hash, and manual candidate ID.

Focused verification:

```bash
pytest tests/unit/drawing_review/test_actions.py -q
```

### Task 4: Append-only action service

**Files:**
- Create: `src/ansim_review/drawing_review/service.py`
- Test: `tests/integration/drawing_review/test_action_service.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class AnnotationActionResult:
    candidate_entry: CaseManifestEntry | None
    confirmation_entry: CaseManifestEntry


def record_annotation_action(
    case_dir: Path,
    page: DrawingPage,
    candidate_entries: Mapping[str, CaseManifestEntry],
    action: AnnotationAction,
) -> AnnotationActionResult: ...
```

Required behavior:

- verify indexed candidate ID, canonical relative path, and recorded SHA-256 before loading;
- validate source, page, coordinate system, and page bounds before writing;
- derive confirmation ID in backend code;
- route existing actions through `persist_confirmation()`;
- route manual creation through `create_manual_candidate()`, `persist_candidate()`, and `persist_confirmation()`;
- return both new manifest entries for manual creation;
- preserve existing bytes when a duplicate create-only path is attempted.

Focused verification:

```bash
pytest tests/integration/drawing_review/test_action_service.py -q
```

### Task 5: Secure localhost server

**Files:**
- Create: `src/ansim_review/drawing_review/local_server.py`
- Test: `tests/integration/drawing_review/test_local_server.py`

**Interface:**

```python
serve_annotation_workspace(...) -> AnnotationServer
```

Routes:

```text
GET  /annotation/<token>
POST /annotation/<token>/actions
```

Required behavior:

- bind only to `127.0.0.1`;
- require a 32–128 character URL-safe access token;
- verify exact Host and same-origin Origin;
- emit no CORS permission;
- apply CSP, no-store, no-referrer, and nosniff headers;
- accept only bounded `application/json` POST bodies;
- reject symlink or Windows reparse-point case roots;
- disclose stable error codes without filesystem paths;
- serialize writes behind one action lock and route them through Task 4.

Focused verification:

```bash
pytest tests/integration/drawing_review/test_local_server.py -q
```

### Task 6: Manual annotation browser interaction

**Files:**
- Modify: `src/ansim_review/drawing_review/assets/annotation.js`
- Modify: `src/ansim_review/drawing_review/assets/annotation.css`
- Test: `tests/integration/drawing_review/test_browser_contract.py`

Required behavior:

- use SVG `getScreenCTM()` and `createSVGPoint()` for viewport-to-page conversion;
- support POINT click, BBOX drag, LINESTRING point sequence, and closed POLYGON point sequence;
- invert display Y only for `PDF_BOTTOM_LEFT_POINTS`;
- generate only Task 3 action fields;
- avoid real-world scale, length, area, ratio, threshold, rule, or confidence calculations;
- avoid external resources, dynamic code evaluation, browser storage, and `innerHTML`;
- leave reviewer actions unselected until explicit input.

Focused verification:

```bash
pytest tests/integration/drawing_review/test_browser_contract.py -q
```

### Task 7: End-to-end acceptance and documentation

**Files:**
- Create: `tests/integration/drawing_review/test_manual_annotation_browser_flow.py`
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `docs/superpowers/plans/2026-08-01-evidence-review-system-master-roadmap.md`
- Modify: `documentation-integrity.json`

Automated E2E contract:

```text
immutable PNG intake
  -> extractor candidate
  -> deterministic HTML
  -> loopback GET/POST
  -> ACCEPTED confirmation
  -> manual CREATED candidate and confirmation
  -> ConfirmedInput construction
  -> immutable source/candidate/confirmation hash revalidation
  -> deterministic engine binding
```

The same test must prove an `UNCONFIRMED` candidate cannot become a confirmed engine input.

Repository verification:

```bash
pytest -q
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
python -m build --wheel
```

Human browser QA:

- candidate overlays align at 100%, 200%, and fit-to-page zoom;
- candidate list and SVG selection remain synchronized;
- POINT, BBOX, LINESTRING, and POLYGON can be created;
- ACCEPTED, REJECTED, EDITED, and CREATED actions save append-only artifacts;
- no action is selected by default;
- malformed or unauthorized requests do not create files;
- browser, OS, display scale, exact commit, and PASS/FAIL evidence are recorded.
