# Issue #5 Review Workspace Design

## Goal

Turn the existing read-only Review Packet v1/v2 HTML projection into a local, self-contained review workspace that lets a human move from a claim to its verified evidence, deterministic calculation, rule result, uncertainty, and separate human decision record without changing machine evidence.

The browser remains a review surface, never a decision or calculation engine. `human_decision` stays `null` in every machine packet.

## Requirements derived from Issue #5

The output must visibly provide:

- a top status band containing the original question, run ID, run time, case ID, snapshot hash, formula/rule manifest versions, workflow/finalizer state, and the fixed warning that machine evaluation is not the final decision;
- summary metrics for citations, approved rules, calculations, missing inputs, unresolved conflicts, and confidence;
- a left review-item navigator keyed by `claim_id`/`evaluation_id`;
- a central evidence viewer with verified page image, canonical bbox SVG overlay, exact quote, document/revision/page/element/source-hash identity, raw/reviewed text distinction, and evidence navigation;
- right-side tabs for evidence, rule, calculation, exception/conflict, and audit data;
- a bottom decision form for reviewer identity, one of the four approved decisions, notes, decision timestamp, and machine packet SHA-256;
- synchronization between selected review item, central evidence, and right-side detail panels;
- ready and abstain states, including explicit missing-input, conflict, and abstention reasons;
- a self-contained archival HTML file that works without network access;
- a protected loopback server that can submit a separate append-only decision record;
- browser JavaScript limited to selection, tabs, navigation, zoom, scrolling, and form transport. It must not perform arithmetic, rounding, threshold comparison, rule evaluation, source resolution, or packet mutation.

## Existing authority and compatibility

The machine packet contracts in `schemas/review-packet-v2.schema.json`, `src/ansim_review/contracts/review.py`, and `src/ansim_review/contracts/review_v2.py` remain authoritative. v1 packets continue to render through the existing compatibility path. v2 fields such as `case_id`, `snapshot_sha256`, `formula_manifest_sha256`, `rule_manifest_sha256`, `evidence`, `drawing_evidence`, `exceptions`, `conflicts`, `abstention_reasons`, and `human_decision` are displayed as provided or deterministically resolved; the renderer never invents them.

The existing append-only human decision writer remains the persistence authority. Its timezone-aware `reviewed_at` envelope is the repository's canonical decision timestamp; the UI label is `Decision time`. The browser submits the existing `reviewed_at` field and does not create a second competing timestamp contract.

Existing `final-review-packet.json`, run-local `review.html`, runtime packaging, and v1 golden fixtures remain compatible. The new layout is a projection change, not a machine packet schema rewrite.

## Chosen approach

Use a single self-contained HTML document with three layers:

1. **Server-side view model**

   Extend `build_review_view_model` so it returns normalized review items, verified citations, calculation/rule relationships, status domains, summary metrics, audit data, and a packet hash. It resolves citation identity from the evidence database rather than trusting display fields from a model response. It rejects missing or contradictory evidence before HTML publication.

2. **Deterministic HTML shell and embedded assets**

   Extend `html_renderer.py` and `review.css` to render the complete layout. Page images are verified once per `(revision_id, page_number, source_hash)` and embedded once in a page-asset registry. Each citation references the registry entry and draws its own SVG overlay. CSS provides desktop three-column layout, narrow-screen stacking, print-safe A4 output, visible status separation, and clear empty/error states.

3. **Small projection-only browser controller**

   Add an inline `review.js` asset or an equivalent renderer-owned script. It reads an inert serialized view model and toggles already-rendered DOM nodes. It owns selected item, active tab, page navigation, zoom, evidence focus, and server decision submission only. It never calculates values or constructs machine evidence. In `file:` archival mode, the form downloads a human decision envelope; in protected HTTP mode, it posts the validated envelope to the same-origin decision endpoint.

This keeps the runtime offline and dependency-free while delivering the issue's interaction model. A separate SPA would add a build and packaging boundary without improving evidence authority.

