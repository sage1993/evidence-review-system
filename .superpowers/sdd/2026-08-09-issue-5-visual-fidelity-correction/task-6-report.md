# Task 6 Report: Final-decision panel compactness correction

## Basis

- Repository: `F:\evidence-review-system\.worktrees\issue-5-review-workspace-v3`
- Branch: `codex/issue-5-review-workspace-v3`
- HEAD before commit: `cc591a724f3698371c54083f2498daa2c5b56bf5`
- Scope: presentation corrections to the final review and annotation workspaces, selector-scoped visual contracts, and one review-packet renderer layout wrapper (`global-audit-layout`). The renderer change only recomposed existing audit content; no data projection, controller, decision-envelope, or authority/security behavior changed.

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

## Browser QA Fix Round 1

### Fresh before-state evidence

The controller supplied `build/issue-5-visual-qa-final/review-1863x1494.png` after
commit `4605583`. At `innerWidth=1863`, `innerHeight=1494`, and client width `1848`,
the route had `document.scrollHeight=1669`; the decision form ran from `1378` to
`1604`. The decision form was not fully visible, while horizontal overflow was false,
console logs were empty, and no decision was selected.

The image confirms that the first compact-form change was real but insufficient: the
packet-global audit block immediately above the decision panel still consumed the
remaining primary-workflow budget.

### Root cause and presentation-only correction

The audit area retained its original 14px outer padding, 9px card gap, 10px card
padding, and inherited margins on headings, empty states, fact grids, record cards,
and lists. Those four horizontally arranged cards therefore expanded vertically even
when their values were empty. The decision form also retained an empty live-status row.

The second-round CSS-only correction:

- turns the global audit into a denser four-card desktop strip with 8/12px outer
  padding, 6px grid gaps, 6/8px cards, and 2px internal rhythm;
- preserves every audit, exception/conflict, abstention, and confidence record in its
  existing card and normal document flow—nothing is hidden, removed, or height-clipped;
- tightens only the decision presentation budget (6/10px heading and form padding,
  4px form gap, 24px option floor, 30px inputs, and 48px notes field); and
- suppresses `.form-status` only while it is empty. It returns to normal flow when the
  controller writes a submission status.

The 1180px/820px layout rules and print rules were not changed.

### RED/GREEN evidence

Added `test_global_audit_and_decision_sections_use_the_second_round_compact_budget`.
It is selector-scoped and freezes the audit area padding, heading rhythm, four-card
grid, card display/gap/padding, visible-content behavior (no clipping), empty-state
margin, and the decision form's empty-status handling.

RED command:

```powershell
$env:PYTHONPATH='src'
& 'F:\evidence-review-system\.venv\Scripts\python.exe' -m pytest tests/integration/review_packet/test_review_visual_contract.py::test_global_audit_and_decision_sections_use_the_second_round_compact_budget -q -p no:cacheprovider --basetemp build/pytest-task6-round2-red
```

Result: `1 failed in 0.12s`, expected because the previous audit padding was `14px`.

GREEN command ran the new audit contract and the existing decision contract with
`--basetemp build/pytest-task6-round2-green`.
Result: `2 passed in 0.07s`.

### Duplicate-contract cleanup

Removed the duplicate selector-scoped `.metric` radius assertion from the broad review
visual test. The identical check remains in `_assert_review_viewport_budget`, the
consolidated viewport helper. Removed the analogous duplicate from the drawing broad
visual test; `_assert_annotation_viewport_budget` retains its sole authoritative
selector-scoped radius assertion. No metric-radius coverage was removed.

### Validation

```powershell
$env:PYTHONPATH='src'
& 'F:\evidence-review-system\.venv\Scripts\python.exe' -m pytest tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/review_packet/test_review_visual_contract.py tests/integration/test_review_routes.py tests/integration/drawing_review/test_visual_contract.py -q -p no:cacheprovider --basetemp build/pytest-task6-round2-focused-green
```

Result: `46 passed, 1 skipped in 10.17s`.

```powershell
& 'F:\evidence-review-system\.venv\Scripts\ruff.exe' check src tests
git diff --check
```

Result: Ruff `All checks passed!`; diff check passed with only existing Windows
LF/CRLF notices.

