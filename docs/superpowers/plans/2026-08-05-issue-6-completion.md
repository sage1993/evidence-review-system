# Issue #6 remaining drawing pipeline

## Scope

This plan completes the post-M2 follow-up recorded in the master roadmap:

1. reviewer-confirmed calibration and deterministic pixel-to-length conversion;
2. staged candidate extraction for explicit parser metadata, vector lines, and declared semantic geometry;
3. self-contained Review Packet v2 drawing-evidence rendering.

The existing M0 contracts, M1 immutable case storage, M2 browser annotation workspace, and Issue #56 orchestration remain the authorities. This plan does not define duplicate geometry, status, confirmation, or human-decision contracts.

## Safety rules

- Extracted candidates always start as `UNCONFIRMED`.
- Extraction returns no candidates unless the source quality assessment is `PASS`.
- Calibration requires an explicit reviewer, offset-aware timestamp, source hash, page, axis-aligned reference, and positive decimal length.
- Calibration and pixel-to-real conversion call registered Decimal Math Engine formulas; browser code performs no arithmetic.
- Calibration artifacts are create-only under the case root.
- Packet rendering validates Review Packet v2 before drawing any overlay and keeps `human_decision: null`.
- Page images are embedded as data URIs; no external resource is allowed.

## Verification record

- Added RED tests before production modules:
  - `tests/unit/parsing/test_drawing_calibration.py`
  - `tests/unit/parsing/test_drawing_extractors.py`
  - `tests/integration/review_packet/test_drawing_evidence_renderer.py`
- Added production modules:
  - `src/ansim_review/parsing/drawing_calibration.py`
  - `src/ansim_review/parsing/drawing_extractors.py`
  - `src/ansim_review/review_packet/drawing_evidence.py`
- Added isolated `DRAWING_SCALE@1.0.0` and `DRAWING_LENGTH@1.0.0` formulas in a separate drawing registry so existing frontage-ratio golden hashes remain unchanged.
- AST syntax verification passed for all changed source and test files.
- Dependency-isolated runtime smoke verification passed for calibration, staged extraction, all four geometry overlays, embedded image output, and JSON-null human decision.
- GitHub Actions run `30929218507` had four jobs with `steps: null`; it is recorded as unavailable execution evidence, not as a code failure or PASS.

Full repository pytest, Ruff, mypy, compileall, wheel, and browser acceptance must be run from a complete checkout before marking Issue #6 closed.
