# Drawing Browser Handoff Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add browser-visible calibration and read-only Review Packet routes to the existing loopback drawing annotation workspace, then verify them with the sample PDF and publish the resulting commit to PR #58.

**Architecture:** Extend the existing run-scoped annotation HTTP server with in-memory confirmation/calibration indexes, strict calibration POST validation, and packet selection/rendering. Keep calibration math and Review Packet v2 validation in existing modules; the browser layer only binds verified artifacts and renders a self-contained HTML page. Preserve existing annotation behavior and add launcher URLs/evidence output.

**Tech Stack:** Python 3.11/3.13, `http.server`, existing dataclasses/canonical JSON, pytest, Ruff, mypy, compileall, in-app browser QA.

---

## Chunk 1: Contract and persistence tests

**Files:**
- Modify: `tests/unit/parsing/test_drawing_calibration.py`
- Modify: `tests/integration/drawing_review/test_local_server.py`
- Create: `tests/integration/drawing_review/test_browser_handoff.py`
- Modify: `src/ansim_review/parsing/drawing_calibration.py`

- [ ] Write failing tests for persisted candidate/confirmation bindings, calibration GET form, valid calibration POST response, exact replay, malformed input, no-write-on-failure, security/error headers, exact query rules (unknown/blank/duplicate keys, malformed percent escapes, and raw `+`), UTC timestamp ordering, calibration-after-confirmation validation, and restart-empty indexes.
- [ ] Run the focused tests and confirm they fail because the new routes/indexes/contracts are absent.
- [ ] Add the optional trailing binding fields and canonical compatibility behavior to `CalibrationRecord`.
- [ ] Run the calibration unit tests and focused server tests until the persistence contracts pass.

## Chunk 2: Browser server routes and packet rendering

**Files:**
- Modify: `src/ansim_review/drawing_review/local_server.py`
- Modify: `src/ansim_review/review_packet/drawing_evidence.py`
- Modify: `src/ansim_review/drawing_review/html_renderer.py`
- Modify: `tests/integration/review_packet/test_drawing_evidence_renderer.py`
- Modify: `tests/integration/drawing_review/test_browser_handoff.py`

- [ ] Add failing tests for packet pending/selection/binding, artifact tamper/missing, renderer failure, embedded image, calibration metadata, null human decision, exact strict `ReviewPacketV2` keys, exact `display_metadata` shape, authority-hash validation/startup failure, and no external URLs.
- [ ] Implement the minimal run-scoped indexes and calibration GET/POST handlers with exact status/error contracts.
- [ ] Build a strict valid ReviewPacketV2 mapping from verified records and add the renderer display-metadata contract.
- [ ] Run all focused browser and renderer tests and refactor only while green.

## Chunk 3: Launcher, browser QA, and evidence

**Files:**
- Modify: `scripts/run_drawing_annotation_workspace.py`
- Modify: `tests/integration/drawing_review/test_manual_annotation_browser_flow.py`
- Modify: `scripts/verify_issue_6_manual.ps1`
- Create: `tests/integration/drawing_review/test_launcher_output.py`

- [ ] Write failing tests for exact three-line startup output, startup authority validation, bound packet URL, annotation link enablement, and create-only browser evidence.
- [ ] Implement launcher URL output, authority-hash plumbing, annotation-to-calibration link, and deterministic evidence recording.
- [ ] Run the sample-PDF browser flow using `C:\Users\KSH\Downloads\샘플.pdf` in the in-app browser: confirm candidate, submit calibration values, open Review Packet, and inspect the null human decision and embedded overlay.
- [ ] Record `tmp/pdfs/pr58-sample/browser-evidence.json` against the exact PR HEAD and source hash.

## Chunk 4: Full verification and delivery

**Files:**
- Modify: `docs/superpowers/plans/2026-08-06-drawing-browser-handoff-plan.md`

- [ ] Run documentation validation, pytest, Ruff, mypy, compileall, and Python 3.11/3.13 wheel smoke checks from a clean state; record exact exit codes and the documentation report status/counts/SHA-256.
- [ ] Run the manual verification runner and inspect its report/artifact hashes, including the browser evidence SHA-256.
- [ ] Review the final diff, commit implementation and verification artifacts, push `codex/issue-6-complete-drawing-pipeline`, and report exact HEAD, test results, browser evidence, and remaining human review.
