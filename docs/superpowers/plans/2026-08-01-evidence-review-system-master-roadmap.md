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

---

## Decomposed Plans

| Order | Plan | Deliverable |
|---:|---|---|
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
rules/candidates/ rules/approved/ rules/manifests/
evidence/ source/ runs/ exports/ web_runtime/
tests/unit/ tests/integration/ tests/golden/
docs/superpowers/specs/ docs/superpowers/plans/
```

## Milestone Gates

1. **Core v0.1:** Plans 1–4 pass; source, calculations, and rules are deterministic.
2. **Evidence v0.2:** Plans 5–6 pass; uncited claims and weak evidence abstain.
3. **Review v0.3:** Plan 7 passes; Codex and ChatGPT web packages execute offline.
4. **Ansim v1.0:** Plan 8 passes automated and human acceptance; only this milestone may declare production-review readiness.

## Commit Policy

One independently reviewable commit per task. Observe each test failing before implementation. Never combine parser, Math Engine, and Rule Engine changes in the same commit.
