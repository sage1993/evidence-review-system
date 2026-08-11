# Issue #62 bbox-optional Retrieval Implementation Plan

> **Execution:** Use `superpowers:test-driven-development` for each behavior change and `superpowers:verification-before-completion` before declaring the issue resolved.

**Goal:** Preserve evidence in retrieval when page identity and text exist but bbox is unavailable, while keeping exact bbox citations fail-closed.

**Base:** `main` at `8b37e77b6e2b48653b73f96e5ad0369c7e0f4ded`, which already includes Issue #63 page-geometry validation.

## Architecture

Separate retrieval location quality from exact citation eligibility:

- `bbox != None` → `EXACT_BBOX` → exact `Citation` may be generated.
- `bbox == None` → `PAGE_ONLY` → evidence remains retrievable, but exact citation generation returns `BBOX_UNAVAILABLE`.
- malformed bbox → do not downgrade to `PAGE_ONLY`; preserve existing skip/fail-closed behavior.

`retrieval_records` is a rebuildable cache. To avoid a schema migration, canonical SQL `NULL` bbox values are represented inside the cache as JSON `null`, satisfying the existing `TEXT NOT NULL` column while retaining the semantic distinction.

## Constraints

- Do not make `Citation.bbox` optional.
- Do not fabricate page-sized or zero bbox fallbacks.
- Do not alter Issue #63 page geometry contracts.
- Keep exact bbox coordinates unchanged.
- Preserve deterministic FTS ordering: `bm25_rank`, then `evidence_id`.
- No evidence schema version bump.

## Tasks

### Task 1 — Lexical retrieval RED/GREEN

- Add a failing integration test proving bboxless element evidence is currently omitted.
- Remove bbox-presence filtering for element indexing.
- Encode absent bbox as JSON `null` in `retrieval_records`.
- Decode JSON `null` as `RetrievalHit.bbox = None`.

### Task 2 — table/visual parity

- Add failing bboxless table and visual lexical tests.
- Apply the same index policy to tables and visuals.
- Keep malformed non-null bbox records excluded rather than converting them to page-only.

### Task 3 — explicit citation quality

- Change `RetrievalHit.bbox` to `BBox | None`.
- Add `CitationQuality.EXACT_BBOX` and `CitationQuality.PAGE_ONLY`.
- Make `RetrievalHit.citation()` fail closed with `CitationUnavailableError(reason_code="BBOX_UNAVAILABLE")` for page-only hits.

### Task 4 — downstream retrieval channels

- Make structured retrieval preserve page-only hits.
- Make fusion output emit `bbox: null` and explicit `citation_quality` for page-only hits.
- Keep graph traversal compatible through `load_indexed_hit()`.

### Task 5 — evidence bundle citation boundary

- Keep page-only hits in the evidence bundle.
- Set `citation` to `null` instead of fabricating coordinates.
- Add `citation_unavailable_reason: "BBOX_UNAVAILABLE"`.
- Preserve the existing exact citation object for bbox-resolved hits.

### Task 6 — regression and determinism tests

Cover:

- element/table/visual with bbox absent;
- element/table/visual with bbox present;
- exact bbox coordinate preservation;
- page-only exact-citation refusal;
- malformed bbox not silently downgraded;
- deterministic ordering across repeated queries and index rebuilds;
- structured/fusion/bundle page-only propagation.

## Verification Gate

Run, in order where the environment permits:

```text
python -m pytest tests/integration/retrieval/test_bbox_optional.py -q
python -m pytest tests/integration/retrieval/test_bbox_optional_channels.py -q
python -m pytest tests/unit/retrieval tests/integration/retrieval -q
python -m ruff check .
python -m mypy
python -m compileall -q src
python -m pytest
```

When GitHub Actions are unavailable or billing-blocked, record that CI is unobservable and do not claim CI PASS. Use the repository's established manual-validation policy instead.

## Completion Criteria

- bboxless element/table/visual evidence appears in lexical retrieval;
- page-only and exact-bbox hits are explicitly distinguishable;
- exact citation cannot be created from page-only evidence;
- page-only bundle output exposes `BBOX_UNAVAILABLE`;
- malformed bbox is not silently treated as page-only;
- existing exact bbox coordinates are unchanged;
- retrieval result ordering remains deterministic;
- focused and full validation gates pass, or any unavailable gate is explicitly documented.
