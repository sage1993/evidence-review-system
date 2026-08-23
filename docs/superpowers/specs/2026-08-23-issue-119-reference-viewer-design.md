# Issue #119 Reference Viewer Completion Design

**Status:** Approved in conversation on 2026-08-23

**Goal:** Complete the remaining Visual Review Workspace acceptance criteria by
projecting authoritative reference citations into a real document viewer, linking
each Finding to independent reference and subject locations, preserving existing
evidence authority and routing boundaries, and validating responsive and performance
behavior at the required desktop viewports.

## Scope and constraints

This change extends the Visual Workspace already present on `main`. It does not
replace the workspace, create a new packet version, or redesign the formal review
pipeline.

- `REFERENCE_DOCUMENT` remains in the parser, Evidence DB, deterministic retrieval,
  and revision-scoped `page-images` pipeline.
- `CASE_DRAWING` and `SUPPORTING_IMAGE` remain in the case-visual raster pipeline.
- The final review packet and human-decision contracts remain unchanged.
- A reference projection is display-only. It does not add evidence, alter citation
  authority, create calculations, or create rule outcomes.
- An unconfirmed visual candidate remains unavailable to deterministic Math or Rule
  Engine inputs.
- Existing source bytes, parser output, page geometry, hashes, and immutable run
  artifacts remain authoritative and fail-closed.
- General reference PDF pages keep the existing 2x cache policy. The 4x policy remains
  scoped to CASE PDF raster generation.
- The implementation must not serialize the same raster payload more than once in an
  archival HTML document.

## Current data flow

### Reference evidence

```text
REFERENCE_DOCUMENT source
  -> source-batch parser adapter
  -> documents/revisions/pages/elements/tables/visuals in evidence.sqlite
  -> retrieval_records and exact citation
  -> revision-scoped page-images/<REVISION>/page-NNNN.{png,json}
  -> final packet citation identity
  -> review view-model claim.citations
```

The citation already contains `document_id`, `revision_id`, `page_number`,
`source_hash`, PDF-coordinate `bbox`, page geometry, quote, title, and evidence type.
The Review Workspace verifies the matching cached page bytes, source hash, and page
geometry before rendering.

### Subject evidence

```text
CASE_DRAWING / SUPPORTING_IMAGE
  -> immutable case attachment
  -> validated visual-analysis handoff
  -> DrawingCandidate + issue/claim lineage
  -> case-page-images cache
  -> case_visual_review projection
  -> Subject raster + SVG geometry overlay
```

### Existing gap

`case_visual_projection` links a drawing candidate to claims and citation IDs, but
`render_case_visual._references()` reduces those citations to text cards. It does not
consume the citation page identity or bbox. The visual renderer therefore cannot show
or focus the authoritative reference page.

The normal HTML renderer still constructs its legacy evidence viewer in visual mode,
although CSS hides it. Adding a second copy of each citation page directly to the new
Reference Viewer without changing this flow would duplicate raster base64 payloads.

## Chosen architecture

Add a projection-only Reference Viewer model below the existing review view-model.
The projection is built from resolved citations, Evidence DB auxiliary records, and
verified page-image cache artifacts. It never changes final packet serialization.

The resulting visual projection contains three explicit collections:

```text
case_visual_review
  reference_documents[]
  reference_pages[]
  findings[]
    reference_anchors[]
    subject_region
  subject_pages[]               # current pages collection, renamed only internally
```

The existing outward `pages` field may remain as a compatibility alias while tests and
the renderer migrate. No immutable input contract depends on this projection shape.

### Reference document projection

Each referenced document contains:

```json
{
  "document_id": "DOC-...",
  "revision_id": "REV-...",
  "document_name": "서울특별시 건축조례",
  "page_count": 24,
  "page_asset_keys": ["reference-page-1", "reference-page-2"]
}
```

Only pages cited by Findings in the current run are materialized into the archival
HTML. This keeps multi-page sources bounded. Previous/next controls traverse the
materialized pages for the selected reference document. Arbitrary uncited-page
browsing is not added in this issue.

