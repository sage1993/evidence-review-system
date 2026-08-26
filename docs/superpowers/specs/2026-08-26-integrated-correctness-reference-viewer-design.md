# Integrated Correctness + Reference Viewer Convergence Design

## 1. Purpose

This design converges the remaining open Evidence Review System work onto the current `main` branch without re-merging stale implementation history.

The remaining work is split into two sequential delivery tracks:

1. **PR-A — Issue #116 correctness hardening**: re-integrate the valid behavior from PR #117 onto current `main`, verify it against the real corpus, merge it, then close Issue #116 and supersede PR #117.
2. **PR-B — Reference Viewer v2**: extract only the unique, still-valid Reference Viewer capabilities from PR #121, implement them on top of the already-merged Issue #119/#122 Visual Review architecture, then supersede PR #121.

The current `main` branch, including merged PR #122, is the source of truth for all implementation and regression decisions. The design branch was created from `main@3eb45de3d6d12265d6fa75f713b42a570955e949`; implementation must re-confirm the actual `main` HEAD before creating each delivery branch.

---

## 2. Repository State and Decision

### Current source of truth

- `main` contains merged PR #122 Visual Review hardening.
- Issue #119 is complete.
- PR #117 remains open/draft and is based on an older `main`.
- PR #121 remains open and overlaps Visual Review files now changed by PR #122.
- Issue #116 remains open and requires real-corpus acceptance before closure.

### Decision

Do not merge PR #117 or PR #121 directly.

Instead:

- create fresh integration branches from the then-current `main`;
- inventory legacy behavior against current `main` before porting anything;
- selectively port only behavior, tests, and contracts that are still missing and valid;
- preserve all PR #122 behavior as regression-protected baseline;
- when #117 and #122 touch the same workflow boundary, preserve the already-validated #122 contract unless Issue #116 acceptance proves a targeted change is required;
- close the legacy PRs only after their required behavior has been replaced by current-main-based work.

Equivalent behavior already present in `main` is not reimplemented merely because it exists in a legacy PR.

---

## 3. Delivery Structure

### PR-A — Correctness hardening

PR-A owns the trust and correctness path from active workspace selection through final review artifacts:

```text
Active workspace
→ evidence snapshot provenance
→ QuestionPlan / required facets
→ retrieval and relevance filtering
→ clause/citation locality
→ deterministic comparisons
→ issue/facet/evidence/comparison lineage
→ Track A validation
→ Track B validation
→ final packet
```

PR-A does not redesign the Visual Review UI. Existing PR #122 Visual Review behavior must remain unchanged except where required to consume already-existing final review data safely.

### PR-B — Reference Viewer v2

PR-B owns presentation-only projection and reviewer interaction for authoritative references:

```text
Validated citation / related retrieval evidence
→ safe reference projection
→ verified reference page asset
→ reference anchor
→ Finding binding
→ Reference Viewer focus
```

PR-B cannot create or upgrade evidence authority, deterministic results, confidence, review status, or human decisions.

---

## 4. PR-A Architecture

### 4.1 Active workspace binding

`$ERS_PDF` is responsible for preparing and binding the workspace used by future `$ERS_REVIEW` runs.

The binding is stored in repository-local control state:

```text
.ers/active-workspace.json
```

The binding must identify the exact workspace and its evidence snapshot state.

`$ERS_REVIEW` begins by resolving the active binding; it must not search recursively for `evidence.sqlite`, choose the newest workspace, choose the first match, or infer a workspace from a previous run.

Required fail-closed states:

- `ACTIVE_WORKSPACE_NOT_BOUND`
- `ACTIVE_WORKSPACE_STALE`
- `EVIDENCE_SNAPSHOT_MISMATCH`

A stale or mismatched workspace must stop before substantive review proceeds.

### 4.2 Snapshot provenance

Every prepared review run must preserve enough immutable provenance to establish which evidence snapshot was used.

