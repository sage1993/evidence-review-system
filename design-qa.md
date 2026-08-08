# Drawing Review UI Design QA

- source visual truth: `F:/evidence-review-system/tmp/drawing_evidence_review_ui.html`
- implementation: local drawing annotation workspace at `/annotation/{token}`
- implementation screenshot: `build/drawing-review-korean-selected-1440x1000.png`
- requested comparison viewport: 1440 x 1000 CSS px, device scale factor 1
- implementation pixels: 1265 x 712 (in-app browser content viewport)
- state: `입력 확인 필요`, five unconfirmed drawing candidates, detection mode,
  evidence tab, road-width candidate selected

## Full-view comparison evidence

The implementation was captured in the in-app browser after localization. The source HTML was
claimed successfully in the same browser, but screenshot capture of its `file:` URL was rejected
by browser URL policy even after the Browser plugin was explicitly selected. The policy cannot be
disabled or bypassed, so a valid combined side-by-side comparison input could not be created.

## Focused region evidence

The implementation header, metrics, candidate list, viewer, selected-candidate metadata, right
tabs, reviewer form, and status strip were inspected in the rendered page. Candidate selection
showed `도로 폭 표기`, `사각형 (420.0, 2780.0)`, and `미확인`. The rules pane showed only Korean
labels. There were no browser console warnings or errors.

## Interaction checks

- Candidate selection updates the SVG highlight and Korean object, geometry, and status labels.
- Original mode hides the evidence overlay; detection mode restores it.
- Evidence, rules, and confirmation tabs switch their visible pane.
- Reviewer actions remain unselected by default; no confirmation was written during QA.

## Required fidelity surfaces

- Fonts and typography: the compact sans-serif hierarchy and technical label weight remain
  consistent after Korean text replacement.
- Spacing and layout rhythm: Korean labels fit the existing 260 / fluid / 330 three-column layout
  without clipping in the captured desktop state.
- Colors and visual tokens: the dark navy, slate, green, amber, and blue tokens are unchanged.
- Image quality and asset fidelity: the verified raster drawing remains direct and unmodified; SVG
  content remains limited to trusted evidence geometry.
- Copy and content: all visible workspace labels, candidate types, statuses, geometry tools, engine
  states, and browser feedback are Korean. Machine contract values remain unchanged in data
  attributes and submitted payloads.

## Findings

- No implementation-only P0, P1, or P2 issue was found in the localized rendered screen.
- Automatic source-to-implementation visual comparison remains blocked because browser policy
  prevents source capture from the local `file:` URL.

## Comparison history

- Pass 1: English interface labels were identified as a P1 localization mismatch.
- Fix: translated visible renderer copy, candidate metadata, geometry tools, engine states, and
  runtime feedback while preserving contract values.
- Pass 2: localized implementation capture and interactions passed; source side-by-side evidence
  remains unavailable due the non-configurable browser policy.

## Final result

blocked