### Browser QA handoff

No browser QA or screenshot recapture was performed in this round, as directed. The
controller must regenerate and recapture at 1863x1494 before the P1 finding can be
closed. The supplied before-state image was not modified.

## Populated audit-data fit pass

### Basis and verified gap

- HEAD before this pass: `00827171668f3b78eec97615ea3ad52e4d91688c`
- The desktop audit grid already used the compact four-card composition, but
  `.global-card` had no maximum-height or overflow contract. Multiple audit records,
  conflicts, abstention reasons, or confidence factors therefore expanded the shared
  grid row and could move the decision and process sections below the 1863x1494
  acceptance viewport.
- Earlier Task 6 wording that claimed no renderer changed was inaccurate. The third
  fit round changed `html_renderer.py` by adding the semantic `global-audit-layout`
  wrapper. This populated-data pass does not change the renderer; it adds test-only
  fixture coverage for the existing projection and constrains presentation in CSS.

### RED/GREEN correction

The representative test fixture now contains three audit records, three conflicts,
three abstention reasons, and three confidence factors. Every value is synthetic and
exists only in integration tests. The renderer contract asserts that every populated
value remains in the packet-global section and that no decision is preselected.

The visual contract renders that populated fixture and requires:

- normal, visible overflow in the base card rule;
- a screen-only desktop card maximum of 96px with internal scrolling above 1180px;
- wrapping for long values rather than truncation; and
- explicit unbounded, visible overflow at and below 1180px and in print.

Mutation assertions reject later equal-specificity changes to the base, desktop,
1180px, or print card behavior. The production change is limited to `review.css`; all
audit, conflict, abstention, and confidence content remains rendered and reachable.

RED command:

```powershell
$env:PYTHONPATH='src'
& 'F:\evidence-review-system\.venv\Scripts\python.exe' -m pytest tests/integration/review_packet/test_html_renderer.py::test_packet_global_review_preserves_populated_audit_content tests/integration/review_packet/test_review_visual_contract.py::test_populated_global_audit_cards_use_bounded_desktop_internal_scrolling tests/integration/review_packet/test_review_visual_contract.py::test_populated_global_audit_card_budget_rejects_cascade_mutations -q -p no:cacheprovider --basetemp build/pytest-task6-populated-red
```

Result: `1 failed, 2 passed in 0.23s`. The expected failure showed that the base
`.global-card` rule had no concrete max-height/overflow policy.

GREEN used the same selectors with `--basetemp build/pytest-task6-populated-green`.
Result: `3 passed in 0.08s`.

### Validation

```powershell
$env:PYTHONPATH='src'
& 'F:\evidence-review-system\.venv\Scripts\python.exe' -m pytest tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/review_packet/test_review_visual_contract.py tests/integration/test_review_routes.py -q -p no:cacheprovider --basetemp build/pytest-task6-populated-focused-rerun
```

Result: `48 passed, 1 skipped in 10.18s`. The first combined attempt had `47 passed,
1 skipped` plus one Windows `WinError 10053` connection abort in the unchanged
foreign-origin route test. That exact test passed alone (`1 passed in 1.16s`), and the
complete focused suite then passed on the recorded rerun above.

```powershell
& 'F:\evidence-review-system\.venv\Scripts\ruff.exe' check tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_review_visual_contract.py
git diff --check -- . ':(exclude)design-qa.md'
```

Result: Ruff `All checks passed!`; the scoped diff check passed. The parent-owned
`design-qa.md` modification was preserved and excluded from this pass.

### Scope and preserved behavior

- Production: desktop-only audit-card height/scroll behavior in `review.css`.
- Tests: populated renderer fixture/content assertions and selector-scoped
  desktop/mobile/print cascade and mutation contracts.
- Documentation: this Task 6 report correction and pass record.
- Unchanged: renderer/controller code in this pass, fail-closed authority, decision
  envelope, null/default human decision behavior, offline boundary, responsive layout,
  and print full-flow content.

No browser QA or screenshots were created or modified in this pass. The parent retains
responsibility for final acceptance evidence.

## Final browser-fit pass

### Fresh measurement and minimal scope

