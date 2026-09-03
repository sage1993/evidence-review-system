# Reference Viewer v2 port inventory

## Scope and baseline

This inventory records the selective port boundary for PR-B Task 1 from PR #121 into the current `agent/reference-viewer-v2` baseline.

- Baseline branch: `agent/reference-viewer-v2`
- Baseline HEAD: `4e754a0f0d587a6441470daf6cfe073532523d39`
- Baseline worktree: clean before this document
- Baseline verification: 1726 passed, 1 skipped; Ruff PASS; mypy PASS for 233 files; compileall PASS
- PR #121 HEAD: `efb8b54...`
- PR #121 and current `main`: diverged, 10 ahead / 2 behind; merge base predates PR #122

Wholesale merge or cherry-pick of PR #121 is prohibited. The current mainline behavior from PR #122 and the PR-A unified renderer remain authoritative where noted below.

## Port inventory

| Area | Decision | Boundary |
| --- | --- | --- |
| `reference_projection.py` | PORT | Port the reference type allowlist and bounded `TABLE` projection concept. Task 2 starts here. |
| `reference_pages.py` | PORT, reimplement | Port the verified-page and anchor model, including `PDF_BOTTOM_LEFT_POINTS` geometry. Do not port eager `data_uri` base64 embedding. |
| `builder.py` | PORT, selective | Add `document_page_count` and safe `reference` metadata only. Citation authority identity remains unchanged. |
| `case_visual_projection.py` | PORT, selective | Integrate reference document/page/anchor projection with the current #122 routing. Do not replace current related-reference routing. |
| `local_server.py` | PORT, selective | Implement only the protected lazy reference-page asset delivery needed by the current server contract. |
| related-reference routing | KEEP CURRENT MAIN | Preserve the current #122 implementation. |
| semantic findings | KEEP CURRENT MAIN | Preserve the current #122 implementation. |
| subject HQ/tile/lazy | KEEP CURRENT MAIN | Preserve current main behavior. |
| `not_comparable` | KEEP CURRENT MAIN | Preserve current main behavior. |
| selected-only / Decision Drawer | KEEP CURRENT MAIN | Preserve current main behavior. |
| unified workspace shell | KEEP CURRENT MAIN | Preserve the PR-A merged renderer. |

## Explicit exclusions

### PR #121 `case_visual_projection._claim_citations()` routing

Do not port this structure as-is. It builds Finding references from Track A direct claim citations only. The current mainline implementation from #122 separates direct references from retrieval-lineage-derived related references; replacing it would regress that routing.

### PR #121 `reference_pages.py` `data_uri`

Do not port the `data:image/png;base64,...` field. Raster bytes must not be duplicated in the `#review-model` JSON. Reference raster delivery belongs to the protected lazy asset path.

### PR #121 `render_case_visual.py` and `html_renderer.py` wholesale patches

Do not port either file wholesale. The #122 interaction/markup behavior and PR-A unified renderer have already converged in the current baseline. Any required typed-reference UI must be reimplemented narrowly in the current renderer.

## Authority and implementation constraints

- Preserve source, revision, page, source hash, and bbox/geometry provenance.
- Verified page geometry and anchors are valid to port; raster bytes are not.
- Reference metadata is projection metadata and must not change citation authority identity.
- Reference types are bounded to `TEXT`, `TABLE`, `PDF_PAGE`, `IMAGE`, `DIAGRAM`, and `DRAWING`.
- `TABLE` projection must remain bounded metadata rather than an unbounded table payload.
- Keep current main routing and renderer contracts intact while adding typed references.

## Task 2 entry point

The first implementation target is `reference_projection.py`. RED tests should first lock:

1. classification of `TEXT`, `TABLE`, `PDF_PAGE`, `IMAGE`, `DIAGRAM`, and `DRAWING`; and
2. bounded `TABLE` metadata projection.

Page serving and renderer changes are out of scope for this first RED/GREEN slice.

## Reference-only material

The 2026-08-23 old specification and plan are reference-only. The integrated 2026-08-26 specification and PR-B plan, together with the current mainline code, are authoritative.
