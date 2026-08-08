# Issue #5 Visual Fidelity Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the production drawing-confirmation and final-review routes faithfully follow the approved Issue #5 visual target while retaining verified evidence, deterministic engine boundaries, and append-only human records.

**Architecture:** Keep the annotation and final-review renderers independent because they consume different canonical view models, but align them through equivalent semantic landmarks and the same visual tokens. Extend only server-side projections and presentation-only JavaScript; do not add a new schema, browser calculation, browser storage, or source replacement path.

**Tech Stack:** Python 3.11+, server-rendered self-contained HTML, packaged CSS and vanilla JavaScript, pytest, Ruff, mypy, compileall, documentation-integrity validator, Codex in-app Browser.

## Global Constraints

- `/annotation/{token}` remains drawing candidate confirmation; `/runs/{run_id}/{token}/review` remains final packet review and human decision.
- Machine packet `human_decision` remains `null`; drawing actions and human decisions are separate append-only records.
- Source images, page assets, hashes, coordinates, candidate values, rule data, and statuses come only from validated server data.
- Browser JavaScript may handle selection, tabs, visual modes, zoom/scroll, geometry capture, form validation, and same-origin transport only.
- Browser JavaScript must not perform domain arithmetic, rounding, threshold comparison, rule evaluation, source resolution, or packet mutation.
- No external asset, remote URL, remote font, browser storage, browser-local source replacement, destructive reset, or sample drawing may be introduced.
- No candidate action or final decision is preselected.
- The full primary workflow must fit the 1863 x 1494 desktop comparison viewport without document-level horizontal overflow.
- Production changes follow red-green-refactor; each task observes the stated failing tests before implementation.

---

### Task 1: Freeze the annotation fidelity contract

**Files:**
- Modify: `tests/integration/drawing_review/test_html_renderer.py`
- Modify: `tests/integration/drawing_review/test_browser_contract.py`
- Create: `tests/integration/drawing_review/test_visual_contract.py`

**Interfaces:**
- Consumes: `render_annotation_html(view_model, page_image, mime) -> str`
- Consumes: packaged `annotation.css` and `annotation.js`
- Produces: executable contract for the approved shell, Korean copy, route-specific panes, and viewport rhythm

- [ ] **Step 1: Add a failing semantic-layout test**

Add a test using the existing `_model()` fixture:

```python
def test_annotation_workspace_matches_issue_5_semantic_layout() -> None:
    html = _renderer()(_model(), b"\x89PNG\r\n\x1a\nfixture", "image/png")

    assert 'class="app-shell"' in html
    assert 'class="topbar"' in html
    assert html.count('class="metric"') == 4
    assert 'class="main-grid"' in html
    assert 'class="candidate-panel' in html
    assert 'class="viewer-panel' in html
    assert 'class="detail-panel' in html
    assert "도면 입력 확인" in html
    assert "보류 사유" in html
    assert "연결된 승인 규칙" in html
    assert "검토자 확인 기록" in html
    assert "검토자 최종 판정" not in html
```

- [ ] **Step 2: Add a failing presentation-safety test**

Extend `test_browser_contract.py` so annotation JavaScript still exposes all existing payload and geometry functions, while the HTML contains no unsafe prototype controls:

```python
for forbidden in (
    'type="file"',
    "localStorage",
    "sessionStorage",
    "resetPrototype",
    "runEngine()",
):
    assert forbidden not in html
```

Retain the existing assertions rejecting `Math.round`, `.toFixed(`, `ruleEvaluation`, and browser-owned fields.

- [ ] **Step 3: Add a failing CSS visual-contract test**

Create `test_visual_contract.py` and read `annotation.css` through `importlib.resources.files`. Assert the target tokens and non-stretching action:

```python
assert ".app-shell" in css and "max-width: 1700px" in css
assert ".metrics" in css and "gap: 10px" in css
assert ".metric" in css and "border-radius: 14px" in css
assert "grid-template-columns: 260px minmax(450px, 1fr) 330px" in css
assert ".feature" in css and "min-height: 68px" not in css
assert ".primary-action" in css and "align-self: stretch" not in css
assert "@media (max-width: 1180px)" in css
assert "@media (max-width: 820px)" in css
```