After `e508af9`, the controller measured `decisionBottom=1473` and confirmed the
decision section was fully visible. `processBottom=1502` remained eight pixels below the
1494px acceptance viewport, with `scrollHeight=1521`; horizontal overflow, console
errors, and decision selection were all absent. The only remaining cause was desktop
bottom rhythm, not a content or viewer-size problem.

This final pass preserves the required 18px outer shell margin. It changes only desktop
`review-workspace` bottom padding from 6px to 0 and process-strip vertical padding from
4/5px to 3/2px, a combined 10px reduction. The 1180px-and-below process-strip padding is
explicitly restored to 4/5px; print behavior remains unchanged and hides the process
strip as before.

### RED/GREEN evidence

Adjusted the selector-scoped desktop primary-workflow contract to require the preserved
18px shell margin, zero desktop workspace bottom padding, 3/2px desktop process-strip
padding, and the restored 4/5px process-strip padding below 1180px.

RED command:

```powershell
$env:PYTHONPATH='src'
& 'F:\evidence-review-system\.venv\Scripts\python.exe' -m pytest tests/integration/review_packet/test_review_visual_contract.py::test_desktop_primary_workflow_uses_the_third_round_vertical_budget -q -p no:cacheprovider --basetemp build/pytest-task6-final-fit-red
```

Result: `1 failed in 0.13s`, expected because the previous desktop workspace bottom
padding was 6px.

GREEN command used the same selector-scoped test with
`--basetemp build/pytest-task6-final-fit-green`.
Result: `1 passed in 0.06s`.

### Validation

```powershell
$env:PYTHONPATH='src'
& 'F:\evidence-review-system\.venv\Scripts\python.exe' -m pytest tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/review_packet/test_review_visual_contract.py tests/integration/test_review_routes.py tests/integration/drawing_review/test_visual_contract.py -q -p no:cacheprovider --basetemp build/pytest-task6-final-fit-focused
```

Result: `47 passed, 1 skipped in 10.17s`.

```powershell
& 'F:\evidence-review-system\.venv\Scripts\ruff.exe' check src tests
git diff --check
```

Result: Ruff `All checks passed!`; diff check passed with only existing Windows
LF/CRLF notices.

### Browser QA handoff

No browser QA or screenshot recapture was performed in this pass, as directed. The
controller must regenerate and recapture at 1863x1494 to verify the full process strip
now lies within the viewport before the P1 finding is closed.

## Final annotation fit pass

### Fresh measurement and root cause

After `e6fb9bc`, the controller measured the annotation `#reviewer-action` bottom at
1451 (fully visible) and the status strip bottom at 1499, five pixels below the 1494px
viewport. `scrollHeight=1512`; horizontal overflow, console errors, and preselected
actions were absent. The mobile 820x1180 view remained stacked, reachable, and free of
horizontal overflow.

The only remaining height source was the desktop status strip's 34px minimum and 8px
vertical padding, which exceeded the 9px monospace status content's required height.

### RED/GREEN correction

Added a selector-scoped screen-only desktop contract for
`@media screen and (min-width: 1181px)`. It preserves the 18px shell margin and base
34px/8px status-strip rule for non-desktop layouts while requiring a 28px minimum and
4px vertical desktop padding. The mobile column layout remains asserted.

RED command:

```powershell
$env:PYTHONPATH='src'
& 'F:\evidence-review-system\.venv\Scripts\python.exe' -m pytest tests/integration/drawing_review/test_visual_contract.py::test_annotation_css_freezes_concrete_viewport_budgets_and_print_flow -q -p no:cacheprovider --basetemp build/pytest-task6-annotation-final-red
```

Result: `1 failed in 0.12s`, expected because the desktop-only status-strip rule was
absent.

GREEN command used the same test with
`--basetemp build/pytest-task6-annotation-final-green`.
Result: `1 passed in 0.07s`.

### Validation

```powershell
$env:PYTHONPATH='src'
& 'F:\evidence-review-system\.venv\Scripts\python.exe' -m pytest tests/integration/drawing_review/test_html_renderer.py tests/integration/drawing_review/test_visual_contract.py tests/integration/drawing_review/test_browser_contract.py tests/integration/drawing_review/test_manual_annotation_browser_flow.py tests/integration/drawing_review/test_local_server.py -q -p no:cacheprovider --basetemp build/pytest-task6-annotation-final-focused
```

