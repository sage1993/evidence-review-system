# Remaining Integrity and Generic PDF Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete issues #19, #20, #22, #25, and #26 through six independently reviewable pull requests.

**Architecture:** Stabilize evidence identity first, then harden claim and offline boundaries, then align release attestation semantics, and finally complete parser/state genericization and the internal namespace migration. Each PR must produce working, independently testable software and must not rely on unmerged later PRs.

**Tech Stack:** Python 3.11 standard library, SQLite STRICT tables and FTS5, dataclasses, pathlib, hashlib, canonical JSON, pytest, Ruff, strict mypy.

## Global Constraints

- Runtime dependencies remain empty.
- Project code does not call external model, search, or document APIs.
- New artifacts use the `evidence-review/` format prefix.
- Machine output never contains a non-null human final decision.
- Source bytes, parser artifacts, rule versions, formula versions, and release inputs remain hash-addressed.
- Same normalized input produces byte-equivalent canonical JSON.
- Existing `ansim/*` artifacts are accepted only by explicitly named legacy readers.
- Every implementation PR follows red-green-refactor TDD and ends with the full quality gate.
- Do not combine the six implementation PRs into one branch.

---

## Ordered Pull Requests

| Order | Branch | Issue | Detailed plan |
|---:|---|---:|---|
| 1 | `agent/issue19-evidence-schema-v2` | #19 | `2026-08-02-evidence-schema-v2-migration.md` |
| 2A | `agent/issue25-track-a-numeric-grammar` | #25 | `2026-08-02-track-a-numeric-grammar.md` |
| 2B | `agent/issue26-offline-boundary` | #26 | `2026-08-02-offline-boundary-hardening.md` |
| 3 | `agent/issue20-process-attestation` | #20 | `2026-08-02-process-attestation.md` |
| 4A | `agent/issue22-parser-registry-state` | #22 | `2026-08-02-generic-parser-registry-state-model.md` |
| 4B | `agent/issue22-namespace-fixtures-e2e` | #22 | `2026-08-02-evidence-review-namespace-fixtures-e2e.md` |

## Dependency Rules

```text
PR 1 (#19)
  ├─> PR 2A (#25)
  └─> PR 2B (#26)
          └─> PR 3 (#20)
PR 1 + PR 2A + PR 2B + PR 3
          └─> PR 4A (#22)
                  └─> PR 4B (#22)
```

- PR 2A and PR 2B may be developed in parallel after PR 1 merges.
- PR 3 must consume the assurance vocabulary introduced by PR 2B.
- PR 4A must target a `main` that already contains PRs 1–3.
- PR 4B is the only PR allowed to rename the canonical Python package.

## Branch Preparation

For every implementation PR:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git worktree add ../evidence-review-<short-name> -b <branch> origin/main
```

Do not reuse the design branch for code implementation.

## Common Verification Gate

Every PR must run:

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

Expected result:

```text
pytest: all tests passed
ruff: All checks passed
mypy: Success: no issues found
compileall: exit code 0
```

## PR Review Gates

Before requesting merge:

- [ ] The detailed plan task checklist is complete.
- [ ] Focused regression tests fail on the parent commit and pass on the branch.
- [ ] Full quality gate passes on the PR head.
- [ ] New JSON output is canonical and byte-reproducible.
- [ ] Documentation describes the implemented assurance level without stronger claims.
- [ ] The PR body names the exact issue it closes or advances.
- [ ] No unrelated refactoring is included.

## Final Epic Closure Gate

Issue #22 may close only after PR 4B proves all of the following:

```text
arbitrary names + different bytes       -> distinct source identity
same bytes + different names            -> deduplicated source identity
different supported parser adapters     -> registry dispatch
missing parser artifact                  -> explicit pending state
visual evidence                          -> explicit document/revision/page identity
new artifacts and user-facing docs       -> no ansim identifier
legacy artifacts                         -> read-only explicit compatibility path
full generic fixture matrix              -> passing end-to-end tests
```

## Execution Handoff

Recommended execution mode:

```text
superpowers:subagent-driven-development
```

Use one fresh implementation subagent per task, followed by specification review and code-quality review before moving to the next task.