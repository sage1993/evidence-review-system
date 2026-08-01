# Remaining Integrity and Generic PDF Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete issues #19, #20, #22, #25, and #26 through six independently reviewable pull requests.

**Architecture:** Stabilize evidence identity first, then harden claim and offline boundaries, then align release attestation semantics, and finally complete parser/state genericization and the internal namespace migration. Each PR must produce working, independently testable software and must not rely on unmerged later PRs.

**Tech Stack:** Python 3.11 standard library, SQLite STRICT tables and FTS5, dataclasses, pathlib, hashlib, canonical JSON, pytest, Ruff, strict mypy.

**Reviewed main:** `09f6209ccdcb81dad3a14d32a8efb5165dd723b7`

## Global Constraints

- Runtime dependencies remain empty.
- Project code does not call external model, search, or document APIs.
- New artifacts use the `evidence-review/` format prefix.
- Machine output never contains a non-null human final decision.
- Source bytes, parser artifacts, rule versions, formula versions, release inputs, drawing candidates, and drawing confirmations remain hash-addressed.
- Same normalized input produces byte-equivalent canonical JSON.
- Existing `ansim/*` artifacts are accepted only by explicitly named legacy readers.
- Every implementation PR follows red-green-refactor TDD and ends with the full quality gate.
- Do not combine the six implementation PRs into one branch.
- Preserve PR #29 candidate-provenance binding and `ACCEPTED`/`EDITED` semantics.

---

## Completed prerequisite

PR #29 was merged before execution of this roadmap:

```text
09f6209ccdcb81dad3a14d32a8efb5165dd723b7
fix: reverify drawing candidate provenance
```

The detailed correction document below is authoritative where it conflicts with the earlier #22 plans:

```text
docs/superpowers/plans/2026-08-02-drawing-backend-plan-corrections.md
```

## Ordered Pull Requests

| Order | Branch | Issue | Detailed plan |
|---:|---|---:|---|
| 1 | `agent/issue19-evidence-schema-v2` | #19 | `2026-08-02-evidence-schema-v2-migration.md` |
| 2A | `agent/issue25-track-a-numeric-grammar` | #25 | `2026-08-02-track-a-numeric-grammar.md` |
| 2B | `agent/issue26-offline-boundary` | #26 | `2026-08-02-offline-boundary-hardening.md` |
| 3 | `agent/issue20-process-attestation` | #20 | `2026-08-02-process-attestation.md` |
| 4A | `agent/issue22-parser-registry-state` | #22 | `2026-08-02-generic-parser-registry-state-model.md` plus correction document |
| 4B | `agent/issue22-namespace-fixtures-e2e` | #22 | `2026-08-02-evidence-review-namespace-fixtures-e2e.md` plus correction document |

## Dependency Rules

```text
PR #29 drawing provenance hotfix
          ↓
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
- `DRAWING_BACKEND_ONLY` remains a source-routing result; drawing workflow remains owned by `drawing_workflow.py`.

## Plan Self-Review Corrections

The detailed plans were checked against the current `main` tree. The following test modules do not exist yet and must be treated as **Create**, even where a task table says `Modify`:

```text
tests/unit/evidence/test_store.py
tests/unit/evidence/test_ingest.py
tests/unit/evidence/test_snapshot.py
tests/integration/retrieval/test_index.py
tests/unit/llm_layer/test_track_a_templates.py
tests/integration/release/test_release_validator.py
tests/unit/test_documentation_contracts.py
```

The following modules were confirmed to exist and are modified in place:

```text
tests/unit/test_network_guard.py
tests/unit/parsing/test_odl_adapter.py
tests/integration/release/test_acceptance_record.py
tests/unit/llm_layer/test_track_a_validator.py
```

When this correction table conflicts with a per-task `Create/Modify` label, this table is authoritative. Exact production interfaces, test behavior, and commit boundaries in the detailed plans remain unchanged except where the drawing-backend correction document explicitly supersedes them.

### Spec coverage check

| Spec requirement | Implementing plan/task |
|---|---|
| authoritative `page_id`, table/visual FK, bbox rejection | Schema v2 Tasks 2–5 |
| copy-on-write versioned migration | Schema v2 Tasks 1, 6, 7 |
| unsupported numeric syntax cannot bypass validation | Numeric grammar Tasks 1–4 |
| one offline policy, TCP/UDP/subprocess boundary | Offline Tasks 1–5 |
| application guard vs OS isolation wording | Offline Tasks 4, 6 |
| internal process attestation, no signature claim | Attestation Tasks 1–6 |
| candidate and packet hashes gate release | Attestation Tasks 2, 5 |
| parser registry and source status model | Parser/state Tasks 1–6 plus drawing correction |
| explicit visual document/revision/page identity | Parser/state Task 7 |
| drawing source/candidate/confirmation authority separation | Drawing correction Sections 1–3 |
| canonical `evidence_review` namespace | Namespace Task 2 plus drawing correction Section 4 |
| legacy compatibility isolation | Namespace Tasks 3, 5, 6 |
| varied PDF fixture matrix and E2E | Namespace Tasks 7–9 plus drawing correction Section 4.2 |

### Placeholder and type-consistency check

- No `TBD`, `TODO`, “implement later,” or unspecified test steps remain.
- `ParserRegistry.require(kind) -> ParserAdapter` is consistent between registry and importer plans.
- `NormalizedParserContribution` is the sole adapter-to-importer payload.
- `validate_bbox_within_page()` from the schema-v2 plan is reused by parser models and migration.
- `PROCESS_ATTESTATION` and `cryptographic_identity_verified=false` are consistent between attestation, release validation, and documentation plans.
- `APPLICATION_OFFLINE_GUARD` and `OS_ISOLATED` are consistent between policy code, release reports, and documentation.
- `bind_confirmed_inputs(..., candidate_entries=...)` is preserved through parser/state and namespace migration.
- `ACCEPTED` never carries replacement value, unit, or geometry; `EDITED` is required for changes.

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
- [ ] Drawing engine binding still revalidates source, candidate, and confirmation artifacts.
- [ ] The PR body names the exact issue it closes or advances.
- [ ] No unrelated refactoring is included.

## Final Epic Closure Gate

Issue #22 may close only after PR 4B proves all of the following:

```text
arbitrary names + different bytes       -> distinct source identity
same bytes + different names            -> deduplicated source identity
different supported parser adapters     -> registry dispatch
missing parser artifact                  -> explicit pending state
parserless CASE_DRAWING                  -> DRAWING_BACKEND_ONLY
drawing workflow                         -> existing drawing backend projection
candidate tampering                      -> engine binding blocked
ACCEPTED replacement data                -> rejected
visual evidence                          -> explicit document/revision/page identity
new artifacts and user-facing docs       -> no ansim identifier
legacy artifacts                         -> read-only explicit compatibility path
full generic fixture matrix              -> passing end-to-end tests
```

## Execution Handoff

Selected execution mode:

```text
superpowers:executing-plans
```

Execute one implementation PR at a time with a review checkpoint after each PR. Do not start a dependent PR until its required parent PR is merged and verified on `main`.