## Layout and interaction model

```text
┌────────────────────────────────────────────────────────────────────┐
│ status / question / run metadata / packet hash / warning            │
├───────────────┬─────────────────────────────┬──────────────────────┤
│ review items  │ evidence viewer             │ detail tabs          │
│ claim/rule    │ page image + SVG bbox       │ evidence             │
│ status badges │ quote + source identity     │ rule / calculation   │
│ missing/conf. │ prev/next/zoom/focus        │ exceptions / audit   │
├───────────────┴─────────────────────────────┴──────────────────────┤
│ human decision form: reviewer / decision / notes / timestamp / hash │
└────────────────────────────────────────────────────────────────────┘
```

The initial selected item is the first claim with a citation, or the first review item when no citation exists. A claim selection updates all panels by stable IDs. A citation focus selects its page asset and adds an active overlay class without changing the canonical coordinates. Tabs hide/show content only; they do not discard any evidence.

The top status distinguishes `workflow_state`, `finalizer_status`, `reason_codes`, individual rule statuses, and the blank human decision. `SATISFIED` or `NOT_SATISFIED` is never rendered as the overall question decision.

## Data flow

```text
final-review-packet.json + verified evidence DB + page assets
        │
        ▼
build_review_view_model()
        │  validates IDs, hashes, citations, relationships
        ▼
review view model + packet_sha256
        │
        ├── render_review_html() ──► self-contained review.html
        │                              └─ CSS + JS + verified images
        │
        └── protected localhost server
              ├─ GET review/packet/hash
              └─ POST decision ──► write_human_decision()
```

Finalization writes the packet first, generates the HTML only after all required evidence resolves, and appends `READY_FOR_REVIEW` only after both artifacts exist. A missing packet, missing verified image metadata, hash mismatch, unsupported packet, or unresolved cited evidence prevents the final review route from becoming available.

## Error and security behavior

- Machine packets with non-null `human_decision` are rejected.
- A claim with no citation is an explicit review error for evidence-backed ready cases; abstain packets show the missing/abstention reason instead of silently hiding it.
- Source, revision, page, element, bbox, and image hashes are verified before display.
- User-visible strings are HTML-escaped and serialized JSON is safely embedded without executable user content.
- No external images, scripts, fonts, stylesheets, network calls, or CDN resources are emitted.
- The HTTP server remains loopback-only, token-scoped by run, exact-Host/same-Origin protected, CORS-disabled, body-limited, path-safe, and symlink/reparse-point resistant.
- The decision endpoint validates the exact allowed fields and compares the supplied packet hash to the current packet bytes before append-only create.
- No route or browser action edits `final-review-packet.json`.

## Testing and browser QA

Unit tests will cover view-model normalization, summary metrics, stable item relationships, status-domain separation, and decision-envelope construction. Renderer tests will cover all planned sections, raw/reviewed text escaping, active item metadata, single page-asset embedding, inline script restrictions, responsive/print CSS markers, ready/abstain states, and deterministic output for repeated input.

Integration tests will cover:

- real v1 and v2 golden packets;
- cited evidence and drawing evidence with overlays;
- missing evidence and hash mismatch fail-closed behavior;
- protected GET and POST routes;
- packet hash-bound append-only decisions;
- `review-run finalize --open` starting/targeting the run-scoped local route;
- 20-page/100-citation bounded output size and render fixture timing.

Manual QA will inspect ready and abstain cases at 1366×768, 1920×1080, and a 4K viewport, then inspect print preview. The reviewer must be able to identify the evidence location, calculation path, rule version, uncertainty, and decision input without opening machine JSON.

## Non-goals

- no model/API calls;
- no new calculation or rule evaluation logic;
- no browser-side arithmetic or evidence resolution;
- no final legal/business decision by the machine;
- no unrelated redesign of drawing annotation workflows;
- no replacement of the existing packet contracts with an SPA-specific schema.
