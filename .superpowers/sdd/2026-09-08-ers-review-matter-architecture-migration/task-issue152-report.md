# Issue #152 implementation report

## Scope delivered

- Added one named Review HTML shell for both reference-only and `CASE_DRAWING` output: Status/Question, Evidence Workspace, Detail/Issue Results, Human Decision, and Audit.
- Kept status, summary, issue results, Human Decision, and audit rendering in the shared shell for drawing mode.
- Collapsed the drawing Reference pane and divider when no direct reference exists, leaving a concise accessible notice and a full-width Subject workspace.
- Added separate drawing view controls for 화면 맞춤, 폭 맞춤, and 원본 100%; drawing starts at fit-width.
- Raised drawing helper/filter/pagination typography and standardized icon controls at 40px with centered inline-flex SVG layout.

## Independent review follow-up

Follow-up commit: `fix(issue-152): correct unified review interactions`.

- Corrected 화면 맞춤/폭 맞춤/원본 100% transforms so each target scale also compensates for the SVG `preserveAspectRatio="meet"` centering offset. The first drawing page still starts in 폭 맞춤.
- Restored the drawing Human Decision presentation in the unified shell as an off-canvas, state-controlled region. It starts hidden, focuses its first control when opened, returns focus to its trigger on close or Escape, and remains visible in print.
- Scoped the 40px viewer controls and 32px filter controls below the global 44px minimum with `min-height: 0`; the full-render contract verifies the later, more-specific cascade.

## Independent re-review follow-up

Follow-up commit: `fix(issue-152): preserve drawing print and initialization`.

- Added a drawing-specific print override with matching selector specificity. It resets the off-canvas drawer to normal document flow: static positioning, placement, dimensions, overflow, transform, visibility, pointer interaction, and shadow.
- The full renderer now requests drawing-only initial `aria-hidden="true"` decision markup. The inline drawing script can still bind before the later Human Decision element parses; its opener then retrieves, reveals, focuses, and closes that form after it exists.
- Preserved reference-only decision markup through the renderer default. Packet hashing/provenance, protected routes, and append-only decision storage remain untouched.

## Changed files

- `src/evidence_review/review_packet/html_renderer.py`
- `src/evidence_review/review_packet/render_workspace.py`
- `src/evidence_review/review_packet/render_summary.py`
- `src/evidence_review/review_packet/render_case_visual.py`
- `src/evidence_review/review_packet/render_decision.py`
- `src/evidence_review/review_packet/assets/review.css`
- `tests/unit/review_packet/test_case_visual_renderer.py`
- `tests/unit/review_packet/test_issue_119_visual_hardening.py`
- `tests/integration/review_packet/test_review_workspace_ui.py`
- `tests/integration/review_packet/test_persisted_decision_ui.py`

## Verification

