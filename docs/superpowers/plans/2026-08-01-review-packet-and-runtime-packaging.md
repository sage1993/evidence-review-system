# Review Packet and Runtime Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render source-traceable JSON/HTML review packets and export the same deterministic runtime for Codex Desktop and ChatGPT web without API calls.

**Architecture:** A read-only renderer consumes finalized packet JSON and local page images. Human decisions live in separate append-only files. Exporters build reproducible Codex and web bundles with evidence DB, rules, formulas, instructions, and self-tests.

**Tech Stack:** Python 3.11+, HTML/CSS/SVG, html/base64/zipfile/json, pytest.

## Global Constraints

- Renderer cannot change engine outputs.
- Machine packet keeps `human_decision: null`.
- Screen shows source, clause, exact quote, page/bbox, calculation trace, rule version, confidence basis, exceptions, conflicts, and abstention reasons.
- Web runtime requires no `pip install` and no server.

---

### Task 1: Review View Model

**Files:** Create `src/ansim_review/review_packet/builder.py`; test `tests/unit/review_packet/test_builder.py`.

- [ ] Test the view model includes every required section and blank decision.
- [ ] Run and observe failure.
- [ ] Resolve display source fields from evidence DB and verify hashes rather than trusting LLM display text.
- [ ] Run tests.
- [ ] Commit: `git commit -m "feat: build reviewer-facing evidence model"`.

### Task 2: Self-Contained HTML and BBox Overlay

**Files:** Create `src/ansim_review/review_packet/html_renderer.py`, `src/ansim_review/review_packet/assets/review.css`; test `tests/integration/review_packet/test_html_renderer.py`.

- [ ] Test HTML contains document/page, exact quote, `data-bbox`, Math Engine values, confidence factors, `Machine evaluation is not the final decision`, and no preselected decision.
- [ ] Run and observe failure.
- [ ] Escape all LLM text, embed cited page images as base64, draw SVG rectangles from canonical bboxes, and produce print-safe A4 output.
- [ ] Run automated test and manually open a fixture HTML.
- [ ] Commit: `git commit -m "feat: render self-contained human review packet"`.

### Task 3: Separate Human Decision Record

**Files:** Create `src/ansim_review/review_packet/decision_record.py`; test `tests/unit/review_packet/test_decision_record.py`.

- [ ] Test reviewer identity, packet hash, allowed decision, and append-only file behavior.
- [ ] Run and observe failure.
- [ ] Write `runs/<run_id>/human-decisions/<timestamp>-<reviewer>.json`; refuse modification of existing records.
- [ ] Run tests.
- [ ] Commit: `git commit -m "feat: separate human decision records"`.

### Task 4: Codex Workspace Bundle and AGENTS Routing

**Files:** Create `src/ansim_review/packaging/codex_bundle.py`; modify `AGENTS.md`; test `tests/integration/packaging/test_codex_bundle.py`.

- [ ] Test bundle contains AGENTS, five PDF skills, runtime code, evidence DB, approved rules, manifests, and validation command.
- [ ] Run and observe failure.
- [ ] Add question routing: retrieve evidence, run Math/Rule Engines, create Track A/B separately, finalize, show review packet, never decide.
- [ ] Export and smoke-test a copied bundle.
- [ ] Commit: `git commit -m "feat: package codex evidence review workspace"`.

### Task 5: ChatGPT Web Runtime ZIP

**Files:** Create `src/ansim_review/packaging/web_bundle.py`, `src/ansim_review/packaging/project_instructions.py`, `web_runtime/bootstrap.py`, `web_runtime/PROJECT_INSTRUCTIONS.md`; test `tests/integration/packaging/test_web_bundle.py`.

- [ ] Test extracted ZIP runs `python bootstrap.py --self-test` without installation and prints `WEB_RUNTIME_SELF_TEST_PASS`.
- [ ] Run and observe failure.
- [ ] Include standard-library runtime, evidence DB, approved rules, formula manifest, sample request, and exact command sequence; exclude unnecessary source PDFs by default.
- [ ] Build twice with sorted entries/fixed ZIP timestamps and assert identical SHA-256.
- [ ] Commit: `git commit -m "feat: export chatgpt web review runtime"`.

### Task 6: Workflow Documentation

**Files:** Create `docs/REVIEWER_WORKFLOW.md`, `docs/CODEX_WORKFLOW.md`, `docs/CHATGPT_WEB_WORKFLOW.md`; test `tests/integration/docs/test_documented_commands.py`.

- [ ] Write a test extracting fenced commands marked `smoke` and executing them against fixtures.
- [ ] Run and observe missing-doc failure.
- [ ] Document one ready case and one abstention case using only implemented commands.
- [ ] Run documented-command tests and scan wording for AI final-decision language.
- [ ] Commit: `git commit -m "docs: add codex web and reviewer workflows"`.
