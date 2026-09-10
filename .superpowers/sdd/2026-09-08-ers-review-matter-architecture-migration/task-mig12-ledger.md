# SDD ledger — MIG-12 / Issue #182

## Preflight rulings

| Boundary | Ruling |
| --- | --- |
| ReviewMatter CLI → application service | Every Matter mutation routes through `ReviewMatterService`; handlers do not own storage/formal engine mutations. |
| Work state → Formal Run state | CLI output distinguishes mutable Matter work state from immutable formalization/run identities. |
| Revision concurrency | Every mutation requires the expected revision/ETag equivalent and stale/invalid IDs fail closed without partial mutation. |
| Authority/path resolution | Use canonical repository-local active workspace and existing trust primitives; no filesystem guessing or user-supplied authority hashes/timestamps. |
| Compatibility | Existing `review-question` and `review-run` commands remain available and behavior-compatible. |

## Acceptance checklist

- [ ] RED focused CLI flow fails only for the missing canonical service/CLI contract
- [ ] ReviewMatterService owns all Matter mutations
- [ ] create/status/add-issue/bind-evidence/search/select-evidence/formalize CLI flow works
- [ ] Stale expected revision and invalid Matter ID fail closed without partial mutation
- [ ] Formalization returns immutable snapshot/run identities
- [ ] Existing formal CLI regressions pass
- [ ] Focused/adjacent/static/full exact-head gates pass
- [ ] Independent gpt-5.6-sol-high review PASS/APPROVED
- [ ] Remote SHA parity, PR, merge, Issue #182 closure, and ancestry verified

## Scope control

- `SCOPE_EXPANSION_REQUIRED = YES` — `add-issue` must be an append-only,
  revision-checked Matter mutation. The existing event projection has no
  `ISSUE_ADDED` transition, so this issue must also modify
  `src/evidence_review/review_matter/projection.py`. This is limited to the
  canonical event projection required by the new service; it does not alter
  Matter schema, finalized evidence, Formal Run, Track A/B, finalizer, or UI.
- Do not modify protected Workbench/UI, evidence authority, or unrelated legacy compatibility paths.
