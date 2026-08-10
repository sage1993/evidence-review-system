# Issue #5 Visual Fidelity Correction Design

## Goal

Correct the current drawing confirmation and final review workspaces so they visibly follow the
approved Issue #5 drawing-review prototype while preserving the repository's deterministic engine,
verified-evidence, route-separation, and append-only human-record boundaries.

The correction is complete only when the rendered production screens, not a standalone mock, pass
same-viewport browser comparison against the user-supplied full-screen and focused reference PNGs.

## Approved visual target

The visual source of truth is Issue #5 comment `5152751517`, its attached
`drawing_evidence_review_ui.html`, and the eight user-supplied reference screenshots recorded in
`design-qa.md`.

The production screen must reproduce these visible characteristics:

- a centered, rounded dark shell with restrained outer margins;
- a compact header and safe action group;
- four separated, rounded summary cards;
- a 260 px / flexible / 330 px desktop grid;
- compact candidate rows with clear selected and pending states;
- a verified drawing viewer with original, detection, and compare modes;
- three-card selected-object metadata below the viewer;
- a right-side tab panel with dense evidence, rule, and confirmation content;
- a compact full-width lower action area;
- a short process-boundary strip;
- Korean interface copy, retaining only stable machine identifiers and contract values where useful.

The real verified drawing image and its server-provided SVG geometry replace the prototype's sample
SVG. This is an intentional evidence-authority difference, not a visual mismatch.

## Route and authority model

The two production routes share visual tokens and layout primitives but keep different write authority.

### Drawing confirmation route: `/annotation/{token}`

This route remains the drawing-candidate confirmation workspace.

- The left list is generated from validated drawing candidates.
- The center viewer displays the hash-verified source image once with canonical geometry overlays.
- The right `근거` tab shows candidate-wide extraction state, selected-candidate provenance, and the
  server-provided hold or abstention reason.
- The right `규칙` tab shows approved rule readiness and input bindings supplied by the server. It does
  not evaluate a rule in JavaScript.
- The right `입력 확인` tab presents confirmation completeness and the fields needed for the selected
  candidate action.
- The lower panel remains the existing append-only drawing action surface for `ACCEPTED`, `REJECTED`,
  `EDITED`, and `CREATED`. It is visually compacted to the reference proportions but is not relabeled as
  a final decision.
- Saving continues to POST the existing strict payload to the protected server. The browser does not
  create confirmation IDs, hashes, paths, engine results, or human decisions.

### Final review route: `/runs/{run_id}/{token}/review`

This route remains the Issue #5 final review workspace.

- The shared shell, summary-card treatment, three-column proportions, tabs, viewer metadata, and lower
  panel styling match the drawing prototype.
- The left list remains claim/evaluation oriented rather than pretending packet claims are drawing
  candidates.
- The center viewer shows verified page assets, exact quotes, and canonical overlays.
- The right side preserves all Issue #5 information domains: evidence, rules, calculations,
  exceptions/conflicts, and audit. Tabs may group related domains visually, but no domain may disappear.
- The lower panel uses the four allowed human decisions, reviewer identity, notes, reviewed time, and
  exact machine-packet SHA-256.
- Submitting a decision writes a separate append-only record. `final-review-packet.json` and
  `review.html` remain unchanged, and machine `human_decision` remains `null`.

## Shared presentation structure

The renderers remain independent because they consume different canonical view models. They share a
small set of CSS design tokens and equivalent semantic landmarks rather than a browser framework or a
new cross-package data contract.

### Header

The header height and typography follow the prototype. Unsafe prototype actions are not copied.

- Both routes may expose `HTML 인쇄` through `window.print()`.
- Annotation may expose the existing safe navigation to its confirmation area.
- Final review may expose decision export only after a valid decision envelope exists.
- Browser-local file replacement, destructive reset, and `localStorage` persistence are prohibited.

### Metrics

Metrics are server-derived projections displayed in four independent cards with 10-12 px gaps and
14 px radii. No metric is calculated from DOM text.

- Annotation: source integrity, candidate count, confirmation/action count, workflow state.
- Final review: citation/evidence count, approved rules, calculations, and readiness/abstention state.
  Missing inputs, conflicts, and confidence remain visibly available in the review details.

### Main grid

At desktop widths above 1180 px the grid is `260px minmax(450px, 1fr) 330px` inside the centered shell.
At the 1863 x 1494 comparison viewport, the complete primary workflow including the lower action area
must be visible without document-level horizontal overflow. The primary save button must not stretch to
the full height of unrelated form fields.

