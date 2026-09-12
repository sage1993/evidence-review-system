# Evidence Review System Documentation

This is the documentation entrypoint for the current Evidence Review System
runtime. Use the current-authority documents first. Dated acceptance records
and implementation plans preserve what was verified or decided at a specific
point in history; they are not replacements for the current workflow or
release policy.

## ReviewMatter authority modes

**Evidence Navigation** is non-authoritative use of finalized evidence and
does not itself create a Planner handoff, conclusion, packet, or decision. The
Workbench stores **mutable ReviewMatter work state** separately from evidence.
**Formalization** is the only promotion boundary into **Formal Review**;
Formal Review keeps the validated Planner, deterministic engines, Track A/B,
immutable packet, and append-only Human Decision authority.

## Current authority

- [Manual Acceptance and Main-Merge Policy](MANUAL_ACCEPTANCE_POLICY.md) — current release and merge acceptance authority.
- [Commit, Push, and Pull Request Policy](COMMIT_PUSH_POLICY.md) — current issue-scoped branch, commit, push, PR, review, and merge process.
- [Release Version Policy](RELEASE_VERSION_POLICY.md) — current source-version and publication authority.
- [Reviewer Workflow](REVIEWER_WORKFLOW.md) — current human review, protected browser, archival decision, and browser QA workflow.
- [Codex Workflow](CODEX_WORKFLOW.md) — current `$ERS_PDF` / `$ERS_REVIEW` handoffs and runtime contracts.
- [ChatGPT Web Workflow](CHATGPT_WEB_WORKFLOW.md) — current external handoff boundary for web-assisted review.
- [Active Codex skills](../.agents/skills/README.md) — current user-facing `$ERS_PDF` and `$ERS_REVIEW` skill instructions.

### Release acceptance authority

The current release commands are:

```powershell
py -3.13 scripts/validate_release.py $WORKSPACE --run-id <RUN-ID>
py -3.13 scripts/build_release.py $WORKSPACE <output> --run-id <RUN-ID>
```

`scripts/validate_workspace.py` is retired and is not a current release gate.
`scripts/validate_legacy_ansim_workspace.py` is retained only for explicit
legacy ANSIM/Grist migration or acceptance work; it must not replace the
release validator or builder.

## Architecture and contracts

- [Contract Governance](CONTRACT_GOVERNANCE.md)
- [AI Question Planning](question-planning.md)
- [Source Batch v2 and Parser Registry](SOURCE_BATCH_V2.md)
- [OpenDataLoader Parser Reproducibility](PARSER_REPRODUCIBILITY.md)
- [Rule Activation Governance](RULE_ACTIVATION_GOVERNANCE.md)
- [Track A Numeric Grammar](TRACK_A_NUMERIC_GRAMMAR.md)

## Operations

- [Offline Execution Boundary](OFFLINE_EXECUTION.md)
- [Source Batch v2 and Parser Registry](SOURCE_BATCH_V2.md)
- [OpenDataLoader Parser Reproducibility](PARSER_REPRODUCIBILITY.md)
- [Example assets](examples/README.md)
- [Generated/reference viewer image](ui-reference/review-result.png)

## Migration and compatibility

- [Evidence Database Schema Migration](EVIDENCE_SCHEMA_MIGRATION.md)
- [Legacy Document Lineage Migration](LEGACY_LINEAGE_MIGRATION.md)
- [Legacy Grist Visual Compatibility Boundary](LEGACY_VISUALS.md)
- [Legacy skill-path compatibility pointer](../skills/README.md)

These documents describe bounded compatibility or migration paths. They do
not replace the current `$ERS_PDF` / `$ERS_REVIEW` workflow.

## Acceptance records

These documents are commit/date-specific verification records. They are
evidence of the scope they name, not current runtime authority.

- [Reference Viewer v2 cold-cache acceptance — 2026-09-03](REFERENCE_VIEWER_V2_COLD_CACHE_ACCEPTANCE_2026-09-03.md)
- [Stabilization Closure Round 2 — 2026-09](STABILIZATION_CLOSURE_2026-09.md) — historical exact-main and inherited acceptance evidence.

## Historical implementation plans

The documents below are historical execution records. Do not use their
commands as current release or runbook authority; use
[Manual Acceptance and Main-Merge Policy](MANUAL_ACCEPTANCE_POLICY.md) and the
current workflow documents above.