At minimum:

- evidence snapshot hash;
- evidence database SHA-256;
- schema version;
- retrieval record count;
- clause record count.

The same provenance must remain traceable through retrieval artifacts and the Track A handoff.

### 4.3 Clause granularity

Operational legal/administrative standards must support deterministic derived subclauses below large section headings.

For structures such as:

```text
4-4-2.
  나.
    1)
      가)
      나)
    2)
      나)
```

derived structural keys may use forms such as:

```text
4-4-2/나/1/가
4-4-2/나/1/나
4-4-2/나/2/나
```

Parser elements remain source truth. Derived clauses are deterministic retrieval artifacts and must retain page/source-element/bbox provenance.

### 4.4 Issue/facet compilation

A compound legal issue must not be treated as one generic `rule` requirement when independent determinations are required.

For the Issue #116 I2 case, required facets are:

- `minimum-area-threshold`
- `distance-normal-threshold`
- `distance-conditional-threshold`

The system may add deterministic facet search requests when the planner's broad request does not separately retrieve all required rules.

### 4.5 Relevance and conflict gates

Search results must be validated against the actual issue subject and facet intent before they satisfy coverage.

Known regression constraints include:

```text
역세권 != 간선도로변
임대형기숙사 != 임대형기숙사를 제외한
```

Rejected evidence must remain observable in retrieval trace with a deterministic rejection reason.

A non-empty search result is not sufficient to terminate fallback if the result fails required anchors or subject relevance.

### 4.6 Match-local citation materialization

Citation resolution must not simply return the first N source elements associated with a broad derived clause.

Citation selection must prioritize:

1. the source element that directly matched the required facet/query;
2. deterministic nearest supporting source elements when needed;
3. a bounded citation budget.

All returned citations retain source/page/bbox provenance.

### 4.7 Deterministic comparison

Numeric rule application is runtime-owned, not prose-owned.

For I2, the required comparisons are:

```text
1500 >= 1000 → true
300 <= 250   → false
300 <= 350   → true
```

These comparisons belong to I2, not I1.

Each comparison preserves:

- `comparison_id`
- `issue_id`
- `facet_id`
- fact value and unit
- threshold value and unit
- operator
- boolean result
- supporting evidence lineage
- deterministic result hash

I2 is `CONDITIONAL` only when all required facets are present and the comparison pattern supports the conditional path.

### 4.8 Coverage and lineage

Coverage is facet-aware, not merely role-aware.

The final lineage chain is:

```text
Issue
↕
Facet
↕
Evidence
↕
Comparison
↕
Track A claim
↕
Final IssueResult
```

A generic rule hit cannot mark a compound issue `RESOLVED` if required facets are missing.

Optional lineage fields in existing contracts remain backward compatible for older packets.

### 4.9 Track A / Track B retry ownership

External generation writes attempt-specific files only:

```text
track-a-attempt-<N>.json
track-b-attempt-<N>.json
```

Canonical validated outputs are runtime-owned:

```text
track-a-output.json
track-b-output.json
```

After successful validation of a stage, that stage must not be externally generated again.

A finalization/recovery error after successful Track B validation must reuse the canonical validated Track B output and resume finalization only.

`FILEEXISTSERROR` is not a normal retry signal.

Retry identity mismatches must fail closed.

If current `main` already contains a stronger equivalent Track A/Track B invariant from PR #122, PR-A retains that stronger invariant and ports only the missing Issue #116 behavior around it.

---

## 5. PR-A Acceptance

### 5.1 Automated regression gate

On the exact current-main-based PR-A HEAD, all of the following must pass:

```text
Issue #116 targeted tests
full pytest
Ruff
mypy
compileall
documentation validation
```

Any regression introduced while porting #117 behavior onto current `main` must be resolved before real-corpus acceptance.

### 5.2 Real-corpus smoke cases

The same bound evidence snapshot must successfully answer the three direct retrieval cases:

