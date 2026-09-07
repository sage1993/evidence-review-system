# Issue #138 Legacy Workspace Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove ambiguity around `scripts/validate_workspace.py` by explicitly retiring it as a current validation gate while preserving the legacy ANSIM/Grist validator under a clearly legacy name.

**Architecture:** Keep the current release authority unchanged: `scripts/validate_release.py` and `scripts/build_release.py` remain the supported current release gates. Move the legacy validation logic to `scripts/validate_legacy_ansim_workspace.py`; retain `scripts/validate_workspace.py` only as a fail-closed retirement entrypoint that exits nonzero and directs operators to the canonical current gates or the explicitly legacy script. Historical Superpowers implementation plans remain intact as execution records, while their stale validator command examples are explicitly superseded by the current manual-acceptance policy.

**Tech Stack:** Python 3.13, pytest, Ruff, mypy, compileall.

**Spec:** GitHub Issue #138 — `P2: Retire or replace legacy validate_workspace.py with the current validation contract`

## Global Constraints

- Do not replace `scripts/validate_release.py` / `scripts/build_release.py` as the current release validation authority.
- Current command contracts are `py -3.13 scripts/validate_release.py <workspace>` and `py -3.13 scripts/build_release.py <workspace> <output-dir>`.
- Preserve the legacy ANSIM/Grist validation behavior for explicit legacy use only.
- `scripts/validate_workspace.py` must no longer be capable of producing a misleading PASS for the retired layout.
- Historical implementation plans are not rewritten solely to update old command examples; the plans index must explicitly supersede those examples with the current policy.
- No production package behavior or evidence-review contracts change.
- GitHub Actions remain out of scope.

---

### Task 1: Retire the ambiguous entrypoint and preserve explicit legacy validation

**Files:**
- Create: `scripts/validate_legacy_ansim_workspace.py`
- Modify: `scripts/validate_workspace.py`
- Create: `tests/unit/test_validate_workspace_entrypoints.py`

**Interfaces:**
- Consumes: current legacy validator behavior from `scripts/validate_workspace.py`.
- Produces: a fail-closed retired entrypoint and an explicit legacy validator entrypoint.

- [x] **Step 1: Write failing entrypoint tests**

Test that `scripts/validate_workspace.py` exits nonzero and names `scripts/validate_release.py`, `scripts/build_release.py`, and `scripts/validate_legacy_ansim_workspace.py`, while the explicit legacy script remains present and retains the legacy Grist markers.

- [x] **Step 2: Run focused tests and verify RED**

Run:

```powershell
py -3.13 -m pytest -q tests/unit/test_validate_workspace_entrypoints.py
```

Observed RED: the ambiguous entrypoint returned the legacy validator result instead of retirement exit code 2, and the explicit legacy script did not exist.

- [x] **Step 3: Implement the minimum split**

Move the existing legacy validation logic unchanged except for a legacy-identifying module docstring into `scripts/validate_legacy_ansim_workspace.py`. Replace `scripts/validate_workspace.py` with a small command-line entrypoint that explains retirement, identifies the current release commands, and exits with code 2.

- [x] **Step 4: Run focused tests and verify GREEN**

The focused entrypoint contract changed from RED to GREEN before the documentation contract was added.

---

### Task 2: Make current validation authority unambiguous in documentation

**Files:**
- Modify: `docs/MANUAL_ACCEPTANCE_POLICY.md`
- Modify: `docs/superpowers/plans/README.md`
- Test: `tests/unit/test_validate_workspace_entrypoints.py`

**Interfaces:**
- Consumes: Task 1 entrypoint names and current release CLI signatures.
- Produces: explicit documentation that current release validation uses `validate_release.py` / `build_release.py`, that the legacy validator is not a current release gate, and that historical implementation-plan command examples are superseded by current policy.

- [x] **Step 1: Add failing documentation assertions**

Require the current manual policy to name the canonical current release scripts and identify `validate_legacy_ansim_workspace.py` as legacy-only. Require the plans index to identify historical plan commands as non-current authority.

- [x] **Step 2: Run focused tests and verify RED**

Observed RED: the entrypoint tests passed while the new documentation-authority assertion failed.

- [x] **Step 3: Update documentation minimally**

Add the current/legacy validation-authority section to `docs/MANUAL_ACCEPTANCE_POLICY.md` and a supersession notice to `docs/superpowers/plans/README.md`. Preserve the historical stabilization plan itself rather than rewriting its execution record.

- [ ] **Step 4: Run focused tests and verify final GREEN**

Require the final focused suite to pass after the deterministic legacy-fixture test and exact `<output-dir>` command contract are applied.

---

### Task 3: Verification and integration

**Files:**
- `scripts/validate_workspace.py`
- `scripts/validate_legacy_ansim_workspace.py`
- `tests/unit/test_validate_workspace_entrypoints.py`
- `docs/MANUAL_ACCEPTANCE_POLICY.md`
- `docs/superpowers/plans/README.md`
- `docs/superpowers/plans/2026-09-07-issue-138-legacy-workspace-validator.md`

- [ ] **Step 1: Run focused tests**

```powershell
py -3.13 -m pytest -q tests/unit/test_validate_workspace_entrypoints.py
```

- [ ] **Step 2: Run full required verification**

```powershell
py -3.13 -m pytest -q
py -3.13 -m ruff check .
py -3.13 -m mypy src
py -3.13 -m compileall -q src tests scripts
git diff --check
```

Every unexecuted command must be reported as `NOT_RUN`; do not infer PASS.

- [ ] **Step 3: Scope audit**

Confirm only the six Issue #138 files listed above differ from `main`.

- [ ] **Step 4: Publish for review only after evidence is classified correctly**

If all required gates are freshly available and PASS, create a normal PR. If the GitHub-only execution environment cannot run the full repository verification matrix, create a draft PR and report the missing gates as `NOT_RUN`; do not claim merge readiness and do not add a GitHub Actions workflow.
