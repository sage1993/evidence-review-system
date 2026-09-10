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

- [x] RED focused CLI flow fails only for the missing canonical service/CLI contract
- [x] ReviewMatterService owns all Matter mutations
- [x] create/status/add-issue/bind-evidence/search/select-evidence/formalize CLI flow works
- [x] Stale expected revision and invalid Matter ID fail closed without partial mutation
- [x] Formalization returns immutable snapshot/run identities
- [x] Existing formal CLI regressions pass
- [x] Focused/adjacent/static/full implementation-candidate gates pass
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

## Execution record

- Base SHA: `b766707`; branch: `feat/mig-12-review-matter-cli`.
- RED (Python 3.13.14, fresh elevated Windows temp base): 2 failed in 0.96s,
  both because `review-matter` was absent from the parser. The initial sandboxed
  run was a host ACL error before test setup and is not RED evidence.
- GREEN: focused CLI flow 2 passed in 1.33s. It covers create, add-issue,
  bind-evidence, read-only navigation search, evidence selection, status, and
  formalization; it also proves a stale expected revision returns
  `MATTER_REVISION_CONFLICT` without an issue/event write.
- Adjacent Matter/navigation/formal CLI suite: 183 passed in 45.84s.
- Full Python 3.13 pytest at implementation candidate
  `1d44346ef3e21e8a3a11a6e3fbeee4dc35b5fa9f`: 2097 passed, 1 skipped in
  391.20s.
- Ruff, mypy (`src`), mypy (`--platform win32 src`), compileall, source-tree
  documentation validation (50 documents, errors=0, warnings=145), and diff
  check: PASS at that implementation candidate.
- Browser/manual acceptance: `NOT_RUN`. GitHub Actions: `ACTIONS_NOT_RUN`.
- Independent gpt-5.6-sol-high review, push, remote SHA parity, PR, merge, and
  Issue #182 closure: `NOT_RUN` (outside this implementer authorization).

## Fix-round execution record

- Review blockers reproduced with focused RED tests (Python 3.13.14, fresh
  elevated Windows temp base): 8 failed, 2 passed in 2.22s. Missing-Matter
  operations created `matter.sqlite`, and a sidecar trust `RuntimeError`
  escaped the CLI.
- GREEN: 11 focused tests passed in 3.04s. Existing-Matter operations now use
  an existing-file-only store path and preflight Matter existence; navigation
  authority `RuntimeError` is converted to the canonical CLI exit code 2 with
  its stable reason.
- Adjacent Matter/navigation/formal CLI suite: 192 passed in 45.15s.
- Fix-round exact-head implementation commit:
  `2f6af66e2353a68a63d988abf8f8c265a750b0ba`.
- Exact-head focused CLI flow: 11 passed in 2.02s; adjacent
  Matter/navigation/formal CLI suite: 192 passed in 45.80s.
- Exact-head full Python 3.13 pytest: 2106 passed, 1 skipped in 377.81s.
- Exact-head Ruff, mypy `src`, mypy `--platform win32 src`, compileall, and
  `git diff --check`: PASS. Both mypy runs checked 260 source files.
- Exact-head source-tree documentation validation: PASS; 50 documents,
  errors=0, warnings=145. The initial invocation against an unrelated
  installed checkout returned `SOURCE_MISMATCH`; the corrected source-tree
  invocation with this worktree's `src` on `PYTHONPATH` passed.

## Fix-round-2 execution record

- Sol-high blockers reproduced with focused RED tests (Python 3.13.14, fresh
  elevated Windows temp base): 3 failed, 11 passed in 3.68s. Invalid create
  left `matter.sqlite`; an existing dependency was rejected as unknown; and a
  self-dependency was accepted.
- GREEN: 14 focused tests passed in 3.22s. Create identity/title validation
  now precedes create-store opening. Candidate issue validation uses the
  actual current Matter, rejects self-dependency, and preserves the existing
  dependency graph and formal lineage.
- Adjacent Matter/navigation/formal CLI suite before the candidate commit:
  195 passed in 64.09s.
- Fix-round-2 exact code candidate:
  `9afa848e3dcc667c0f207fe98e2efa6e571d0998`.
- Exact-head focused CLI flow: 14 passed in 2.32s; adjacent
  Matter/navigation/formal CLI suite: 195 passed in 47.94s.
- Exact-head full Python 3.13 pytest: 2109 passed, 1 skipped in 372.33s.
- Exact-head Ruff, mypy `src`, mypy `--platform win32 src`, compileall, and
  `git diff --check`: PASS. Both mypy runs checked 260 source files.
- Exact-head source-tree documentation validation: PASS; 50 documents,
  errors=0, warnings=145.