- [ ] **Step 4: Run RED and confirm the expected failures**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/integration/drawing_review/test_html_renderer.py tests/integration/drawing_review/test_browser_contract.py tests/integration/drawing_review/test_visual_contract.py -q
```

Expected: failures for the missing `보류 사유`/`연결된 승인 규칙` semantics and the current edge-to-edge/flush-card/stretching CSS declarations. Existing security tests must continue to execute rather than error.

- [ ] **Step 5: Commit the failing contract**

```powershell
git add tests/integration/drawing_review/test_html_renderer.py tests/integration/drawing_review/test_browser_contract.py tests/integration/drawing_review/test_visual_contract.py
git commit -m "test: freeze issue 5 annotation fidelity"
```

---

### Task 2: Recompose and compact the annotation workspace

**Files:**
- Modify: `src/ansim_review/drawing_review/html_renderer.py`
- Modify: `src/ansim_review/drawing_review/assets/annotation.css`
- Modify: `src/ansim_review/drawing_review/assets/annotation.js`
- Test: `tests/integration/drawing_review/test_html_renderer.py`
- Test: `tests/integration/drawing_review/test_browser_contract.py`
- Test: `tests/integration/drawing_review/test_visual_contract.py`

**Interfaces:**
- Preserves: version-1 drawing review view model and `/actions` payload contracts
- Preserves: `existingActionPayload`, `manualCreatePayload`, POINT/BBOX/LINESTRING/POLYGON capture, and protected POST
- Produces: source-like annotation shell using only validated candidate data and explicit empty states

- [ ] **Step 1: Add renderer helpers without changing the view-model schema**

Refactor `html_renderer.py` into small projection helpers:

```python
def _render_annotation_metrics(
    *, candidate_count: int, confirmed_count: int, short_hash: str
) -> str:
    return "".join(
        (
            '<section class="metrics" aria-label="검토 현황">',
            f'<article class="metric"><span>원본 무결성</span><strong>확인됨</strong><small>{escape(short_hash)}</small></article>',
            f'<article class="metric"><span>검출 객체</span><strong>{candidate_count}</strong><small>현재 페이지 후보</small></article>',
            f'<article class="metric"><span>확인 기록</span><strong>{confirmed_count}</strong><small>추가 전용 기록</small></article>',
            '<article class="metric" data-tone="alert"><span>현재 상태</span><strong>확인 필요</strong><small>엔진 입력 전</small></article>',
            "</section>",
        )
    )


def _render_rule_readiness() -> str:
    return (
        '<div class="empty-state" data-rule-readiness>'
        '<strong>연결된 승인 규칙 없음</strong>'
        '<p>확인된 입력만 서버 측 규칙·계산 엔진에 전달됩니다.</p>'
        '</div>'
    )
