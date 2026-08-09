# Task 6 Report: Final-decision panel compactness correction

## Basis

- Repository: `F:\evidence-review-system\.worktrees\issue-5-review-workspace-v3`
- Branch: `codex/issue-5-review-workspace-v3`
- HEAD before commit: `cc591a724f3698371c54083f2498daa2c5b56bf5`
- Scope: presentation-only correction to the final reviewer decision form and its selector-scoped visual contract. No renderer, controller, decision-envelope, or authority/security behavior changed.

## Before-state evidence and finding

Primary evidence is `build/issue-5-visual-qa/review-1863x1494.png`, captured in the in-app Browser at `innerWidth=1863`, `innerHeight=1494`, and client width `1848`. The final-decision panel begins at the bottom of that capture and is not fully visible. This is the acceptance-viewport confirmation of the P1 compactness blocker.

Supporting evidence is `build/issue-5-visual-qa/comparison-final-decision.png`, `build/issue-5-visual-qa/review-decision-visible.png`, and the user-supplied reference `C:\Users\KSH\AppData\Local\Temp\codex-clipboard-a54b13dc-93b0-49b8-b982-7b041dbfc9f0.png`. The reference uses a compact three-column desktop region with short decision controls, a bounded memo area, and a primary action that does not fill excess height.

Root cause: the implementation combined 12/14px section/form padding, a 10px form gap, three vertically stacked metadata controls, a 112px textarea, and a separate full-width action row. Those independent vertical budgets made the lower panel materially taller than the reference.

## RED/GREEN correction

Added `test_final_decision_panel_uses_compact_three_column_desktop_budget`, which reads the rendered inline CSS through selector-scoped helpers. It freezes the desktop form's three columns, 8/6px outer rhythm, 4px decision/metadata gaps, 28px option floor, 32px control floor, 64px textarea floor, inline three-field metadata layout, and an end-aligned non-stretching primary action.

RED command:

```powershell
$env:PYTHONPATH='src'
& 'F:\evidence-review-system\.venv\Scripts\python.exe' -m pytest tests/integration/review_packet/test_review_visual_contract.py::test_final_decision_panel_uses_compact_three_column_desktop_budget -q -p no:cacheprovider --basetemp build/pytest-task6-red
```

Result: `1 failed in 0.09s`, as expected. The initial failure showed the previous `.decision-heading` padding `12px 14px` instead of the required `8px 12px`.

The minimum CSS-only correction in `review.css` reduces heading/form padding and gaps; makes the required metadata controls a compact inner three-column grid; reduces choice and control padding while keeping a 28px/32px minimum control budget; reduces the notes field from 112px to 64px; and end-aligns the action row and primary action without changing button semantics.

GREEN command used the same test with `--basetemp build/pytest-task6-green`. Result: `1 passed in 0.06s`.

## Preserved behavior

- The four allowed decision radios remain required and have no preselection.
- `reviewer_id`, `reviewed_at`, `packet_sha256`, `notes`, submit, and download controls remain rendered with their existing names and envelope behavior.
- The 1180px and 820px responsive form/workspace rules and the print overrides remain in place.
- Existing focus styles, field semantics, `fetch("./decision")`, and no-storage/no-calculation constraints are unchanged.

## Validation

```powershell
$env:PYTHONPATH='src'
& 'F:\evidence-review-system\.venv\Scripts\python.exe' -m pytest tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/review_packet/test_review_visual_contract.py tests/integration/test_review_routes.py -q -p no:cacheprovider --basetemp build/pytest-task6-focused-green
```

Result: `43 passed, 1 skipped in 10.15s`.

```powershell
& 'F:\evidence-review-system\.venv\Scripts\ruff.exe' check src tests
git diff --check
```

Result: Ruff `All checks passed!`; `git diff --check` passed. Git emitted only existing Windows LF/CRLF notices.

## Browser QA handoff

No browser QA or screenshot recapture was performed for this correction, as directed. The controller must recapture the final-review route at the acceptance viewport and decide whether the visual P1 is cleared. The pre-fix images were not modified.