Result: `25 passed, 1 skipped in 4.35s`.

```powershell
& 'F:\evidence-review-system\.venv\Scripts\ruff.exe' check src tests
git diff --check
```

Result: Ruff `All checks passed!`; diff check passed with only existing Windows
LF/CRLF notices.

### Browser QA handoff

No browser QA or screenshot recapture was performed in this pass, as directed. The
controller must recapture at 1863x1494 to verify the status strip is now within the
viewport before closing the final visual finding.

## Browser QA Fix Round 2

### Fresh before-state evidence

The controller supplied `build/issue-5-visual-qa-final2/review-1863x1494.png` after
commit `d4fcfd2`. At the exact acceptance viewport, `scrollHeight=1594`; the decision
section ran from `1326` to `1529`. The action controls were clipped by 35px and the
process strip remained below the viewport. Horizontal overflow remained false, the
console was empty, and no decision was selected.

This confirms that the second round reduced the document by 75px but did not satisfy
the complete-primary-workflow target of 1494px.

### Root cause and presentation-only correction

The viewer and three desktop columns were already within the approved layout. The
remaining vertical waste was structural: the packet-global heading/context occupied a
full row above the four audit cards, the desktop workspace kept 12px row gaps and
14/12px outer rhythm, and the process strip retained 9/11px vertical padding.

The third round adds the single `global-audit-layout` renderer landmark around the
existing heading and card grid. Above 1180px it presents a 210px heading/context column
beside the unchanged four-card audit grid. It does not remove, hide, truncate, or
reassign any audit, conflict, abstention, or confidence value. The desktop-only CSS
budget also uses 6px workspace gaps, 8/6px workspace padding, a 10/14px header,
42px notes field, compact action-button padding, and a 4/12/5px process strip.

At and below 1180px the audit layout intentionally returns to a readable stacked heading
and grid with the previous 12px workspace rhythm; at 820px it keeps an 8px stacked
rhythm. Print also forces the audit layout back to a block so it stays readable.

### RED/GREEN evidence

Added `test_desktop_primary_workflow_uses_the_third_round_vertical_budget`. It verifies
the new renderer landmark, the 260/flexible/330 desktop grid, desktop header/workspace
budget, side-by-side audit composition, action-button and process-strip rhythm, and the
1180px/820px responsive restoration.

RED command:

```powershell
$env:PYTHONPATH='src'
& 'F:\evidence-review-system\.venv\Scripts\python.exe' -m pytest tests/integration/review_packet/test_review_visual_contract.py::test_desktop_primary_workflow_uses_the_third_round_vertical_budget -q -p no:cacheprovider --basetemp build/pytest-task6-round3-red
```

Result: `1 failed in 0.13s`, expected because the existing HTML had no
`global-audit-layout` landmark.

GREEN command ran the new third-round contract and the existing decision contract with
`--basetemp build/pytest-task6-round3-green`.
Result: `2 passed in 0.08s`.

The unrelated wide-table renderer test and earlier audit test each contained an obsolete
desktop-spacing assertion. Their exact spacing coverage now belongs to the new
consolidated third-round contract, so the stale duplicates were removed without reducing
coverage of table containment, print flow, or audit visibility.

### Validation

```powershell
$env:PYTHONPATH='src'
& 'F:\evidence-review-system\.venv\Scripts\python.exe' -m pytest tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/review_packet/test_review_visual_contract.py tests/integration/test_review_routes.py tests/integration/drawing_review/test_visual_contract.py -q -p no:cacheprovider --basetemp build/pytest-task6-round3-focused-green
```

Result: `47 passed, 1 skipped in 10.18s`.

```powershell
& 'F:\evidence-review-system\.venv\Scripts\ruff.exe' check src tests
git diff --check
```

Result: Ruff `All checks passed!`; diff check passed with only existing Windows
LF/CRLF notices.

### Browser QA handoff

No browser QA or screenshot recapture was performed in this round, as directed. The
controller must regenerate and recapture at 1863x1494 before the P1 finding can be
closed. The supplied before-state image was not modified.
