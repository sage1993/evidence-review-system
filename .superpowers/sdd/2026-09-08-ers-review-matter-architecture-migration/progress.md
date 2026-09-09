# SDD ledger — MIG-11 / Issue #181

## Preflight

| Interface | Producer / consumer | Ruling |
| --- | --- | --- |
| MIG-10 Formal RUN identity → MIG-11 lineage | FormalizationSnapshot and finalized RUN identity are immutable inputs to Matter history. | Preserve exact snapshot ID, RUN ID, packet SHA, and Matter ID; do not derive authority from planner or draft state. |
| #157 run-local packet → current-review pointer | The pointer is a convenience selector, not a replacement packet authority. | Bind exact `run_id` + packet SHA and resolve only after verifying the run-local packet and canonical finalized-run authority. |
| Human Decision → new RUN | Existing decisions are packet-hash/run scoped. | Never copy or project a prior decision when resolving a new current review. |
| Matter schema → append-only history | One Matter can have multiple formal runs. | Add append-only lineage storage with deterministic ordering and duplicate/conflict rejection. |

## Acceptance checklist

- [x] Focused RED reproduces missing lineage/pointer contract without unrelated host failure
- [x] Two formal runs bind and list without overwrite/delete
- [x] Current pointer canonical bind/resolve works
- [x] Missing/stale/malformed/hash-mismatch pointer fails closed
- [x] Prior Human Decision is not reused
- [x] #157 regression passes
- [x] Focused/adjacent/static/full exact-head gates pass
- [ ] Feature branch pushed with remote SHA parity
- [ ] PR reviewed with gpt-5.6-sol-high and merged
- [ ] Issue #181 closed and post-merge ancestry verified

## Scope control

- `SCOPE_EXPANSION_REQUIRED = YES` — `MatterStore` owns schema-version migration
  and fail-closed table validation, so MIG-11 must update
  `src/evidence_review/review_matter/store.py` and its existing schema regression
  coverage. The required SDD completion report also updates this ledger directory.
- Do not modify drawing/visual, protected viewer, or ReviewMatter service/UI paths in MIG-11.
