# Drawing Review UI Alignment Design

## Goal

Align the existing drawing annotation workspace with the visual and interaction model in `tmp/drawing_evidence_review_ui.html`, while preserving the repository's existing Review Packet v2 contracts, verified source image handling, coordinate projection, and append-only reviewer action service.

## Reference and scope

The GitHub issue comment `#issuecomment-5152751517` and the local HTML prototype are the visual source of truth. This change applies to the drawing confirmation/annotation workspace, not the final `READY_FOR_HUMAN_REVIEW` packet page. The final `/review` screen remains a separate projection.

The reference prototype's hard-coded sample calculations, local file upload, `localStorage`, browser-side rule evaluation, and browser-owned final decision are not copied. They conflict with the offline deterministic runtime boundary. Existing server-owned action validation and append-only confirmation persistence remain authoritative.

## Screen structure

The rendered annotation workspace uses the reference layout:

1. A dark top bar with `INPUT CONFIRMATION REQUIRED`, page/run context, source integrity, and print action.
2. Four metric cards for source integrity, detected candidates, confirmed candidates, and workflow state.
3. A three-column main grid:
   - left: candidate/feature list with selected and pending states;
   - center: verified drawing image, original/detection/compare modes, SVG geometry overlay, and selected geometry metadata;
   - right: Evidence, Rules, and Input confirmation tabs.
4. A bottom reviewer-action area containing the existing ACCEPTED, REJECTED, EDITED, and CREATED actions, reviewer identity, confirmed value, unit, and manual geometry controls.
5. A status strip explaining the parser -> reviewer confirmation -> deterministic engine -> human review boundary.

## Data mapping

Each left-side feature comes from the validated `candidates` view-model array. Candidate ID, type, origin, status, normalized/raw value, and geometry are escaped and projected without invention. The source SHA-256, page, coordinate system, and page dimensions remain server-validated metadata.

The screen derives display-only counts from the candidate list. It does not calculate domain values, evaluate rules, or invent confirmations. The action form sends the existing strict payload to `/actions`; server-owned hashes, paths, confirmation IDs, and source identity remain absent from browser payloads.

## Interaction model

- Selecting a candidate synchronizes the list, overlay, metadata, and action controls.
- Original, Detection, and Compare buttons only change visual layers.
- Evidence, Rules, and Input confirmation tabs switch presentation only.
- Manual POINT, BBOX, LINESTRING, and POLYGON capture keeps the current coordinate conversion.
- Saving an action continues through the protected local server and append-only action service.
- No action is preselected and no reviewer decision is stored in browser storage.

## Responsive and print behavior

Desktop uses the reference 260px / flexible canvas / 330px grid. Below 1100px the right panel moves below the first two columns. Below 760px the screen becomes a single column with horizontal overflow contained inside tables and tool groups. Print uses a light, static, A4 landscape presentation and hides mutation controls.

## Verification

Acceptance requires:

- renderer contract tests for the reference landmarks and all existing action hooks;
- browser contract tests proving no browser-side math/rule evaluation or storage;
- existing local-server and append-only action tests;
- desktop and mobile browser screenshots compared with the reference HTML;
- candidate selection, display-mode switching, tab switching, and action submission evidence;
- no relevant console errors or document-level horizontal overflow.