Below 1180 px, the right panel moves below the list and viewer. Below 820 px, all regions stack in one
column. Internal evidence panes may scroll, but persistent primary controls must remain reachable and no
document-level horizontal overflow is permitted.

### Candidate and review-item rows

Rows use transparent or softly tinted backgrounds, compact 10-12 px vertical padding, an 11 px radius,
and one clear selected outline. The list must not use heavy card chrome for every row. State color is
semantic: green for confirmed/ready, amber for pending/abstain, and red only for rejection or errors.

### Viewer

The viewer toolbar, three mode buttons, image stage, and three metadata cards follow the focused
reference screenshots. Original mode hides overlays, detection mode emphasizes evidence geometry, and
compare mode combines the verified image and overlays. These modes only change presentation.

The image remains direct verified evidence. No screenshot, sample plan, generated illustration, CSS art,
or replacement SVG may stand in for the source asset.

### Right-side tabs

Tab styling follows the reference's full-width labels and two-pixel active underline. Important hold
reasons, missing inputs, conflicts, and abstention reasons are visible without an extra disclosure step.

For annotation, the source-like Rule-as-Code cards display server-owned rule ID, version, approval/input
state, and current readiness. When no rule binding is available, the pane says so explicitly rather than
inventing the three sample rules from the prototype.

### Lower action panels

Both lower panels use a compact header and a three-column desktop form. Annotation retains drawing
action fields and geometry tools. Final review retains human-decision fields. Their titles and copy must
make the authority distinction unambiguous.

## Data flow and trust boundaries

```text
verified source + drawing candidates
    -> drawing review view model
    -> annotation HTML projection
    -> protected append-only drawing action endpoint

final-review-packet.json + verified page assets
    -> review packet view model
    -> review.html projection
    -> protected append-only human decision endpoint
```

All displayed identifiers, hashes, statuses, rule bindings, numeric values, coordinates, and reasons come
from validated server-side data. Browser JavaScript is limited to selection, tab switching, presentation
modes, zoom/scroll, geometry capture, form validation, and same-origin transport. It must not perform
domain arithmetic, rounding, threshold comparison, rule evaluation, evidence resolution, or packet
mutation.

## Error behavior

- Missing or hash-mismatched source images fail before rendering.
- Unsupported geometry and coordinate systems fail closed.
- Missing rule bindings or confirmation inputs render explicit waiting/abstention content.
- No candidate, action, or final decision is preselected.
- Decision and confirmation submissions reject unknown fields, invalid enum values, wrong tokens, wrong
  Origin/Host, oversized bodies, and packet/source hash mismatches.
- User-visible strings are escaped, and serialized data cannot break out of inert script containers.

## Testing strategy

Implementation follows red-green-refactor.

1. Add failing renderer tests for the exact shell landmarks, route-specific right-tab content, compact
   lower panels, and Korean copy.
2. Add failing CSS contract tests for the centered shell, separated metric cards, target grid, compact
   row rhythm, non-stretching primary action, and desktop viewport budget.
3. Add failing browser-contract tests proving modes, tabs, selection, and form transport still work while
   forbidden browser calculations and storage remain absent.
4. Implement the minimum renderer/CSS/JavaScript changes to pass each test.
5. Run route, append-only persistence, XSS, provenance, responsive, print, and performance regressions.
6. Capture annotation and final review at 1863 x 1494 and compare them with the full and focused reference
   screenshots in combined boards.
7. Fix every remaining P0/P1/P2 issue and repeat the capture until `design-qa.md` says `passed`.

## Acceptance criteria

- The annotation route visibly matches the reference shell, density, cards, list, viewer, tabs, and lower
  panel while retaining drawing-confirmation semantics.
- The final review route visibly matches the same design language and exposes the complete Issue #5 review
  domains and append-only human-decision form.
- At 1863 x 1494, each route's full primary workflow is visible and usable without horizontal overflow.
- At 1366 x 768 and mobile width, all controls remain reachable through the documented responsive layout.
- The source drawing/page asset is verified, shown once, and never replaced by prototype or generated art.
- No production browser code evaluates a rule or calculates a domain result.
- Machine packet and source artifacts are byte-identical before and after reviewer submissions.
- Relevant pytest, Ruff, mypy, compileall, documentation-integrity, browser interaction, console, and design
  QA gates pass before completion is reported.

## Non-goals

- No new parser, OCR, Math Engine, or Rule Engine behavior.
- No new Review Packet schema or duplicate status enum.
- No browser-owned source upload, reset, localStorage record, or machine result.
- No attempt to make real evidence visually identical to the prototype's sample drawing.
- No unrelated redesign outside the annotation and final review workspaces.
