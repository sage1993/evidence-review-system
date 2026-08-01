# End-to-End Validation and Ansim Housing Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the current Ansim Housing PDF/Grist workspace, prove deterministic behavior across Codex and ChatGPT web packages, and establish the production-review release gate.

**Architecture:** Migration is additive and source-preserving. Golden question cases exercise retrieval, calculations, rules, citations, Track A/B, confidence, abstention, rendering, and human handoff. Deterministic artifacts are compared byte-for-byte across runtimes.

**Tech Stack:** Python 3.11+, pytest, SQLite, SHA-256 manifests, zipfile, current PDF/Grist/CSV/visual workspace.

## Global Constraints

- Do not declare overall PASS without automated validation and human Grist/HTML acceptance.
- Preserve original `안심주택DB.grist` and all source/parser files.
- LLM prose is schema-validated but excluded from byte-equivalence comparison; deterministic artifacts must match exactly.
- Release files include manifests, hashes, validation report, and signed acceptance record.

---

### Task 1: Source Inventory and Backup

**Files:** Create `scripts/migrate_ansim_workspace.py`; test `tests/integration/migration/test_ansim_migration.py`.

- [ ] Test tree hashes under `02_source_pdf/` are identical before and after migration.
- [ ] Run and observe missing script failure.
- [ ] Create dated Grist/source backups and `migration/source-inventory.json` with counts/hashes for PDFs, parser outputs, images, tables, clauses, and exports.
- [ ] Run migration test.
- [ ] Commit: `git commit -m "feat: inventory and protect ansim source workspace"`.

### Task 2: Evidence Migration and Reviewed-Field Preservation

**Files:** Modify `scripts/migrate_ansim_workspace.py`; test `tests/integration/migration/test_ansim_review_preservation.py`.

- [ ] Test a human-reviewed normalized value survives an identical rebuild.
- [ ] Run and observe failure.
- [ ] Merge by stable source identity; on source revision change preserve old record and create `SOURCE_REVISION_REVIEW_REQUIRED` rather than copying reviewed status.
- [ ] Produce `evidence/ansim-evidence.sqlite` and `migration/unresolved-links.json`.
- [ ] Commit: `git commit -m "feat: preserve human-reviewed ansim data"`.

### Task 3: Golden Question Cases

**Files:** Create `tests/golden/questions/ansim_cases.json`, `tests/integration/golden/test_golden_question_runs.py`, and `tests/golden/runs/`.

**Cases:** direct source lookup; ratio below threshold; equality at 1/8; missing perimeter; exception retrieval; source conflict; uncited claim; Track B rejection; low-confidence parse; null human decision.

- [ ] Define expected retrieval IDs, calculation result, rule status, confidence factors, abstention reasons, and final status before orchestration fixes.
- [ ] Run and observe failures.
- [ ] Fix the owning subsystem only; never change expected output to hide a defect.
- [ ] Run twice and compare deterministic JSON bytes.
- [ ] Commit: `git commit -m "test: add ansim evidence review golden cases"`.

### Task 4: Cross-Runtime Equivalence

**Files:** Create `tests/integration/packaging/test_cross_runtime_equivalence.py`; modify `src/ansim_review/packaging/web_bundle.py`.

- [ ] Test local and extracted web runtime outputs match for query, math, rules, confidence, abstention, and final packet deterministic fields.
- [ ] Run and observe failure.
- [ ] Remove absolute paths, process IDs, current timestamps, and temp directories from canonical outputs; retain them only in non-canonical logs.
- [ ] Run on Windows-compatible and POSIX fixture paths.
- [ ] Commit: `git commit -m "test: verify cross-runtime deterministic equivalence"`.

### Task 5: No-Network and Reproducible Build Audit

**Files:** Create `scripts/validate_release.py`; test `tests/integration/release/test_no_network_runtime.py`.

- [ ] Test every deterministic command succeeds with outbound sockets blocked.
- [ ] Run and identify hidden assumptions.
- [ ] Add forbidden-import scan, manifest verification, foreign-key/integrity checks, and double-build ZIP hash comparison.
- [ ] Run validator and save canonical `release-validation.json`.
- [ ] Commit: `git commit -m "test: enforce offline reproducible runtime"`.

### Task 6: Human Acceptance

**Files:** Create `docs/acceptance/ANSIM_ACCEPTANCE_CHECKLIST.md`.

- [ ] Define exact checks: 10 clause-to-PDF samples, 10 bbox overlays, 5 table crops, Grist thumbnails, readable references/no `Invalid column`, evidence/calculation/confidence display, blank decision, visible abstention reason.
- [ ] Execute with a named human reviewer and record file/screenshot references.
- [ ] Fix failures through the owning subsystem and repeat affected checks.
- [ ] Create signed `releases/ansim-v1.0/acceptance-record.json` linked to packet/release hashes.
- [ ] Commit: `git commit -m "docs: record ansim reviewer acceptance"`.

### Task 7: Release Builder and Final Gate

**Files:** Create `scripts/build_ansim_release.py`, `releases/ansim-v1.0/README.md`; test `tests/integration/release/test_release_builder.py`.

- [ ] Test release is `BLOCKED/MANUAL_ACCEPTANCE_MISSING` without a signed acceptance record.
- [ ] Run and observe failure.
- [ ] Build `ansim-codex-workspace.zip`, `ansim-chatgpt-web-runtime.zip`, evidence DB, approved-rule archive, release manifest, validation report, and acceptance record by hash.
- [ ] Run `pytest -v`, ruff, mypy, release validator, and release builder; expect `RELEASE_READY` only after all gates pass.
- [ ] Commit and tag: `git commit -m "feat: build validated ansim review release" && git tag ansim-v1.0`.
