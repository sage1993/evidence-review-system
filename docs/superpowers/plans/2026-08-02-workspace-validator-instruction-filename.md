# Workspace Validator Instruction Filename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `scripts/validate_workspace.py` require only the canonical root instruction file `AGENTS.md`, report a stable missing-file code, and enforce the same exact-case filename policy on Linux and Windows.

**Architecture:** Extract the required-file policy into focused functions inside the existing validator script, preserve the existing JSON `errors` field for compatibility, and add structured `error_details` records for stable machine handling. Test the script against isolated temporary workspace fixtures and run the focused tests on Ubuntu and Windows GitHub Actions runners.

**Tech Stack:** Python 3.11+, `pytest`, `sqlite3`, GitHub Actions.

## Global Constraints

- `AGENTS.md` is the only canonical repository instruction filename.
- `agent.md`, `agents.md`, and other case variants do not satisfy the requirement.
- Existing human-readable `errors` output remains available.
- Missing required files expose the stable code `MISSING_REQUIRED_FILE` and a POSIX-style relative path.
- The validator remains directly executable with `python scripts/validate_workspace.py`.
- No unrelated Grist validation behavior is changed.

---

### Task 1: Reproduce the incorrect legacy filename requirement

**Files:**
- Create: `tests/integration/test_workspace_validator.py`
- Test: `scripts/validate_workspace.py`

**Interfaces:**
- Consumes: validator JSON written to stdout.
- Produces: regression tests proving `AGENTS.md` is accepted without `agent.md` and exact-case matching is required.

- [ ] Write a temporary valid legacy workspace fixture with `AGENTS.md` but no `agent.md`.
- [ ] Run the existing validator from the fixture and assert it does not report `missing: agent.md`.
- [ ] Run the focused test and confirm it fails against current `main` for the expected reason.
- [ ] Commit the RED test as `test: reproduce workspace instruction filename mismatch`.

### Task 2: Implement the canonical instruction policy

**Files:**
- Modify: `scripts/validate_workspace.py`
- Test: `tests/integration/test_workspace_validator.py`

**Interfaces:**
- Produces: `required_workspace_paths(root: Path) -> tuple[Path, ...]`.
- Produces: `missing_required_files(root: Path) -> tuple[str, ...]` using exact directory-entry names.
- Produces: JSON `error_details` entries shaped as `{"code": "MISSING_REQUIRED_FILE", "path": "AGENTS.md"}`.

- [ ] Replace the duplicate `agent.md`/`AGENTS.md` requirement with `AGENTS.md` only.
- [ ] Add exact-case existence checking so Windows does not accept `agents.md` for `AGENTS.md`.
- [ ] Preserve `errors` strings while adding stable structured `error_details`.
- [ ] Add `main()` and a `__main__` guard so the validation helpers can be imported without executing the script.
- [ ] Run the focused tests and confirm they pass.
- [ ] Commit as `fix: align workspace validator instruction filename`.

### Task 3: Verify Linux and Windows behavior

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/integration/test_workspace_validator.py`

**Interfaces:**
- Consumes: focused pytest file.
- Produces: dedicated Ubuntu and Windows workflow coverage.

- [ ] Add tests for exact `AGENTS.md`, legacy `agent.md`, and lowercase `agents.md` fixtures.
- [ ] Add a small `workspace-validator-platforms` matrix job for `ubuntu-latest` and `windows-latest`.
- [ ] Run or observe focused CI on both platforms.
- [ ] Run full `pytest`, Ruff, strict mypy, and compileall verification.
- [ ] Commit as `ci: verify workspace validator across platforms`.

### Task 4: Completion and issue linkage

**Files:**
- Modify: GitHub issue #39 through a completion comment.
- Create: pull request from `agent/issue39-workspace-validator-instruction` to `main`.

- [ ] Record the RED failure and GREEN verification results.
- [ ] Open a pull request with `Closes #39` only after both platform jobs pass.
- [ ] Confirm no unrelated files changed.
