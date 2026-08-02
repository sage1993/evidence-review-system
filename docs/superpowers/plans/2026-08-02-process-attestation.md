# Named Reviewer Process Attestation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the misleading legacy `signature` acceptance field with a strict named-reviewer process attestation whose guarantees and release status are explicit.

**Architecture:** Define a new `evidence-review/human-attestation` contract, validate exact release-candidate and packet hashes plus required checklist evidence, and report `PROCESS_ATTESTATION` with cryptographic identity verification explicitly false. Legacy `ansim/human-acceptance` records remain inspectable but cannot authorize a new release. The release gate is implemented in `release/builder.py`, which is the current authority for `BLOCKED` and `RELEASE_READY`.

**Tech Stack:** Python 3.11 standard library, dataclasses, pathlib, canonical JSON, JSON Schema, pytest.

## Global Constraints

- Runtime dependencies remain empty.
- No cryptographic signing, reviewer key registry, or identity authentication is added.
- Candidate and packet hashes must exactly match the current release artifacts.
- Attestation records are append-only and never overwritten.
- Missing, malformed, stale, legacy, or mismatched records keep the release `BLOCKED`.
- New canonical documentation and artifacts do not describe the attestation as an electronic signature.
- Offline assurance and human process assurance remain separate fields.

---

### Task 1: Strict schema and decoder

**Files:**
- Create: `schemas/human-attestation.schema.json`
- Create: `src/ansim_review/release/attestation.py`
- Create: `tests/unit/release/test_attestation.py`
- Modify: `src/ansim_review/contracts/formats.py`
- Modify: `tests/unit/contracts/test_schema_documents.py`

- [ ] Add RED tests for exact fields, format/version constants, assurance level, fixed statement, reviewer ID, timezone-aware timestamp, lowercase SHA-256, required checks, duplicate checks, unknown fields, and removal of `signature`.
- [ ] Confirm focused tests fail because the new contract does not exist.
- [ ] Implement immutable dataclasses, strict decoder, canonical document, and JSON Schema.
- [ ] Confirm focused tests pass.

### Task 2: Exact hash validation and append-only writer

**Files:**
- Modify: `src/ansim_review/release/attestation.py`
- Modify: `tests/unit/release/test_attestation.py`

- [ ] Add RED tests for one-character candidate/packet hash changes, failed checks, deterministic check order, canonical bytes, returned SHA-256, and overwrite refusal.
- [ ] Implement `validate_attestation()` and `write_attestation()` using exclusive binary creation.
- [ ] Confirm focused tests pass.

### Task 3: Legacy inspection boundary

**Files:**
- Create: `src/ansim_review/release/legacy_acceptance.py`
- Modify: `src/ansim_review/release/acceptance.py`
- Create: `tests/unit/release/test_legacy_acceptance.py`

- [ ] Add RED tests proving legacy records are inspectable as `LEGACY_UNVERIFIED_ACCEPTANCE` and cannot authorize a release.
- [ ] Move old decoding to inspection-only code.
- [ ] Make the old validation entrypoint fail closed with migration guidance.

### Task 4: Release builder gate

**Files:**
- Modify: `src/ansim_review/release/config.py`
- Modify: `src/ansim_review/release/builder.py`
- Modify: `tests/integration/release/test_acceptance_record.py`
- Modify: `tests/integration/release/test_release_builder.py`

- [ ] Rename canonical configuration from acceptance record to attestation record while preserving a compatibility property only where required.
- [ ] Remove legacy release-directory fallback from authorization.
- [ ] Add RED cases for missing, malformed, stale, legacy, and valid attestation records.
- [ ] Require automated validation and valid attestation for `RELEASE_READY`.
- [ ] Emit `attestation_assurance: PROCESS_ATTESTATION` and `cryptographic_identity_verified: false`.
- [ ] Copy only a validated canonical attestation into the release output.

### Task 5: CLI and documentation

**Files:**
- Modify: `src/ansim_review/cli.py`
- Modify: `README.md`
- Modify: `docs/REVIEWER_WORKFLOW.md`
- Modify: `docs/OFFLINE_ASSURANCE.md`
- Create or modify documentation contract tests.

- [ ] Add `release validate-attestation` with canonical status output.
- [ ] State that possession of the JSON record is not cryptographic proof of reviewer identity.
- [ ] Document candidate hash, packet hash, checklist, and append-only procedure.
- [ ] Keep legacy terminology only in explicitly labeled compatibility sections.

### Task 6: Full verification and PR

- [ ] Run release unit and integration tests.
- [ ] Run full pytest, Ruff, strict mypy, compileall, Python 3.11 wheel, and Python 3.13 wheel gates.
- [ ] Search canonical source and docs for misleading signature terminology.
- [ ] Open a PR with RED/GREEN evidence and `Closes #20` only after all gates pass.