- [Historical: 2026-08-16 real-review retrieval relevance fix](plans/2026-08-16-real-review-retrieval-relevance-fix.md)
- [Historical: 2026-08-26 Reference Viewer v2 port inventory](plans/2026-08-26-reference-viewer-v2-port-inventory.md)
- [Historical: 2026-08-13 Korean retrieval formal-review invariants](superpowers/plans/2026-08-13-korean-retrieval-formal-review-invariants.md)
- [Historical: 2026-08-14 Issues 98–101 integrated fix](superpowers/plans/2026-08-14-issues-98-101-integrated-fix.md)
- [Historical: 2026-08-15 Issue 112 AI Question Planner](superpowers/plans/2026-08-15-issue-112-ai-question-planner.md)
- [Historical: 2026-08-15 public readiness v0.2.0](superpowers/plans/2026-08-15-public-readiness-v0.2.0.md)
- [Historical: 2026-08-16 real workspace clause retrieval repair](superpowers/plans/2026-08-16-real-workspace-clause-retrieval-repair.md)
- [Historical: 2026-08-21 case visual review integration](superpowers/plans/2026-08-21-case-visual-review-integration.md)
- [Historical: 2026-08-24 Issue 119 visual review hardening](superpowers/plans/2026-08-24-issue-119-visual-review-hardening.md)
- [Historical: 2026-08-26 PR-A execution bootstrap](superpowers/plans/2026-08-26-pr-a-execution-bootstrap.md)
- [Historical: 2026-08-26 PR-A Issue 116 correctness convergence](superpowers/plans/2026-08-26-pr-a-issue-116-correctness-convergence.md)
- [Historical: 2026-08-26 PR-B Reference Viewer v2](superpowers/plans/2026-08-26-pr-b-reference-viewer-v2.md)
- [Historical: 2026-08-26 PR122 formal acceptance hardening](superpowers/plans/2026-08-26-pr122-formal-acceptance-hardening.md)
- [Historical: 2026-09-03 cold-case visual tile prewarm](superpowers/plans/2026-09-03-cold-case-visual-tile-prewarm.md)
- [Historical: 2026-09-05 Evidence Review System stabilization implementation plan](superpowers/plans/2026-09-05-evidence-review-system-stabilization-implementation-plan.md)
- [Historical: 2026-09-07 Issue 138 legacy workspace validator](superpowers/plans/2026-09-07-issue-138-legacy-workspace-validator.md)
- [Historical: 2026-09-07 repository hygiene and documentation baseline](superpowers/plans/2026-09-07-repository-hygiene-documentation-baseline.md)
- [Historical: Superpowers implementation plan index](superpowers/plans/README.md)
- [Historical: Korean retrieval formal-review invariants design](superpowers/specs/2026-08-13-korean-retrieval-formal-review-invariants-design.md)
- [Historical: Issues 98–101 integrated fix design](superpowers/specs/2026-08-14-issues-98-101-integrated-fix-design.md)
- [Historical: Public readiness v0.2.0 design](superpowers/specs/2026-08-15-public-readiness-v0.2.0-design.md)
- [Historical: Integrated correctness and Reference Viewer design](superpowers/specs/2026-08-26-integrated-correctness-reference-viewer-design.md)
- [Historical: PR122 formal acceptance hardening design](superpowers/specs/2026-08-26-pr122-formal-acceptance-hardening-design.md)

## Classification notes

- `docs/README.md`, the current workflow/contract/operations documents, and
  the active `.agents/skills` instructions are current material.
- `docs/plans/` and `docs/superpowers/plans/` are `HISTORICAL_PLAN` records.
- `docs/superpowers/specs/` contains historical design records in the same
  preserved planning boundary.
- The dated cold-cache document is an `ACCEPTANCE_RECORD`.
- `docs/EVIDENCE_SCHEMA_MIGRATION.md`, `docs/LEGACY_LINEAGE_MIGRATION.md`,
  `docs/LEGACY_VISUALS.md`, and the legacy skill pointer are
  `MIGRATION_COMPATIBILITY` material.
- No document was deleted or modernized as part of this index; no current
  document is intentionally classified as `OBSOLETE_OR_DUPLICATE` or
  `UNKNOWN`.
