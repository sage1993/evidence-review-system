# Evidence-First Regulatory Review System Master Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an API-free deterministic evidence, calculation, rule, retrieval, audit, and reviewer-packet runtime for Codex Desktop and ChatGPT web.

**Architecture:** A Python core owns source provenance, SQLite evidence, Decimal calculations, versioned JSON rules, retrieval, citation validation, confidence, and abstention. LLM passes create explanation and audit files only; a deterministic finalizer controls delivery and leaves the human decision empty.

**Tech Stack:** Python 3.11+, standard-library runtime, SQLite FTS5, PyMuPDF/OpenDataLoader only for Codex-side ingestion, pytest/ruff/mypy for development, self-contained HTML and ZIP exports.

## Global Constraints

- No API client, HTTP model call, or remote search in project code.
- LLMs never calculate, evaluate rules, assign confidence, or set the human decision.
- Every factual claim must have a resolved document/page citation.
- Original PDFs, raw parser output, coordinates, source hashes, and reviewed values are immutable evidence.
- Identical evidence/rule/formula versions and inputs produce byte-equivalent canonical engine JSON.
- The GPT web runtime core is standard-library-only and requires no installation.
- Grist remains a human maintenance surface; it is not the execution engine.
- Review Packet v1 is frozen and remains byte-compatible.
- Browser review, drawing ingestion, and Codex orchestration must consume shared contracts rather than define duplicate schemas or enums.
- Case drawings remain separate from reusable reference-document evidence.
- Only hash-verified reviewer-confirmed drawing inputs may bind to Math or Rule Engine execution.

---

## Decomposed Plans

| Order | Plan | Deliverable |
|---:|---|---|
| M0 | `2026-08-02-browser-drawing-shared-contracts.md` | Review Packet v2, workflow, drawing, attachment, next-action, and v1 adapter contracts |
| M1 | `2026-08-02-drawing-evidence-backend.md` | immutable case drawing intake, quality gate, candidate repository, append-only confirmations, confirmed-input binding |
| M2 | `2026-08-03-drawing-manual-annotation-ui.md` | deterministic browser projection, SVG annotation tools, strict actions, append-only service, loopback server |
| 1 | `2026-08-01-foundation-and-contracts.md` | package, canonical models, immutable runs, no-network guard |
| 2 | `2026-08-01-parse-engine-and-evidence-store.md` | coordinate-traceable evidence SQLite snapshot |
| 3 | `2026-08-01-math-engine.md` | versioned Decimal calculation engine |
| 4 | `2026-08-01-rule-as-code-engine.md` | approved executable JSON rules |
| 5 | `2026-08-01-hybrid-rag-and-citations.md` | deterministic retrieval and citation enforcement |
| 6 | `2026-08-01-llm-dual-track-confidence-abstention.md` | Track A/B validation, confidence, abstention |
| 7 | `2026-08-01-review-packet-and-runtime-packaging.md` | reviewer HTML/JSON, Codex bundle, ChatGPT web ZIP |
| 8 | `2026-08-01-end-to-end-validation-and-migration.md` | Ansim Housing migration, golden cases, release gate |

## Target Repository Structure

```text
AGENTS.md
pyproject.toml
src/ansim_review/
  contracts/ evidence/ parsing/ math_engine/ rule_engine/
  retrieval/ llm_layer/ confidence/ abstention/ review_packet/ packaging/
  drawing_review/
rules/candidates/ rules/approved/ rules/manifests/
evidence/ source/ runs/ exports/ web_runtime/
cases/<case_id>/sources/drawings/ candidates/ confirmations/
tests/unit/ tests/integration/ tests/golden/
docs/superpowers/specs/ docs/superpowers/plans/
```

## Milestone Gates

0. **M0 Shared contracts — complete:** Review Packet v1 is frozen; v2, workflow, drawing, immutable-attachment, next-action, and deterministic adapter contracts passed automated validation and human contract review in PR #16.
1. **M1 Drawing evidence backend — complete:** Supported drawings are copied into immutable case storage, quality assessed, represented by extractor or reviewer-manual candidates, confirmed through append-only records, and bound to engines only after source and confirmation hash revalidation.
2. **M2 Browser manual annotation — implementation in Draft PR #54:** The deterministic page/candidate view model, self-contained SVG renderer, strict browser action decoder, append-only action service, loopback-only server, four geometry capture tools, and browser-to-engine E2E contract are implemented. Repository-wide automated verification and actual browser manual QA remain required before completion.
3. **Core v0.1:** Plans 1–4 pass; source, calculations, and rules are deterministic.
4. **Evidence v0.2:** Plans 5–6 pass; uncited claims and weak evidence abstain.
5. **Review v0.3:** Plan 7 passes; Codex and ChatGPT web packages execute offline.
6. **Ansim v1.0:** Plan 8 passes automated and human acceptance; only this milestone may declare production-review readiness.

## M2 Acceptance Boundary

M2 is complete only when all of the following are true:

- all four M0 geometry types remain aligned at 100%, 200%, and fit-to-page zoom;
- no reviewer action is selected by default;
- browser payloads cannot set source hashes, output paths, confirmation IDs, or manual candidate IDs;
- existing candidate accept/reject/edit and reviewer-manual create actions produce create-only or append-only artifacts;
- Host, Origin, access token, body-size, content-type, case-root, and path checks fail closed;
- confirmed values reach Math or Rule Engine binding only after candidate, confirmation, and immutable source hashes are reverified;
- repository pytest, Ruff, strict mypy, compileall, Python 3.11/3.13 wheel, Windows, and Ubuntu verification pass;
- human browser QA records browser, OS, exact HEAD, screen scale, and PASS/FAIL evidence.

GitHub Actions runs that terminate without executing job steps are recorded as `ACTIONS_UNAVAILABLE` and do not satisfy this gate.

## Drawing Follow-Up Order

After M2 manual annotation acceptance:

1. calibration records and Math Engine formulas for confirmed scale/reference dimensions;
2. staged automatic candidate extractors for text/table metadata, then lines, then semantic boundaries and entrances;
3. Review Packet v2 drawing-evidence rendering and reviewer workflow integration;
4. issue #7 state-machine and resumable Codex orchestration integration.

Automatic detection success is never the sole acceptance criterion. The manual annotation to confirmed input to engine-binding path remains mandatory.

## Contract Governance

`docs/CONTRACT_GOVERNANCE.md` is authoritative for shared enum ownership, v1 compatibility, machine/human authority separation, deterministic payload boundaries, and downstream integration rules.

## Commit Policy

One independently reviewable commit per task. Observe each test failing before implementation. Never combine parser, Math Engine, and Rule Engine changes in the same commit.
