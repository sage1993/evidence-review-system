# Issue 5 Drawing Review UI Design QA

## Result

`passed` for the implemented visual and interaction scope. The annotation route remains an input-confirmation workspace and the final-review route remains the separate human-decision workspace required by repository authority. No decision or confirmation was written during QA.

## Comparison target and implementation evidence

- Source visual truth: the eight user-supplied PNGs under `C:/Users/KSH/AppData/Local/Temp/codex-clipboard-*.png`, including the full workspace, three viewer modes, three right-panel states, and compact final-decision panel.
- Source prototype: `F:/evidence-review-system/tmp/drawing_evidence_review_ui.html`.
- Annotation implementation: `/annotation/{token}`.
- Final-review implementation: `/runs/{run-id}/{token}/review`.
- Acceptance viewport: 1863 x 1494 CSS pixels at device scale factor 1. Browser content width was 1848 pixels because the vertical scrollbar is excluded.
- Real evidence asset: `tmp/pdfs/pr58-sample/sample-page17-600dpi-17.png`, 9925 x 7017 pixels, SHA-256 `015e0f41d147f2c7e7f276e2b8379b905d9de93a678da84579200d1c11c0e96f`.
- Final captures:
  - `build/issue-5-visual-qa-final5/annotation-1863x1494.png`
  - `build/issue-5-visual-qa-final5/review-1863x1494.png`
  - `build/issue-5-visual-qa-final5/annotation-mobile.png`
  - `build/issue-5-visual-qa-final5/annotation-mobile-action.png`
  - `build/issue-5-visual-qa-final5/review-mobile.png`
  - `build/issue-5-visual-qa-final5/review-mobile-decision.png`
- Same-input comparison boards:
  - `build/issue-5-visual-qa-final5/comparison-annotation-full.png`
  - `build/issue-5-visual-qa-final5/comparison-final-decision.png`

The implementation intentionally displays the hash-verified project drawing rather than replacing it with the prototype sample SVG. Only the source-supported candidate `CAND-SAMPLE-PAGE17` is shown; no second candidate was invented to imitate the sample.

## Visual comparison result

- The centered dark shell, four separated metric cards, compact three-column desktop workspace, light drawing canvas, dense candidate list, three viewer modes, three detail tabs, and lower action/decision regions now match the approved hierarchy and density.
- The annotation right panel exposes evidence, approved-rule readiness, abstention context, and explicit confirmation controls while preserving server-side rule and math authority.
- The final-review route exposes packet evidence, audit/exception/conflict/abstention/confidence domains, and the separate compact human-decision form without creating a default decision.
- The desktop annotation action panel and status strip are fully visible at 1863 x 1494. The final decision panel and process strip are also fully visible at that viewport.
- Mobile layouts collapse to one column without horizontal overflow. Lower confirmation and decision forms remain reachable by scrolling, and print rules restore full-flow content.
- Two independent screenshot reviews returned PASS with no P0 or P1 findings. One review reported no P2 findings; the accessibility-oriented review recorded two non-blocking P2 recommendations: add optional mobile jump links to lower actions, and recheck very small provenance/process text for low-vision users.

## Browser interaction and runtime checks

- Annotation: candidate selection, original/detection/compare modes, evidence/rules/confirmation tabs, and the lower confirmation form were exercised.
- Final review: both review items, original/evidence/compare modes, evidence/rules-calculations/audit-exceptions tabs, zoom to 1.2 and reset, and the lower final-decision form were exercised.
- Reviewer actions and human decisions remained unselected after reload.
- Annotation desktop: action panel bottom 1451; status strip bottom 1493; no horizontal overflow.
- Final review desktop: decision bottom 1473; process strip bottom 1492; no horizontal overflow.
- Mobile 820 x 1180: both routes had no horizontal overflow and lower forms were reachable.
- The evidence image reported complete in both routes. Browser developer logs were empty in the final desktop passes.

## Resolved findings

1. The English interface was fully localized to Korean while stable machine identifiers and engine terms remain unchanged.
2. The confirmation route now follows the approved evidence -> rules -> input-confirmation information architecture.
3. The final-decision panel was implemented on the final-review route, preserving the confirmation/final-decision authority boundary.
4. Shell margins, metric cards, list density, toolbar hierarchy, viewer metadata, right-panel rhythm, and bottom-panel compactness were aligned to the source.
5. Desktop vertical budgets were tightened until action, decision, and process/status strips fit the acceptance viewport.
6. Responsive, print, focus, no-preselection, offline, immutable evidence, and append-only server boundaries remain covered by automated contracts.

## Repository verification

- Documentation integrity: PASS, 0 errors, 72 warnings, 74 documents (28 current, 2 generated, 44 historical). Report: `build/documentation-integrity-report-issue5-final3.json`; SHA-256 `e0ad7f1bee3036236b312a469a862a6488126e78b3c078ef9597d32ce4b1bc3b`.
- Pytest: 1082 passed, 6 skipped.
- Ruff: `All checks passed!`.
- Compileall: passed.
- Required `mypy src`: environment gate failed before repository code analysis because installed NumPy 2.5.1 uses Python 3.12 PEP 695 syntax while the repository mypy target is Python 3.11 (`numpy/__init__.pyi:737`). Supplemental `mypy --python-version 3.13 src` passed for 170 source files. No dependency or typing-policy change was made as part of this UI issue.
- Wheel checks for Python 3.11/3.13, GitHub Actions, release-output validation, and process attestation were not executed for this non-release UI change and remain pending.

## Comparison history

- Pass 1: English labels and task architecture did not match the approved reference.
- Pass 2: Korean localization passed, but the confirmation tabs, final-decision route, and compact viewport layout were incomplete.
- Pass 3: route-specific information architecture and final-decision UI were implemented; automated visual contracts passed.
- Pass 4: repeated exact-viewport and mobile Browser checks removed the remaining lower-panel clipping and produced the final comparison boards.
- Review follow-up: populated global audit data is bounded by desktop internal scrolling while mobile and print retain full-flow visibility; test fixtures cover populated audit, conflict, abstention, and confidence records.

## Remaining human boundary

The UI packet is ready for inspection. A reviewer must still independently confirm drawing inputs and record any final human decision; this QA result is not a project approval.
