# Issue #152 implementation report

## Scope delivered

- Added one named Review HTML shell for both reference-only and `CASE_DRAWING` output: Status/Question, Evidence Workspace, Detail/Issue Results, Human Decision, and Audit.
- Kept status, summary, issue results, Human Decision, and audit rendering in the shared shell for drawing mode.
- Collapsed the drawing Reference pane and divider when no direct reference exists, leaving a concise accessible notice and a full-width Subject workspace.
- Added separate drawing view controls for 화면 맞춤, 폭 맞춤, and 원본 100%; drawing starts at fit-width.
- Raised drawing helper/filter/pagination typography and standardized icon controls at 40px with centered inline-flex SVG layout.

## Changed files

- `src/evidence_review/review_packet/html_renderer.py`
- `src/evidence_review/review_packet/render_workspace.py`
- `src/evidence_review/review_packet/render_summary.py`
- `src/evidence_review/review_packet/render_case_visual.py`
- `src/evidence_review/review_packet/assets/review.css`
- `tests/unit/review_packet/test_case_visual_renderer.py`
- `tests/unit/review_packet/test_issue_119_visual_hardening.py`

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

## NOT_RUN

- Fixture-dependent renderer/protected-viewer suites and the full pytest suite: pytest fails during `tmp_path` setup with `PermissionError: [WinError 5]` while reading its own temporary directory. This happened with both the default temp root and an explicitly redirected scratch root, before affected test bodies ran.
- Manual browser QA at supported desktop/mobile viewport matrix, keyboard traversal, print preview, and protected-server lifecycle matrix.
- Documentation integrity and the full test suite.
- GitHub Actions: `ACTIONS_NOT_RUN`.

## Risks

- The UI contracts are regression-tested and static validation is clean, but the blocked fixture-dependent tests and manual browser matrix remain required before merge acceptance.
- No packet/evidence authority, hash verification, protected routes, or append-only Human Decision request/storage code was changed.