- RED: `py -3.13 -m pytest -q -p no:cacheprovider tests/unit/review_packet/test_case_visual_renderer.py -k issue_152` — 3 failures against the base implementation: missing named view controls, missing collapsed Reference path, and missing shared shell regions.
- GREEN: the same command — `4 passed`.
- Keyboard/reference-focus harness: `py -3.13 -m pytest -q -p no:cacheprovider tests/integration/review_packet/test_review_workspace_ui.py -k finding_click` — `1 passed`.
- Adjacent renderer checks without fixture setup: `py -3.13 -m pytest -q -p no:cacheprovider tests/unit/review_packet/test_case_visual_renderer.py tests/unit/review_packet/test_issue_119_visual_hardening.py -k 'not projection_separates_direct_and_related_references and not projection_groups_ocr_fragments_into_semantic_finding'` — `26 passed, 2 deselected`.
- `py -3.13 -m ruff check src tests` — passed.
- `py -3.13 -m mypy src` — passed.
- `py -3.13 -m mypy --platform win32 src` — passed.
- `py -3.13 -m compileall -q src scripts web_runtime tests` — passed.
- `git diff --check` — passed before commit.
- Follow-up RED: `PYTHONPATH="$PWD\src" py -3.13 -m pytest -q -p no:cacheprovider tests/integration/review_packet/test_review_workspace_ui.py -k issue_152` — failed on the pre-fix portrait fit-width transform and missing unified-drawer/CSS contract.
- Follow-up GREEN: the same command — `2 passed, 12 deselected`; behavior harnesses cover portrait fit-width, landscape native-size centering, initial drawer state, opener focus, Escape, and close-button focus return.
- `PYTHONPATH="$PWD\src" py -3.13 -m pytest -q -p no:cacheprovider tests/integration/review_packet/test_review_workspace_ui.py -k 'finding_click or issue_152'` — `3 passed, 11 deselected`.
- `PYTHONPATH="$PWD\src" py -3.13 -m pytest -q -p no:cacheprovider tests/unit/review_packet/test_case_visual_renderer.py tests/unit/review_packet/test_issue_119_visual_hardening.py -k 'not projection_separates_direct_and_related_references and not projection_groups_ocr_fragments_into_semantic_finding'` — `26 passed, 2 deselected`.
- `py -3.13 -m ruff check src tests`; `py -3.13 -m mypy src`; `py -3.13 -m compileall -q src scripts web_runtime tests`; and `git diff --check` — passed after the follow-up.
- Re-review RED: `PYTHONPATH="$PWD\src" py -3.13 -m pytest -q -p no:cacheprovider tests/integration/review_packet/test_review_workspace_ui.py -k issue_152` — `1 passed, 2 failed`: the print cascade lacked the required reset rule and the full-render decision markup had no initial `aria-hidden` state.
- Re-review GREEN: the same command — `3 passed, 12 deselected`; contracts cover the print cascade and the actual script-before-form parser order, then opener focus plus Escape, backdrop, and close-button focus restoration.
- `PYTHONPATH="$PWD\src" py -3.13 -m pytest -q -p no:cacheprovider tests/integration/review_packet/test_review_workspace_ui.py -k 'finding_click or issue_152'` — `4 passed, 11 deselected`.
- `PYTHONPATH="$PWD\src" py -3.13 -m pytest -q -p no:cacheprovider tests/integration/review_packet/test_persisted_decision_ui.py tests/unit/review_packet/test_case_visual_renderer.py tests/unit/review_packet/test_issue_119_visual_hardening.py -k 'not projection_separates_direct_and_related_references and not projection_groups_ocr_fragments_into_semantic_finding'` — `29 passed, 2 deselected`.

## NOT_RUN

- Fixture-dependent renderer/protected-viewer suites and the full pytest suite: pytest fails during `tmp_path` setup with `PermissionError: [WinError 5]` while reading its own temporary directory. This happened with both the default temp root and an explicitly redirected scratch root, before affected test bodies ran.
- The reference-only unified workspace suite was retried in this re-review and remained `NOT_RUN`: four tests were blocked before their bodies by `OSError: could not create numbered dir with prefix pytest-` under the Windows pytest temp root.
- Manual browser QA at supported desktop/mobile viewport matrix, keyboard traversal, print preview, and protected-server lifecycle matrix.
- Real-browser computed-style and print QA: `NOT_RUN`. The Browser plugin is unavailable and no local Playwright module is installed; no dependency or network call was added. The emitted full-render regression test verifies the scoped, later, higher-specificity `min-height: 0` override against the global 44px minimum, and the new print contract verifies the equally specific document-flow reset.
- Documentation integrity and the full test suite.
- GitHub Actions: `ACTIONS_NOT_RUN`.

## Risks

- The UI contracts are regression-tested and static validation is clean, but the blocked fixture-dependent tests and manual browser matrix remain required before merge acceptance.
- The Human Decision form is deliberately hidden off-canvas only in `CASE_DRAWING` mode and is explicitly reset for print; real-browser viewport/print QA remains outstanding.
- No packet/evidence authority, hash verification, protected routes, or append-only Human Decision request/storage code was changed.