```

Add `_render_candidate_summary(candidates)` by iterating the already validated candidate mappings and escaping candidate type, value, and status into `<div class="kv-row">` rows. Add `_render_confirmation_guidance()` as static authority copy and `_render_reviewer_action_panel()` as the existing `_review_controls()` wrapped in the compact lower-panel landmarks. These helpers must not add a second action payload or a second candidate model. `_render_candidate_summary` may count validated candidate statuses for display, but it must not calculate domain results. `_render_rule_readiness` renders `연결된 승인 규칙 없음` until a future canonical model supplies bindings; it must not copy prototype rule IDs.

- [ ] **Step 2: Match the approved semantic composition**

Render:

- compact header with Korean status, page/hash context, `확인 기록 열기`, and `HTML 인쇄`;
- four separated metric cards;
- compact candidate rows and one explanatory callout;
- verified image viewer with the existing three mode buttons and metadata hooks;
- `근거`, `규칙`, `입력 확인` panes with candidate summary, explicit rule empty state, confirmation guidance, and visible hold reason;
- compact append-only action panel titled `검토자 확인 기록`;
- short parser -> 사용자 확인 -> 규칙·계산 엔진 -> 최종 검토 process strip.

Keep the existing geometry elements and every `data-*` action hook unchanged.

- [ ] **Step 3: Replace the annotation layout tokens and rhythm**

Update `annotation.css` with the approved values:

```css
body { margin: 0; min-width: 320px; min-height: 100vh; background: var(--bg); }
.app-shell { width: min(1700px, calc(100% - 36px)); margin: 18px auto; border: 1px solid var(--line); border-radius: 18px; overflow: hidden; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; padding: 14px 18px; background: transparent; }
.metric { min-height: 87px; padding: 13px 14px; border: 1px solid var(--line); border-radius: 14px; background: var(--panel-raised); }
.main-grid { grid-template-columns: 260px minmax(450px, 1fr) 330px; gap: 12px; padding: 0 18px 14px; }
.feature { min-height: 0; padding: 10px 11px; border: 1px solid transparent; background: transparent; }
.primary-action { align-self: end; min-height: 42px; }
```

Set a bounded desktop drawing stage so the header, metrics, main grid, lower action panel, and process strip fit the 1863 x 1494 viewport. At the two responsive breakpoints, stack the right panel and then all three regions.

- [ ] **Step 4: Keep JavaScript presentation-only**

Extend existing handlers only where new semantic hooks require synchronization. Add a print handler using `window.print()` and update candidate-wide counts from existing DOM data. Do not add file loading, reset, local storage, rule execution, or domain calculations.

- [ ] **Step 5: Run GREEN and drawing regressions**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/integration/drawing_review tests/unit/drawing_review tests/integration/drawing -q
python -m compileall -q src/ansim_review/drawing_review tests/integration/drawing_review
```

Expected: all tests pass, and the renderer remains self-contained with one source image embed.

- [ ] **Step 6: Commit the annotation correction**

```powershell
git add src/ansim_review/drawing_review/html_renderer.py src/ansim_review/drawing_review/assets/annotation.css src/ansim_review/drawing_review/assets/annotation.js tests/integration/drawing_review
git commit -m "feat: align drawing confirmation with issue 5"
```

---

### Task 3: Freeze the final review fidelity and localization contract

**Files:**
- Modify: `tests/integration/review_packet/test_html_renderer.py`
- Modify: `tests/integration/review_packet/test_review_workspace_ui.py`
- Create: `tests/integration/review_packet/test_review_visual_contract.py`

**Interfaces:**
- Consumes: `render_review_html(view_model, page_image_root) -> str`
- Produces: executable contract for the final review shell, complete Issue #5 domains, Korean copy, and compact decision form

- [ ] **Step 1: Add a failing final-review semantic test**

Use `_model()` and `_write_page_assets()` from the existing renderer tests:

```python
html = render_review_html(_model(), tmp_path / "pages")
for copy in (
    "근거 검토 화면",
    "기계 평가는 최종 판정이 아닙니다",
    "검토 요약",
    "검토 항목",
    "근거 뷰어",
    "근거",
    "규칙·계산",
    "감사·예외",
    "검토자 최종 판정",
    "판정 확정",
    "판정 JSON 저장",
):
    assert copy in html
assert html.count('class="metric"') == 4
assert "Evidence Review Workspace" not in html
assert "Human decision" not in html
```

- [ ] **Step 2: Add a failing complete-domain test**

Build a model containing one exception, one conflict, one abstention reason, and audit data. Assert they appear under the correct item-scoped detail panel and are not hidden behind an absent domain:

```python
assert 'data-detail-tab="evidence"' in html
assert 'data-detail-tab="rules-calculations"' in html
assert 'data-detail-tab="audit-exceptions"' in html
assert "SOURCE_CONFLICT" in html
assert "TRACK_B_REJECTED" in html
```

Retain the existing provenance scoping tests for calculations and rules.

- [ ] **Step 3: Add a failing CSS visual-contract test**

Create `test_review_visual_contract.py` with the same centered shell, four metric cards, 260/flexible/330 grid, compact lower form, 1180/820 breakpoints, print rules, and no-horizontal-overflow assertions used for annotation.

