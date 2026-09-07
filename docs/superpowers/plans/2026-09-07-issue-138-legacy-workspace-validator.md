# Issue #138 Legacy Workspace Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove ambiguity around `scripts/validate_workspace.py` by explicitly retiring it as a current validation gate while preserving the legacy ANSIM/Grist validator under a clearly legacy name.

**Architecture:** Keep the current release authority unchanged: `scripts/validate_release.py` and `scripts/build_release.py` remain the supported current release gates. Move the legacy validation logic to `scripts/validate_legacy_ansim_workspace.py`; retain `scripts/validate_workspace.py` only as a fail-closed retirement entrypoint that exits nonzero and directs operators to the canonical current gates or the explicitly legacy script.

**Tech Stack:** Python 3.13, pytest, Ruff, mypy, compileall.

**Spec:** GitHub Issue #138 — `P2: Retire or replace legacy validate_workspace.py with the current validation contract`

## Global Constraints

- Do not replace `scripts/validate_release.py` / `scripts/build_release.py` as the current release validation authority.
- Preserve the legacy ANSIM/Grist validation behavior for explicit legacy use only.
- `scripts/validate_workspace.py` must no longer be capable of producing a misleading PASS for the retired layout.
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

- [ ] **Step 1: Write failing entrypoint tests**

Test that `scripts/validate_workspace.py` exits nonzero and names both `scripts/validate_release.py` and `scripts/validate_legacy_ansim_workspace.py`, while the explicit legacy script remains present and retains the legacy Grist markers.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
py -3.13 -m pytest -q tests/unit/test_validate_workspace_entrypoints.py
```

Expected: FAIL because the ambiguous entrypoint still contains the legacy validator and the explicit legacy script does not yet exist.

- [ ] **Step 3: Implement the minimum split**

Move the existing legacy validation logic unchanged except for a legacy-identifying module docstring into `scripts/validate_legacy_ansim_workspace.py`. Replace `scripts/validate_workspace.py` with a small command-line entrypoint that prints an error explaining that the validator was retired and exits with code 2.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the same focused pytest command and require PASS.

---

### Task 2: Make current validation authority unambiguous in documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/MANUAL_ACCEPTANCE_POLICY.md`
- Test: `tests/unit/test_validate_workspace_entrypoints.py`

**Interfaces:**
- Consumes: Task 1 entrypoint names.
- Produces: explicit documentation that current release validation uses `validate_release.py` / `build_release.py` and that the legacy validator is not a current release gate.

- [ ] **Step 1: Add failing documentation assertions**

Require current documentation to name the canonical current release scripts and identify `validate_legacy_ansim_workspace.py` as legacy-only.

- [ ] **Step 2: Run focused tests and verify RED**

Expected: FAIL until documentation is updated.

- [ ] **Step 3: Update documentation minimally**

Add one concise validation-authority section without changing unrelated release policy.

- [ ] **Step 4: Run focused tests and verify GREEN**

Require the focused suite to pass.

---

### Task 3: Verification and integration

**Files:**
- All Issue #138 files above only.

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

Confirm only the plan, two validator entrypoints, focused test, and minimal documentation edits changed.

- [ ] **Step 4: Commit, push, and PR only after required gates are PASS**

Use the dedicated Issue #138 branch based on current `main`; do not add a GitHub Actions workflow.