- S1: business-site minimum area → direct `1,000㎡` evidence;
- S2: station platform boundary distance → direct `250m` and conditional `350m` evidence;
- S3: rental dormitory parking → direct paragraph ② / referenced parking standard lineage.

Target: **3/3 retrieval success on one verified snapshot**.

### 5.3 Real-corpus I1–I7 acceptance

Minimum expected state:

| Issue | Expected outcome |
|---|---|
| I1 | `RESOLVED` with direct minimum-area evidence |
| I2 | `CONDITIONAL` with three required facets and three comparisons |
| I3 | correct authority/source-gap state; no false lineage |
| I4 | mixed-use/dormitory parking lineage assigned to the correct issue |
| I5 | direct 400% semi-industrial FAR evidence |
| I6 | direct `2분의 1까지 완화` + committee/procedure evidence |
| I7 | local rule retained; external authority gap remains explicit if not ingested |

The acceptance review must inspect:

- evidence snapshot provenance;
- retrieval trace and rejection reasons;
- selected evidence;
- facet coverage;
- comparison lineage;
- Track A/Track B attempt counts;
- final packet issue results;
- READY/ABSTAIN state.

The Issue #116 contract that controls this acceptance is I2=`CONDITIONAL`; older PR comments that expected `RESOLVED` do not override the issue acceptance criteria or deterministic comparison contract.

### 5.4 PR-A completion state

Only after the real-corpus gate passes:

1. mark PR-A ready;
2. merge PR-A;
3. close Issue #116 as completed;
4. close PR #117 as superseded by PR-A.

---

## 6. PR-B Architecture — Reference Viewer v2

### 6.1 Purpose

PR-B restores only the still-useful unique capabilities from PR #121 while retaining PR #122's final Visual Review architecture.

The Reference Viewer is a read-only reviewer projection. It cannot modify machine-review authority.

### 6.2 Supported reference types

The projection supports:

- `TEXT`
- `TABLE`
- `PDF_PAGE`
- `IMAGE`
- `DIAGRAM`
- `DRAWING`

Type classification is based only on validated parser/Evidence DB metadata. The viewer must not infer semantic authority that is absent from source records.

### 6.3 Safe reference projection

The projection exposes bounded viewer metadata only.

Examples:

- text quote/title/page;
- table cells with validated row/column/span/text/selected metadata;
- visual kind metadata;
- reference page identity;
- page coordinate anchor.

Raw parser JSON, unbounded table payloads, internal model reasoning, and private implementation identifiers are not presented as user-facing data.

### 6.4 Verified reference page assets

Reference pages are materialized only from already verified page-image cache artifacts.

Pages are deduplicated by source/revision/page identity so the same raster is not embedded multiple times.

Reference raster bytes must not be duplicated into the general review-model JSON when they are already represented as page assets.

Reference projection must verify page geometry and source hash against the cached page record before rendering.

### 6.5 Independent dual focus

A Finding binds two independent targets:

```text
Finding
├─ Reference anchor
└─ Subject region
```

Selecting a Finding causes:

```text
Reference Viewer → authoritative page/type/anchor focus
Subject Viewer   → subject page/region focus
```

Reference and subject coordinates remain independent. Pixel-offset synchronization is not the default model.

### 6.6 Direct and related reference separation

PR #122's authority distinction remains mandatory:

- deterministic Track A claim citations are **direct references**;
- retrieved evidence projected through allowed search-request lineage is **related reference** material only.

A related reference cannot become a direct reference solely because it is visually displayed or focused.

### 6.7 Table behavior

When parser metadata provides a bounded explicit table cell target, the viewer may highlight the target cell/row.

When no explicit target exists, the viewer renders the table without inventing a cell-level focus.

### 6.8 Visual Review regression constraints

PR-B must preserve all merged PR #122 behavior:

- direct/related references remain separate;
- `not_comparable` remains distinct and renders as `비교 불가`;
- semantic visual finding grouping;
- Finding click focus;
- Reference empty state;
- ABSTAIN summary;
- selected-only behavior;
- click-only Decision Drawer;
- SVG overlay safety and no black overlay/box;
- high-resolution large-PDF rendering;
- page/tile lazy rendering;
- zoom/pan/fit behavior;
- resizable Reference/Subject divider;
- Track B immutable evidence support;
- machine packet status and human decision remain unchanged by presentation.

---

## 7. PR-B Acceptance

### 7.1 Type coverage

Each reference type must have deterministic renderer coverage:

```text
TEXT
TABLE
PDF_PAGE
IMAGE
DIAGRAM
DRAWING
```

### 7.2 Interaction coverage

At minimum:

- Finding selection focuses the correct Reference target;
- Finding selection focuses the correct Subject target;
- changing viewer size does not change source-bound anchor identity;
- missing direct reference renders the explicit empty state;
- related references remain visibly separated.

### 7.3 Authority invariance

Rendering Reference Viewer data must not change:

- Track A claim content;
- Track B audit content;
- issue coverage;
- deterministic comparison results;
- final status;
- confidence;
- `human_decision`.

### 7.4 Performance and browser acceptance

PR-B repeats the Issue #119/#122 browser acceptance baseline, including supported viewport sizes and large-PDF high-zoom behavior.

Large reference/page sets must stay within the existing bounded rendering approach; no new tile subsystem is introduced unless measured acceptance evidence proves it necessary.

### 7.5 PR-B completion state

Only after automated and browser acceptance passes:

1. merge PR-B;
2. close PR #121 as superseded by PR-B.

---

## 8. Implementation Order

```text
Phase 0  Freeze and verify current main baseline
Phase 1  Inventory #117 behavior/tests against current main
Phase 2  Implement PR-A on fresh current-main branch
Phase 3  Run targeted + full automated regression
Phase 4  Run real-corpus S1–S3 and I1–I7 acceptance
Phase 5  Merge PR-A; close #116 and supersede #117
Phase 6  Inventory #121-only capabilities against merged main
Phase 7  Implement safe reference projection and verified page assets
Phase 8  Bind Findings to independent Reference + Subject targets
Phase 9  Integrate Reference Viewer renderer/interactions
Phase 10 Run #122 regression + browser/performance acceptance
Phase 11 Merge PR-B; supersede #121
```

PR-B does not begin implementation until PR-A has merged and the new `main` is the verified base.

---

## 9. Non-Goals

This convergence work does not:

- replace the final review packet schema with a new major version;
- allow UI projection to create legal/evidence authority;
- allow the LLM to perform untracked numeric rule comparisons;
- introduce a quick-answer bypass around formal review;
- infer table cells or drawing measurements not present in validated source data;
- re-implement completed Issue #119 behavior from scratch;
- merge stale PR histories merely to preserve commit ancestry;
- add a new general-purpose PDF tiling architecture without measured need.

---

## 10. Failure and Rollback Strategy

Each PR is independently mergeable and testable.

If PR-A fails real-corpus acceptance, Issue #116 remains open and PR-B implementation does not start.

If PR-B fails Visual Review regression acceptance, the merged PR-A correctness work remains unaffected. Reference Viewer changes can be revised or abandoned without reverting correctness changes.

No legacy PR is closed until its required behavior is demonstrably replaced by current-main-based implementation.

---

## 11. Final Target State

After successful completion:

```text
main
├─ Issue #116 correctness/workspace/retry hardening
├─ Issue #119 / PR #122 Visual Review hardening
└─ Reference Viewer v2
```

Repository issue/PR state:

```text
#116 CLOSED — completed by PR-A
#117 CLOSED — superseded by PR-A
#119 CLOSED — already completed
#121 CLOSED — superseded by PR-B
#122 MERGED — regression baseline retained
```