- [ ] **Step 4: Run RED and confirm expected failures**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/review_packet/test_review_visual_contract.py -q
```

Expected: failures for Korean copy, dark shell/card landmarks, grouped detail domains, and compact decision controls. Existing evidence hashing and XSS tests must still run.

- [ ] **Step 5: Commit the failing final-review contract**

```powershell
git add tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/review_packet/test_review_visual_contract.py
git commit -m "test: freeze issue 5 final review fidelity"
```

---

### Task 4: Implement the final review visual system and decision panel

**Files:**
- Modify: `src/ansim_review/review_packet/html_renderer.py`
- Modify: `src/ansim_review/review_packet/assets/review.css`
- Modify: `src/ansim_review/review_packet/assets/review.js`
- Test: `tests/integration/review_packet/test_html_renderer.py`
- Test: `tests/integration/review_packet/test_review_workspace_ui.py`
- Test: `tests/integration/review_packet/test_review_visual_contract.py`

**Interfaces:**
- Preserves: `render_review_html`, `write_review_html`, verified page-asset registry, item/citation IDs, decision envelope, and same-origin POST
- Produces: Korean dark Issue #5 workspace with complete evidence/rule/calculation/audit/exception projection

- [ ] **Step 1: Recompose the status and four-card summary**

Change `_render_status_band` and `_render_summary` so the shell header contains run/status/question context and the fixed machine-warning copy. Render four primary cards for citations, approved rules, calculations, and readiness. Render missing-input, conflict, uncited, and confidence values as visible secondary badges/rows below the primary card values so no Issue #5 metric disappears.

- [ ] **Step 2: Localize and compact the item list and viewer**

Update `_render_review_items` and `_render_evidence_viewer` to use Korean headings and compact selected rows. Add presentation-only original/evidence/compare buttons around the existing verified page canvas; the buttons may change overlay opacity only and must not alter coordinates or page bytes.

- [ ] **Step 3: Group complete detail domains into three source-like tabs**

Update `_render_detail_tabs` to expose:

- `근거`: claim, exact quote, document/revision/page/element/source hash;
- `규칙·계산`: item-scoped approved rule rows and calculation rows;
- `감사·예외`: audit facts, exceptions, conflicts, abstention reasons, and confidence factors.

Continue filtering calculations and rules by each review item's declared IDs. Do not show another item's result in the selected panel.

- [ ] **Step 4: Rebuild the lower human-decision form without changing its envelope**

Render four radio cards using the existing allowed decision values, plus reviewer ID, reviewed-at input, notes, packet hash, submit, and download controls. Keep the exact field names `reviewer_id`, `reviewed_at`, `packet_sha256`, `decision`, and `notes`; update only presentation and Korean labels.

- [ ] **Step 5: Apply the shared dark tokens and responsive grid**

Replace `review.css` with the approved shell/card/grid rhythm. Keep wide item-scoped tables scrollable inside the right panel, restore full table flow in print, and prevent the lower submit button from stretching vertically. Preserve verified evidence image aspect and avoid raster re-encoding.

- [ ] **Step 6: Update projection-only controller hooks**

Update `review.js` for the renamed three detail tabs and viewer modes while preserving:

```javascript
selectReviewItem(itemId)
activateDetailTab(tabName)
focusEvidence(itemId, evidenceId)
setEvidenceZoom(scale)
submitDecision(event)
downloadDecisionEnvelope()
```

Keep `fetch("./decision")`, the exact decision envelope fields, and all existing no-calculation/no-storage restrictions.

- [ ] **Step 7: Run GREEN and review regressions**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/unit/review_packet tests/integration/review_packet tests/integration/review_run tests/integration/test_review_routes.py -q
python -m compileall -q src/ansim_review/review_packet web_runtime tests/integration/review_packet
```

Expected: all renderer, provenance, security, decision, performance, and route tests pass.

- [ ] **Step 8: Commit the final-review correction**

```powershell
git add src/ansim_review/review_packet/html_renderer.py src/ansim_review/review_packet/assets/review.css src/ansim_review/review_packet/assets/review.js tests/integration/review_packet
git commit -m "feat: align final review workspace with issue 5"
```

---

### Task 5: Add viewport and interaction regression evidence

**Files:**
- Modify: `tests/integration/drawing_review/test_visual_contract.py`
- Modify: `tests/integration/review_packet/test_review_visual_contract.py`
- Create: `build/issue-5-visual-qa/annotation-1863x1494.png`
- Create: `build/issue-5-visual-qa/review-1863x1494.png`
- Create: `build/issue-5-visual-qa/annotation-mobile.png`
- Create: `build/issue-5-visual-qa/review-mobile.png`