Each reference page contains one verified raster and its PDF page geometry:

```json
{
  "asset_key": "reference-page-1",
  "document_id": "DOC-...",
  "revision_id": "REV-...",
  "page": 5,
  "source_hash": "...",
  "width": 595.0,
  "height": 842.0,
  "rotation": 0,
  "image_sha256": "...",
  "data_uri": "data:image/png;base64,..."
}
```

Page bytes are accepted only through the existing verified page-image boundary. A
missing cache entry, mismatched source hash, invalid metadata, or geometry mismatch
continues to fail closed.

### Reference anchor contract

Each Finding owns one or more reference anchors independently of its subject region:

```json
{
  "anchor_id": "CIT-...",
  "type": "TEXT",
  "document_id": "DOC-...",
  "revision_id": "REV-...",
  "page": 5,
  "page_asset_key": "reference-page-1",
  "title": "제8조",
  "quote": "...",
  "bbox": {
    "coordinate_system": "PDF_BOTTOM_LEFT_POINTS",
    "coordinates": [72.0, 420.0, 510.0, 460.0]
  },
  "table": null,
  "visual": null
}
```

Allowed semantic types are `TEXT`, `TABLE`, `PDF_PAGE`, `IMAGE`, `DIAGRAM`, and
`DRAWING`. Classification is deterministic:

- table retrieval records or table elements become `TABLE`;
- visual records and figure/image/diagram/drawing elements are mapped using their
  parser-provided kind;
- textual clauses and paragraph-like elements become `TEXT`;
- an otherwise valid page-bound citation becomes `PDF_PAGE`.

Classification affects presentation only. It does not increase authority.

### Table anchors

The projection may expose an allowlisted semantic table structure when the
authoritative parser record contains structured rows/cells. The projection exposes
only display labels, cell text, row/column positions, spans, and explicit stable cell
or range identifiers. Raw database JSON is never copied wholesale to the browser.

An individual row or cell is highlighted only when the parser record supplies an
explicit anchor/range binding. The renderer must not infer a normative row or cell by
matching model prose. When no explicit cell-level binding exists, the Reference Viewer
shows the verified PDF page and highlights the authoritative table bbox as a whole.

### Visual anchors

Image, diagram, and drawing anchors use the same verified reference page raster and
PDF-coordinate SVG overlay. The projection may include the parser-provided visual ID
and kind for focus orchestration, but internal IDs remain hidden from the normal UI.

## Rendering design

The Reference Viewer gains its own toolbar, page stage, transform state, and detail
sheet.

- The page stage renders the verified PDF raster exactly once.
- The SVG overlay converts the citation PDF bbox to the cached page viewport,
  including existing rotation handling.
- TEXT renders the page plus a readable, highlighted quote/clause detail sheet.
- TABLE renders the page plus a semantic table detail sheet when structured data is
  available; the selected row/cell receives accessible focus and highlight styling.
- IMAGE, DIAGRAM, and DRAWING render the page plus the SVG region overlay and a compact
  source caption.
- PDF_PAGE uses the common page renderer and optional bbox.

Reference controls support previous/next materialized page, cursor-centered wheel
zoom, left-button pan, double-click Fit, `+`, `-`, and Fit. Subject controls keep their
current behavior.

Raster images and overlay SVGs share the same stage box and `object-fit: contain`
geometry. SVG strokes use `vector-effect: non-scaling-stroke`.

## Finding focus orchestration

Finding activation performs two independent focus operations:

```text
activate Finding
  -> select reference anchor and reference page
  -> apply reference-only fit/focus transform
  -> reveal/scroll the clause or table cell
  -> select subject page
  -> apply subject-only fit/focus transform
  -> emphasize the selected subject overlay
```

Reference and Subject use separate state objects. No scale, pan offset, or pixel
coordinate is copied between viewers.

Focus computes the bounding box center and a bounded scale that makes the region
legible without exceeding the existing 50% to 500% range. Fit resets only the viewer
whose control was used. Manual pan/zoom in one viewer does not affect the other.

