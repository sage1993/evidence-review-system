# Final Release Output Verifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reopen final Codex and ChatGPT runtime ZIP artifacts, compare their internal manifests against actual member bytes, and block release authorization on any output mismatch.

**Architecture:** Add a standard-library-only `release/output_verifier.py` boundary that never extracts ZIP files. It validates canonical POSIX member paths, duplicate and case-colliding names, strict manifest structure, exact member sets, sizes, and SHA-256 values. The release builder runs this verification after creating the five deterministic candidate artifacts but before writing `release-validation.json`, calculating the candidate hash, or validating process attestation.

**Tech Stack:** Python 3.11 standard library, `zipfile`, `hashlib`, `json`, `pathlib`, pytest.

## Global Constraints

- Runtime dependencies remain empty.
- ZIP files are never extracted to the filesystem.
- ZIP data is read through each unique `ZipInfo`, never by an ambiguous duplicate name lookup.
- Only canonical relative POSIX file paths are accepted.
- Absolute paths, drive-prefixed paths, backslashes, empty components, `.` and `..` are rejected.
- Case-fold collisions are rejected for Windows portability.
- The internal manifest file is excluded from its own `files` collection.
- Errors are deterministic and sorted.
- Output verification runs before candidate hash calculation and process-attestation validation.
- Any output-verification failure produces `RELEASE_OUTPUT_VALIDATION_FAILED` and keeps the release `BLOCKED`.

---

### Task 1: Canonical output and ZIP path validation

**Files:**
- Create: `src/ansim_review/release/output_verifier.py`
- Create: `tests/unit/release/test_output_verifier.py`
- Modify: `src/ansim_review/contracts/formats.py`

**Interfaces:**
- Produces: `validate_release_output(output_directory: Path) -> dict[str, object]`
- Produces: report format `evidence-review/release-output-validation` version 1.
- Candidate files before validation: `evidence.sqlite`, `approved-rules.zip`, `codex-workspace.zip`, `chatgpt-web-runtime.zip`, `final-review-packet.json`.

- [ ] Add RED tests proving missing and unexpected output files fail with stable error codes.
- [ ] Add RED tests proving absolute, parent, current-directory, backslash, drive-prefixed, empty-component, duplicate, and case-colliding ZIP paths fail before manifest trust.
- [ ] Run `pytest tests/unit/release/test_output_verifier.py -v` and confirm collection fails because `output_verifier` does not exist.
- [ ] Implement canonical member-path validation and exact candidate output-file-set validation.
- [ ] Re-run focused tests and confirm path/output tests pass.

### Task 2: Internal manifest and actual-byte verification

**Files:**
- Modify: `src/ansim_review/release/output_verifier.py`
- Modify: `tests/unit/release/test_output_verifier.py`

**Interfaces:**
- Consumes: one ZIP path, one manifest filename, and one expected format.
- Produces: per-archive report containing archive name, manifest name, status, member count, and deterministic errors.

- [ ] Add RED tests for missing or duplicate manifest members, invalid JSON, wrong format/version, invalid `files`, and invalid manifest entries.
- [ ] Add RED tests for manifest duplicate paths and case-fold collisions.
- [ ] Add RED tests for missing declared files, undeclared archive files, size mismatch, and SHA-256 mismatch.
- [ ] Add a passing Codex fixture using `bundle-manifest.json` and a passing web fixture using `runtime-manifest.json`.
- [ ] Run focused tests and confirm they fail on missing manifest verification behavior.
- [ ] Implement strict manifest decoding and `ZipInfo`-bound byte comparison.
- [ ] Run focused tests and confirm all archive cases pass.

### Task 3: Release builder gate integration

**Files:**
- Modify: `src/ansim_review/release/builder.py`
- Modify: `tests/integration/release/test_release_builder.py`
- Create: `tests/unit/release/test_release_output_gate.py`

**Interfaces:**
- Consumes: workspace validation report and release-output validation report.
- Produces: combined `release-validation.json` with `release_output` section.
- Produces: `RELEASE_OUTPUT_VALIDATION_FAILED` release reason when output status is not `PASS`.

- [ ] Add RED tests for deterministic gate reasons: workspace-only failure, output-only failure, and both failures.
- [ ] Add RED integration assertions that a normal release includes a passing `release_output` report with both archives.
- [ ] Run focused tests and confirm the new report and reason-code behavior are absent.
- [ ] Integrate `validate_release_output()` after the five candidate artifacts are built and before `release-validation.json` is written.
- [ ] Preserve `AUTOMATED_VALIDATION_FAILED` for workspace validation and add the separate output reason code.
- [ ] Write the combined validation report canonically, then calculate candidate hash and validate process attestation.
- [ ] Run release unit and integration tests and confirm all pass.

### Task 4: Documentation and full verification

**Files:**
- Modify: `README.md`
- Modify: `docs/OFFLINE_EXECUTION.md`
- Create: `tests/unit/release/test_output_verifier_documentation.py`

**Interfaces:**
- Documents: verified archives, error classes, no-extraction boundary, case-collision behavior, and release blocking semantics.

- [ ] Add RED documentation-contract tests for `bundle-manifest.json`, `runtime-manifest.json`, `RELEASE_OUTPUT_VALIDATION_FAILED`, no extraction, and case-fold collision language.
- [ ] Update user and offline-boundary documentation.
- [ ] Run documentation tests and confirm pass.
- [ ] Run `pytest -v`.
- [ ] Run `ruff check src tests`.
- [ ] Run `mypy src`.
- [ ] Run `python -m compileall -q src scripts web_runtime tests`.
- [ ] Confirm Python 3.11 and 3.13 wheel checks and Windows/Ubuntu CI pass.
- [ ] Open a PR with RED/GREEN evidence and `Closes #42` only after all gates pass.