**Interfaces:**
- Consumes: live tokenized annotation and final-review routes
- Produces: rendered evidence for desktop fit, responsive reachability, interactions, and console state

- [ ] **Step 1: Add deterministic static viewport-budget assertions**

Assert the desktop CSS uses the centered 1700 px shell, four-card metrics, 260/flexible/330 main grid, bounded main stage, compact lower panel, and non-stretching primary action. Preserve the existing print and wide-table containment assertions.

- [ ] **Step 2: Start fresh annotation and final-review fixtures**

Use existing test helpers and CLI/runtime entry points to generate one verified annotation fixture and one finalized review fixture. Do not reuse a stale browser tab as acceptance evidence.

- [ ] **Step 3: Exercise the annotation route in the in-app Browser**

At 1863 x 1494:

- select at least two candidates;
- switch original, detection, and compare modes;
- switch all three right tabs;
- verify the action form remains unselected;
- check document dimensions, horizontal overflow, and console errors;
- capture `annotation-1863x1494.png`.

At a mobile width at or below 820 px, verify stacked regions and reachable controls, then capture `annotation-mobile.png`.

- [ ] **Step 4: Exercise the final-review route in the in-app Browser**

At 1863 x 1494:

- select at least two review items;
- focus cited evidence and exercise zoom/modes;
- switch all three grouped detail tabs;
- verify no decision is selected;
- check document dimensions, horizontal overflow, and console errors;
- capture `review-1863x1494.png`.

At a mobile width at or below 820 px, verify stacked regions and reachable controls, then capture `review-mobile.png`.

- [ ] **Step 5: Run focused browser-backed tests**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/integration/drawing_review/test_browser_contract.py tests/integration/drawing_review/test_manual_annotation_browser_flow.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/test_review_routes.py -q
```

- [ ] **Step 6: Commit viewport regressions if test files changed**

```powershell
git add tests/integration/drawing_review/test_visual_contract.py tests/integration/review_packet/test_review_visual_contract.py
git commit -m "test: protect issue 5 workspace viewports"
```

---

### Task 6: Repeat design QA and run repository gates

**Files:**
- Modify: `design-qa.md`
- Create: `build/issue-5-visual-qa/full-comparison.png`
- Create: `build/issue-5-visual-qa/viewer-comparison.png`
- Create: `build/issue-5-visual-qa/right-panel-comparison.png`
- Create: `build/issue-5-visual-qa/bottom-panel-comparison.png`
- Create: `build/documentation-integrity-issue-5-visual.json`

**Interfaces:**
- Consumes: user-supplied reference PNGs and fresh browser captures
- Produces: same-input comparison boards, final QA result, and repository verification evidence

- [ ] **Step 1: Build native-density comparison boards**

Place each reference and matching implementation capture together in the same image input. Compare the full screen, viewer, right tabs, and lower action panel. Keep real drawing-content differences classified as expected evidence differences.

- [ ] **Step 2: Fix every remaining P0/P1/P2 and repeat capture**

For every blocking finding, record the source evidence, implementation evidence, change, and post-fix evidence in `design-qa.md`. Do not pass QA while a blocking mismatch remains.

- [ ] **Step 3: Run documentation integrity with a fresh output path**

```powershell
$env:PYTHONPATH='src'
python -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output build/documentation-integrity-issue-5-visual.json
```

- [ ] **Step 4: Run the full repository gates**

```powershell
$env:PYTHONPATH='src'
python -m pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

- [ ] **Step 5: Record acceptance evidence**

Update `design-qa.md` with exact source/implementation paths, viewport, dimensions, interaction checks, console state, comparison history, and `final result: passed` only when no actionable P0/P1/P2 issue remains. Record documentation report status/counts/SHA-256, command exit codes, branch, exact HEAD, platform, and Python version in the completion report. Keep wheel, GitHub Actions, release-output, process-attestation, and human-review gates explicitly pending unless they were independently executed.

- [ ] **Step 6: Commit the completed QA report**

```powershell
git add design-qa.md
git commit -m "test: verify issue 5 visual fidelity"
```