## HTML payload and protected delivery

In visual mode, the renderer does not emit the hidden legacy evidence page viewer.
The Reference Viewer becomes the only archival serialization site for reference page
rasters.

After the Reference and Subject `<img>` elements have been rendered, their `data_uri`
fields are removed from the object serialized into `#review-model`. A regression test
counts the exact data URI occurrences.

Reference page images use the existing `data-page-image-source` provenance attributes.
The protected server can therefore replace archival base64 with the existing tokenized
`page-images/<revision>/<page>/<source-hash>` route. Subject case rasters are not moved
into the reference route in this change.

## Responsive design

The required viewports are handled as follows:

- `1920x1080`: Reference, Subject, and Findings remain visible in the fixed workspace.
- `1440x900`: the same three-panel layout remains, with compact toolbar spacing and a
  bounded Findings width.
- `1366x768`: Findings becomes an off-canvas drawer opened by a visible Findings
  control. Reference and Subject retain the existing resizable split and minimum
  readable widths. Closing the drawer returns focus to its trigger.

The workspace continues to own the viewport. Document stages scroll or pan internally;
the page body does not return to a long vertical review workflow.

## Performance policy

- Reference ingestion continues to generate its existing revision cache. This issue
  does not change ingestion to 4x and does not add a second cache namespace.
- The final HTML reads and embeds only unique cited reference pages.
- Duplicate citations on one page share one raster asset and separate SVG overlays.
- The protected presentation continues to remove reference base64 and loads only the
  active and adjacent materialized pages through the existing local route.
- Zoom is CSS/SVG transform-based up to 500%; it does not regenerate raster bytes.
- Measurements will record source raster dimensions and bytes, generated HTML bytes,
  render time, and process memory delta where the platform permits a stable reading.
- Tile rendering is explicitly out of scope unless measurement demonstrates an
  acceptance-blocking problem that cannot be addressed by cited-page materialization.

## Failure behavior

- Unknown or malformed projection fields fail rendering rather than silently choosing
  the wrong source page.
- A citation whose page cache cannot be verified fails closed under the existing page
  verification errors.
- Malformed table structures are ignored for semantic rendering while the verified
  page and authoritative bbox remain available; no raw JSON is exposed.
- A Finding without normative citation renders the existing explicit empty-reference
  state and keeps its subject observation `not_comparable`/review boundary.
- Reference projection failures are not converted into retrieval-no-evidence or a
  legal conclusion.

## Test strategy

Development follows red-green-refactor cycles.

Automated coverage includes:

- TEXT quote/clause projection and highlighted detail rendering;
- PDF page identity, exact page raster selection, bbox conversion, and focus metadata;
- TABLE semantic rendering and explicit row/cell highlight;
- IMAGE/DIAGRAM/DRAWING type mapping and SVG overlay;
- independent Reference and Subject page/transform targets;
- Subject wheel, pan, Fit, page navigation, and overlay regression contracts;
- REFERENCE_DOCUMENT and CASE_DRAWING routing boundaries;
- one-time raster serialization in archival HTML and stripped review-model payload;
- protected reference page lazy delivery;
- 1920, 1440, and 1366 responsive DOM/CSS contracts;
- shared-page render time and HTML-size performance bounds.

Rendered manual QA uses the in-app Browser path against actual generated review HTML at
`1920x1080`, `1440x900`, and `1366x768`. It exercises page navigation, zoom, pan, Fit,
Finding changes, independent focus, divider reset, Findings drawer, console health, and
body scroll behavior.

## Acceptance boundaries

The work may report PASS only for gates actually executed. A valid implementation still
requires focused tests, Ruff, mypy, compileall, the complete pytest suite, browser QA at
all three required viewports, and recorded performance measurements. GitHub Actions and
manual scenarios not executed remain `NOT_EXECUTED`.

The branch is not merged automatically. Issue #119 receives an evidence-backed status
comment only after the applicable gates complete.
