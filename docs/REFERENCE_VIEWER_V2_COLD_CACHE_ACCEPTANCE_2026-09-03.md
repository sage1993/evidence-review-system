# Reference Viewer v2 Cold-Cache Acceptance — 2026-09-03

## Scope

This record closes the cold-cache performance/finalization blocker for `agent/reference-viewer-v2` after moving large CASE_DRAWING tile materialization out of final `view-model-build` and into visual-analysis handoff preparation.

This acceptance does **not** claim unrelated release gates that were not executed, such as publish-mode artifact creation or a separate interactive human visual-QA pass.

## Tested code

- Branch: `agent/reference-viewer-v2`
- Tested HEAD: `3e818cbbca59e7adcceb97863572347032d4e44b`
- Source fixture SHA-256: `4105698c88ec34b3e590e7d93fc7e51e9c942c98ec966b483549b02ad369abc4`
- Fixture pages: 17
- Raster size: `4764 x 3368` per page
- Visual analysis ID: `VIS-CE51DB434C6799AE1CB6`
- Review run ID: `RUN-A9EEAECFF7E6358CEB79`

## Regression/static verification

```text
Focused pytest: 12 passed in 1.41s
Full pytest:    1779 passed, 1 skipped in 280.49s
Ruff:           PASS
mypy:           PASS — 235 source files
git diff --check: PASS
```

Focused tests:

```powershell
py -3.13 -m pytest -q `
  tests/unit/drawing_review/test_visual_page_tiles.py `
  tests/unit/drawing_review/test_visual_handoff.py `
  tests/unit/review_packet/test_case_visual_lazy_projection.py
```

Full/static commands:

```powershell
py -3.13 -m pytest -q
ruff check .
mypy src
git diff --check
```

## Cold-workspace setup

The acceptance workspace started without any pre-existing CASE_DRAWING page or tile cache:

```text
case-page-images-hq-v1: absent
case-page-tiles-v1:     absent
runs:                   absent
```

After standard `review-question prepare`:

```text
status:                  WAITING_VISUAL_ANALYSIS
visual_analysis_id:      VIS-CE51DB434C6799AE1CB6
case-page-tiles-v1:      present
PNG tiles:               102
page tile manifests:     17
```

This confirms large-page tile materialization occurred before external visual analysis and before Track A/Track B finalization.

## Identity preservation

The new cold workspace preserved the prior fresh handoff identity.

```text
visual-analysis-bundle SHA-256:
2D1EEC0EC7D175E991BCC6215EFF862C760E9E50F7E47D071BED942D716D5BC7

track-a-bundle SHA-256:
B9402A40203560729F22A787E313FA93B152C1A8FF8BDA14F008AF38422CE8C6

track-b-bundle SHA-256:
8F7C7A41B0E25DE47453DC175883CABE85926B5BB4831DDB34CE3E4664AAE79A
```

Because these bundle identities matched the previously generated fresh external outputs exactly, those external outputs were reused without changing IDs or semantic payloads.

## Standard workflow result

```text
submit-visual-analysis: WAITING_TRACK_A
visual candidate count: 17
submit-track-a:          WAITING_TRACK_B
submit-track-b:          PARTIALLY_RESOLVED
display_status:          OPENED
workflow transition:     FINALIZING -> READY_FOR_REVIEW
retry_count:             0
TRACK_B_RETRY_MISMATCH:  absent
```

`PARTIALLY_RESOLVED` is the finalizer's semantic status for this review and is not treated as a release-engineering failure. The workflow reached `READY_FOR_REVIEW` through the standard CLI path.

## Finalization read-only cache evidence

A complete file snapshot of `case-page-tiles-v1` was captured immediately before and after `submit-track-b --open`, including path, size, modification time, and SHA-256 for every cached file.

`Compare-Object` returned no differences.

Therefore finalization did not create, rewrite, or mutate the CASE_DRAWING tile cache.

## Performance result

### Before fix — cold finalization

```text
view-model-build:          5033 ms
deterministic_total_ms:    5516 ms
release budget:            <= 5000 ms
result:                    FAIL
```

### After fix — cold finalization

```text
view-model-build:             88 ms
page-image-verification:      29 ms
html-render-write:            19 ms
protected-server-start:      276 ms
browser-dispatch:             63 ms
deterministic_total_ms:      549 ms
external_wait_total_ms:    30925 ms
retry_count:                   0
```

Derived acceptance checks:

```text
deterministic_total_ms <= 5000:                 PASS — 549 ms
protected-server-start + browser-dispatch <= 2000: PASS — 339 ms
workflow READY_FOR_REVIEW:                      PASS
display_status OPENED:                          PASS
final review packet present:                    PASS
review HTML present:                            PASS
finalization tile mutation:                     PASS — none
```

Performance change versus the failing cold run:

```text
view-model-build:       5033 -> 88 ms   (-98.3%)
deterministic total:    5516 -> 549 ms  (-90.0%)
```

## Architecture/trust-boundary assessment

- No source/evidence authority change.
- No network/offline-boundary change.
- No human-decision authority change.
- No publish/release-package contract change.
- Existing tile manifest/SHA validation remains fail-closed.
- `ensure_visual_page_tiles()` remains the explicit materialization path.
- Final review projection uses read-only `load_visual_page_tiles()` and does not silently rebuild missing large-page caches.

## Data safety

No customer/source PDF, evidence database, raster page cache, tile cache, human decision, credential, token, or private runtime URL is committed by this acceptance record.

## Verdict

```text
Cold CASE_DRAWING tile lifecycle:       PASS
Cold view-model performance:            PASS
Standard Track A/B finalization:        PASS
Protected browser handoff:              PASS
Workflow integrity:                     PASS
Cold-cache performance blocker:         CLOSED
```

The scoped Reference Viewer v2 cold-cache release-engineering blocker is closed at tested HEAD `3e818cbbca59e7adcceb97863572347032d4e44b`.
