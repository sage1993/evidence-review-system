# Real Workspace Clause Retrieval Repair Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make a real parser-produced ERS workspace exercise clause-first retrieval end-to-end, prevent user facts in LLM-planned rule queries from suppressing the actual legal thresholds, resolve bounded same-article/legal references, distinguish missing-source/reference gaps from retrieval misses, and make confidence reflect actual issue coverage and human-review completion.

**Architecture:** Keep parser `elements` immutable as citation-grade source truth and build clauses, source-element lineage, structural sibling links, and retrieval indexes as deterministic derived artifacts. Treat QuestionPlan v2 as untrusted planner output: preserve its literal query for auditability, then compile bounded deterministic fallback variants using validated user facts and issue scope. Perform only budgeted structural sibling/reference expansion, retain local evidence even when an external authority is absent, and bind confidence to issue coverage plus actual review state.

**Tech Stack:** Python 3.13, SQLite/FTS5, pytest, Ruff, mypy, existing `EvidenceSnapshot`, QuestionPlan v2, retrieval graph, issue coverage, Track A/Track B, and finalizer contracts.

---

## Scope and production failure to lock

The current production-shaped workspace proves that parsing itself is not the primary failure: parser elements and legacy retrieval records exist, while the derived clause layer is empty. The repair therefore covers the whole boundary from parser elements to final review, not only query tuning.

Observed production shape to reproduce in tests:

```text
elements                   > 0
retrieval_records          > 0
evidence_fts               > 0
clauses                    = 0
clause_retrieval_records   = 0
clause_fts                 = 0
links                      = 0
```

The live review also exposed four distinct retrieval failures that must become acceptance cases:

- I2: planner put user fact `300m` into a rule query, so 250m/350m source clauses were missed.
- I3: query used `공공지원민간임대주택`, while the source rule is expressed as `임대형기숙사를 제외한 안심주택`.
- I4: the answer requires bounded combination of adjacent paragraphs in the same article (parking rule for dormitory + mixed-use application rule).
- I7: generic/noise token `추가` remained after fallback pruning and blocked a direct district-unit-plan parking-relaxation clause.

The existing synthetic regression is not sufficient because it pre-seeds `clauses` and `links` and uses retrieval-friendly paraphrases. The new acceptance must begin from element-only parser-shaped source text and derive the clause layer through production code.

## Non-negotiable guardrails

1. Do not add Ansim-housing-specific production hardcoding.
2. Do not solve planner violations only by changing the LLM prompt. QuestionPlan is untrusted input and requires deterministic compilation/validation.
3. Do not introduce unrestricted token-OR retrieval. Every fallback must retain bounded anchors and hard query/candidate budgets.
4. Parser elements remain source truth. Clauses, structural links, reference links, and FTS materializations are deterministic derived artifacts with provenance back to source elements/page/bbox.
5. Legacy element FTS remains a compatibility fallback, not the expected main path for structured legal documents.
6. Missing external authority is not a retrieval miss. Preserve the local citing clause and report `SOURCE_NOT_INGESTED` or `REFERENCE_TARGET_MISSING` as appropriate.
7. A high confidence label cannot mask unresolved required issue roles or an unperformed human review.
8. New tests must use actual lexical forms from the failing documents or faithful minimal extracts, not answer-shaped paraphrases.
9. Existing claim/citation issue-lineage gates and deterministic missing-input global hard gate must not be weakened.
10. Final verification is Python 3.13 only and must be tied to the exact final HEAD.

---

## Task 0 — Supersede the old acceptance record and freeze the real production failure

**Files:**
- Modify: `docs/plans/2026-08-16-real-review-retrieval-relevance-fix.md`
- Create: `tests/fixtures/real_parser_workspace_retrieval/source-elements.json`
- Create: `tests/fixtures/real_parser_workspace_retrieval/question-plan-contaminated.json`
- Create: `tests/integration/retrieval/test_real_parser_workspace_regression.py`

**Step 1: Mark execution state correctly when implementation starts**

At the start of implementation, convert PR #115 back to Draft and mark the previous exact-head verification at `eb7c6261ced39e8a13ebe28c7648fe3ceec13738` as `SUPERSEDED_BY_REAL_WORKSPACE_REGRESSION`. Do not delete the prior evidence; retain it as historical verification of the earlier scope.

**Step 2: Build an element-only fixture from actual lexical forms**

The fixture must contain minimal citation-grade elements for:

- general 1,000㎡ site minimum;
- 250m station-area rule and conditional 350m designation/review rule;
- parking Article 13 paragraph 1 (non-dormitory Ansim housing);
- Article 13 paragraph 2 (rental dormitory);
- Article 13 paragraph 3 (mixed housing types apply paragraphs 1 and 2 respectively);
- Article 13 paragraph 4 (district-unit-plan parking relaxation);
- 400% FAR and industrial-site rule extracts used by existing I5/I6 tests;
- distractors previously excluded by the relevance gate.

Each element must retain realistic `page_number`, `bbox`, `parser_order`, `raw_text`, and `normalized_text`. The snapshot setup must deliberately provide `clauses=()` and `links=()`.

**Step 3: Lock the contaminated planner output**

Include the actual failure form for I2:

```text
역세권 승강장 경계 300m 사업대상지 면적 기준
```

and a noisy I7 form containing `추가`, `완화`, `요건`, and `절차`.

**Step 4: Write the failing integration test**

Assert on the current code before repair:

```python
assert database_count("elements") > 0
assert database_count("clauses") == 0
assert issue("I2").gap_codes == ("RETRIEVAL_MISS",)
assert issue("I3").gap_codes == ("RETRIEVAL_MISS",)
assert issue("I4").gap_codes == ("RETRIEVAL_MISS",)
assert issue("I7").gap_codes == ("RETRIEVAL_MISS",)
```

The regression should fail only because the desired post-repair behavior is not yet implemented; do not assert implementation details that will become invalid later.

**Step 5: Run the RED test**

```powershell
python -m pytest -q tests/integration/retrieval/test_real_parser_workspace_regression.py
```

Expected: FAIL, demonstrating that the element-only production shape does not reach clause-first retrieval and misses I2/I3/I4/I7.

**Step 6: Commit the regression fixture/test only**

```powershell
git add docs/plans/2026-08-16-real-review-retrieval-relevance-fix.md tests/fixtures/real_parser_workspace_retrieval tests/integration/retrieval/test_real_parser_workspace_regression.py
git commit -m "test: reproduce real workspace retrieval gaps"
```

---

## Task 1 — Materialize generic legal clauses and source-element lineage from parser elements

**Files:**
- Create: `src/evidence_review/evidence/clause_materialization.py`
- Modify only if required for explicit orchestration: `src/evidence_review/evidence/ingest.py`
- Create: `tests/unit/evidence/test_clause_materialization.py`
- Create: `tests/integration/evidence/test_parser_clause_materialization.py`

**Design:** `ingest_snapshot()` remains a deterministic inserter for records already supplied by the caller. Do not hide heuristic mutation inside its insert loop. Add an explicit materialization function that accepts a validated snapshot/ordered element set and returns derived clauses plus lineage links before publishing the retrieval index.

**Step 1: Write unit tests for structural recognition**

Cover generic patterns only:

- legal article heading: `제13조(...)`, including `제13조의2`;
- paragraph markers: `①`, `②`, `③`, ...;
- operational-standard numbering: `1-3-1.`, `2-1-2.`, `4-5-3.`;
- article heading and body split across adjacent parser elements;
- multiple paragraphs emitted inside one parser element;
- ordinary prose without a recognized structural marker stays unmaterialized and remains available through legacy element retrieval.

For every derived clause assert:

```python
assert clause.revision_id == source_revision_id
assert source_element_link.relation_type == "source_element"
assert source_element_link.target_id == source_element_id
```

Clause IDs must be stable for identical revision + structural key + normalized text and must not depend on insertion order outside the source order.

**Step 2: Run RED unit tests**

```powershell
python -m pytest -q tests/unit/evidence/test_clause_materialization.py
```

Expected: FAIL because `clause_materialization` does not exist.

**Step 3: Implement the minimum deterministic materializer**

Implement pure helpers for:

- marker detection and normalized structural key;
- grouping ordered source elements into an article/paragraph or operational clause;
- deterministic clause ID generation;
- `source_element` links for every contributing element;
- bounded structural links needed later for same-article traversal.

Do not infer legal meaning from Ansim-specific phrases. Structural relation types should be generic, for example `article_member`/`next_sibling`, provided they are compatible with existing graph traversal. If the current `links` table is sufficient, reuse it rather than adding schema columns.

**Step 4: Add integration coverage for real element shape**

`test_parser_clause_materialization.py` must start with `elements > 0`, `clauses == 0`; invoke the explicit materialization stage; then assert non-zero clauses and source-element lineage without manually supplying clauses in the fixture.

**Step 5: Run GREEN tests**

```powershell
python -m pytest -q tests/unit/evidence/test_clause_materialization.py tests/integration/evidence/test_parser_clause_materialization.py
```

Expected: PASS.

**Step 6: Commit**

```powershell
git add src/evidence_review/evidence/clause_materialization.py src/evidence_review/evidence/ingest.py tests/unit/evidence/test_clause_materialization.py tests/integration/evidence/test_parser_clause_materialization.py
git commit -m "feat: derive legal clauses from parser elements"
```

---

## Task 2 — Backfill existing v4 workspaces and rebuild a fresh clause index

**Files:**
- Create: `src/evidence_review/evidence/clause_rebuild.py`
- Modify: `src/evidence_review/evidence/store.py`
- Modify: `src/evidence_review/retrieval/index.py`
- Modify only if a schema change is proven necessary: `src/evidence_review/evidence/schema.sql`
- If a schema bump is necessary, create the corresponding copy-on-write migration under `src/evidence_review/evidence/migrations/`
- Create: `tests/integration/migration/test_v4_clause_backfill.py`
- Create: `tests/integration/retrieval/test_clause_index_rebuild.py`

**Step 1: Write a failing existing-workspace backfill test**

Create a schema-v4 database with:

```text
elements > 0
retrieval_records > 0
clauses = 0
clause_retrieval_records = 0
clause_fts = 0
```

Assert that the explicit rebuild/backfill operation:

- derives clauses/links;
- rebuilds `clause_retrieval_records` and `clause_fts`;
- preserves existing source elements and hashes byte-for-byte/logically unchanged;
- leaves SQLite `integrity_check` and FK checks clean;
- causes `require_fresh_index()` to pass only after the rebuild is published.

**Step 2: Run RED**

```powershell
python -m pytest -q tests/integration/migration/test_v4_clause_backfill.py tests/integration/retrieval/test_clause_index_rebuild.py
```

Expected: FAIL because an existing v4 element-only workspace has no clause backfill path.

**Step 3: Implement explicit rebuild orchestration**

The rebuild must be idempotent:

```text
same source snapshot
→ same derived clauses/links
→ same retrieval index fingerprint
```

Clear/recompute only derived clause/index artifacts, not parser elements. Publish freshness metadata only after the derived transaction succeeds.

**Step 4: Decide schema version from evidence, not convenience**

The current schema already has `clauses`, `links`, `clause_retrieval_records`, `clause_fts`, and `clause_evidence_links`. Prefer staying on schema v4 if those structures can represent all required provenance and sibling/reference relations. Introduce v5 only if a required invariant cannot be represented with existing tables; if so, add copy-on-write v4→v5 migration, rollback/failure tests, and update schema-version docs.

**Step 5: Run GREEN + existing migration/freshness regressions**

```powershell
python -m pytest -q tests/integration/migration tests/integration/retrieval/test_clause_index.py tests/integration/retrieval/test_clause_index_rebuild.py
```

Expected: PASS.

**Step 6: Commit**

```powershell
git add src/evidence_review/evidence src/evidence_review/retrieval/index.py tests/integration/migration tests/integration/retrieval/test_clause_index_rebuild.py
git commit -m "feat: backfill clause index for parser workspaces"
```

---

## Task 3 — Compile untrusted planner rule queries into bounded fact-safe variants

**Files:**
- Create: `src/evidence_review/retrieval/query_compiler.py`
- Modify: `src/evidence_review/planned_review_question.py`
- Modify: `src/evidence_review/question_planning.py`
- Modify: `src/evidence_review/retrieval/korean_variants.py`
- Create: `tests/unit/retrieval/test_rule_query_compiler.py`
- Modify: `tests/unit/review_question/test_fact_rule_query_adapter.py`

**Step 1: Write RED tests using the real bad query**

Input:

```text
fact: 대상 부지는 승강장 경계에서 300m 떨어져 있다.
request(role=rule): 역세권 승강장 경계 300m 사업대상지 면적 기준
```

Required compiled attempts, in deterministic order:

1. preserve planner literal for provenance/audit;
2. add a `FACT_DECONTAMINATED` variant that does not require the user-supplied `300m`;
3. add bounded intent/noise-pruned variants only when enough legal/entity anchors remain.

Also test:

- `1,500㎡`, normalized comma/no-comma and unit forms;
- `%` values;
- a value that appears in a fact but is also genuinely present in the rule source (literal attempt must still run first, so useful thresholds such as 400% are not prematurely discarded);
- no change to the canonical QuestionPlan JSON or facts.

**Step 2: Run RED**

```powershell
python -m pytest -q tests/unit/retrieval/test_rule_query_compiler.py tests/unit/review_question/test_fact_rule_query_adapter.py
```

Expected: FAIL.

**Step 3: Implement deterministic compilation**

The compiler receives a validated `QuestionPlan`, `QuestionIssue`, and `SearchRequest`. It must never ask an LLM to rewrite the query. Build a capped attempt list from:

```text
PLANNER_LITERAL
→ FACT_DECONTAMINATED
→ INTENT_PRUNED
→ APPROVED_ALIAS / LEGAL_COMPOUND variants
→ bounded core-token subsets
```

Fact decontamination is a fallback derivative, not mutation of the canonical planner request. Derive fact tokens from validated QuestionPlan facts with deterministic numeric/unit normalization. Remove only exact normalized equivalents and only when at least the configured minimum anchor count remains.

Expand the generic intent/noise vocabulary carefully. `추가` should be removable as review-intent noise when it is not part of a protected legal/entity phrase. Do not globally remove domain nouns.

**Step 4: Add a bounded subset policy instead of token OR**

For a multi-token query, permit only a small deterministic number of AND subsets (for example, n−1 subsets then capped smaller anchor sets with minimum two anchors). Rank/prioritize candidates deterministically. Never emit one independent OR query per token.

This is required for I3, where one planner entity term does not appear in the source clause but `주차장` / `설치기준` and structural context do.

**Step 5: Run GREEN**

```powershell
python -m pytest -q tests/unit/retrieval/test_rule_query_compiler.py tests/unit/review_question/test_fact_rule_query_adapter.py
```

Expected: PASS.

**Step 6: Commit**

```powershell
git add src/evidence_review/retrieval/query_compiler.py src/evidence_review/retrieval/korean_variants.py src/evidence_review/planned_review_question.py src/evidence_review/question_planning.py tests/unit/retrieval/test_rule_query_compiler.py tests/unit/review_question/test_fact_rule_query_adapter.py
git commit -m "fix: compile fact-safe rule retrieval queries"
```

---

## Task 4 — Execute the compiled fallback ladder and record every attempt, including zero-hit legacy fallback

**Files:**
- Modify: `src/evidence_review/retrieval/fallback.py`
- Modify: `src/evidence_review/retrieval/issue_bundle.py`
- Modify: `src/evidence_review/retrieval/trace.py`
- Modify: `tests/integration/retrieval/test_adaptive_fallback.py`
- Modify: `tests/unit/retrieval/test_trace.py`

**Step 1: Write RED tests for trace completeness**

For a query that misses at each stage, assert that the trace includes each attempted query with `hit_count=0`, including the element-FTS fallback. Current behavior records `LEGACY_ELEMENT` only when it succeeds; the repaired trace must make a full failure diagnosable.

For the contaminated I2 query, assert that the trace shows the literal `300m` attempt followed by a fact-safe variant and records the stage that first obtains the 250m/350m candidate.

**Step 2: Run RED**

```powershell
python -m pytest -q tests/integration/retrieval/test_adaptive_fallback.py tests/unit/retrieval/test_trace.py
```

Expected: FAIL.

**Step 3: Integrate the query compiler into issue retrieval**

`_bucket_candidates()` should consume the bounded compiled attempts instead of independently reconstructing ad hoc legacy queries. Keep all existing hard limits (`max_queries_per_issue`, `per_issue_role_limit`, global candidate cap) effective across derived attempts; a planner request must not multiply into an unbounded retrieval workload.

If new trace enum values are introduced, use explicit names such as:

```text
FACT_DECONTAMINATED
INTENT_PRUNED
CORE_TOKEN_AND
LEGACY_ELEMENT
```

**Step 4: Preserve relevance scoring and issue lineage**

Every candidate/match must retain:

```text
search_request_id
issue_id
role
planner query_text
actual retrieval_query
fallback_stage
```

No derived query may sever the original planner request provenance.

**Step 5: Run GREEN + issue-budget regressions**

```powershell
python -m pytest -q tests/integration/retrieval/test_adaptive_fallback.py tests/integration/retrieval/test_issue_bundle.py tests/unit/retrieval/test_trace.py tests/unit/retrieval/test_retrieval_policy.py
```

Expected: PASS.

**Step 6: Commit**

```powershell
git add src/evidence_review/retrieval/fallback.py src/evidence_review/retrieval/issue_bundle.py src/evidence_review/retrieval/trace.py tests/integration/retrieval/test_adaptive_fallback.py tests/unit/retrieval/test_trace.py
git commit -m "fix: make adaptive retrieval fact-safe and observable"
```

---

## Task 5 — Add bounded same-article/sibling expansion for multi-paragraph rules

**Files:**
- Modify: `src/evidence_review/evidence/clause_materialization.py`
- Modify: `src/evidence_review/retrieval/graph.py`
- Modify: `src/evidence_review/retrieval/issue_bundle.py`
- Create: `tests/integration/retrieval/test_bounded_article_sibling_expansion.py`
- Modify: `tests/integration/retrieval/test_bounded_reference_traversal.py`

**Step 1: Write the I4 RED test**

Use a source article where:

- paragraph 2 contains the rental-dormitory parking rule;
- paragraph 3 contains the mixed-use rule saying the housing-use rules are applied respectively.

The initial query may directly hit only paragraph 2. Assert that bounded structural expansion adds paragraph 3 to the same issue lineage without importing unrelated paragraphs beyond the configured structural budget.

**Step 2: Run RED**

```powershell
python -m pytest -q tests/integration/retrieval/test_bounded_article_sibling_expansion.py
```

Expected: FAIL.

**Step 3: Materialize explicit structural relations**

Represent same-article membership/sibling adjacency deterministically from source order. Do not infer sibling relations by textual similarity at query time.

**Step 4: Extend graph traversal with a structural expansion mode**

Apply the existing depth/node/fanout bounds. Structural sibling expansion must:

- stay within the same revision/article container;
- preserve path provenance;
- attribute retrieved sibling clauses/evidence to the originating issue/request;
- remain subject to the Track A/claim relevance gate, so merely neighboring text cannot become a final claim without issue overlap.

**Step 5: Run GREEN + existing graph tests**

```powershell
python -m pytest -q tests/integration/retrieval/test_bounded_article_sibling_expansion.py tests/integration/retrieval/test_bounded_reference_traversal.py tests/unit/retrieval/test_reference_expansion_lineage.py
```

Expected: PASS.

**Step 6: Commit**

```powershell
git add src/evidence_review/evidence/clause_materialization.py src/evidence_review/retrieval/graph.py src/evidence_review/retrieval/issue_bundle.py tests/integration/retrieval/test_bounded_article_sibling_expansion.py tests/integration/retrieval/test_bounded_reference_traversal.py
git commit -m "feat: expand bounded same-article evidence"
```

---

## Task 6 — Extract and resolve legal references deterministically

**Files:**
- Create: `src/evidence_review/evidence/legal_references.py`
- Modify: `src/evidence_review/evidence/lineage_graph.py`
- Modify: `src/evidence_review/retrieval/graph.py`
- Modify: `src/evidence_review/retrieval/coverage.py`
- Create: `tests/unit/evidence/test_legal_reference_extraction.py`
- Create: `tests/integration/retrieval/test_external_reference_resolution.py`

**Step 1: Write RED extraction tests**

Generic examples should cover references of the form:

```text
「...」 제27조
「...」 제20조제1항 별표 2
「...」 제46조제6항
```

Return structured reference data such as authority title, article, paragraph, annex, and source clause ID. Do not use the network or silently import current law.

**Step 2: Run RED**

```powershell
python -m pytest -q tests/unit/evidence/test_legal_reference_extraction.py
```

Expected: FAIL.

**Step 3: Implement deterministic extraction and local resolution**

At clause materialization/rebuild time, extract references from local clause text. Resolve only against already ingested documents/revisions/clauses. Create provenance links for resolved targets.

**Step 4: Distinguish absent-authority states**

Integration cases:

1. authority/document is ingested and referenced clause exists → traverse it;
2. authority/document is not ingested → `SOURCE_NOT_INGESTED`;
3. authority is ingested but referenced article/annex is absent/unmaterialized → `REFERENCE_TARGET_MISSING`.

In cases 2 and 3, the local citing clause remains valid selected evidence. Do not turn the entire issue into `RETRIEVAL_MISS`.

**Step 5: Run GREEN**

```powershell
python -m pytest -q tests/unit/evidence/test_legal_reference_extraction.py tests/integration/retrieval/test_external_reference_resolution.py tests/integration/retrieval/test_bounded_reference_traversal.py
```

Expected: PASS.

**Step 6: Commit**

```powershell
git add src/evidence_review/evidence/legal_references.py src/evidence_review/evidence/lineage_graph.py src/evidence_review/retrieval/graph.py src/evidence_review/retrieval/coverage.py tests/unit/evidence/test_legal_reference_extraction.py tests/integration/retrieval/test_external_reference_resolution.py
git commit -m "feat: resolve bounded legal references from local sources"
```

---

## Task 7 — Correct issue coverage and finalizer semantics for conditional/local-partial evidence

**Files:**
- Modify: `src/evidence_review/retrieval/coverage.py`
- Modify: `src/evidence_review/issue_coverage_binding.py`
- Modify: `src/evidence_review/abstention/issue_policy.py`
- Modify: `src/evidence_review/abstention/finalizer.py`
- Create: `tests/integration/review_question/test_real_issue_gap_semantics.py`
- Modify: `tests/unit/retrieval/test_coverage.py`
- Modify: `tests/unit/abstention/test_issue_partial_policy.py`

**Step 1: Write RED tests for I2**

Given evidence for 1,000㎡ and 250m/350m plus user facts 1,500㎡ and 300m, assert deterministic comparisons:

```text
1500 >= 1000  → true
300 > 250     → true
300 <= 350    → true
```

Expected issue state: `CONDITIONAL`, not `UNRESOLVED/RETRIEVAL_MISS`, unless evidence also establishes all discretionary designation conditions.

**Step 2: Write RED tests for I3/I4/I7 local evidence plus external gaps**

If the local Article 13 clause is found but the referenced external authority is absent:

- retain the supported local proposition in the issue result/Track A inputs;
- attach `SOURCE_NOT_INGESTED` or `REFERENCE_TARGET_MISSING`;
- do not emit `RETRIEVAL_MISS` for the local rule;
- do not invent the missing external numeric standard.

**Step 3: Run RED**

```powershell
python -m pytest -q tests/integration/review_question/test_real_issue_gap_semantics.py tests/unit/retrieval/test_coverage.py tests/unit/abstention/test_issue_partial_policy.py
```

Expected: FAIL.

**Step 4: Implement minimum coverage/finalizer changes**

Keep the existing global deterministic `RuleResult.missing_inputs` hard gate intact. Issue-scoped source/reference gaps may produce partial/conditional results, but may not suppress a genuine global missing-required-input condition.

**Step 5: Run GREEN + finalizer regressions**

```powershell
python -m pytest -q tests/integration/review_question/test_real_issue_gap_semantics.py tests/integration/abstention/test_finalizer.py tests/unit/abstention/test_issue_global_missing_input.py tests/unit/abstention/test_issue_partial_policy.py tests/unit/retrieval/test_coverage.py
```

Expected: PASS.

**Step 6: Commit**

```powershell
git add src/evidence_review/retrieval/coverage.py src/evidence_review/issue_coverage_binding.py src/evidence_review/abstention tests/integration/review_question/test_real_issue_gap_semantics.py tests/unit/retrieval/test_coverage.py
git commit -m "fix: distinguish retrieval and source gaps by issue"
```

---

## Task 8 — Make confidence reflect issue coverage and actual human-review state

**Files:**
- Modify: `src/evidence_review/confidence/coverage.py`
- Modify: `src/evidence_review/confidence/scorer.py`
- Modify: `src/evidence_review/confidence/policy.py`
- Modify: `tests/unit/confidence/test_issue_coverage_factors.py`
- Create: `tests/unit/confidence/test_review_completion_factor.py`
- Create: `tests/unit/confidence/test_issue_coverage_cap.py`
- Create: `tests/integration/review_question/test_real_confidence_semantics.py`

**Step 1: Write RED tests for absent human review**

When `human_decision is None`, assert that the human-review factor does not report `1.0`/complete.

**Step 2: Write RED tests for unresolved issue roles**

For 3 covered required rule roles out of 7, assert:

- input/issue completeness reflects the unresolved four roles;
- overall confidence cannot be `HIGH` around 0.91;
- a high score from unrelated factors cannot override the issue-coverage cap.

Do not hard-code a new arbitrary numeric weight unless existing policy semantics justify it. Prefer a deterministic cap/coverage factor directly tied to required-role completion.

**Step 3: Run RED**

```powershell
python -m pytest -q tests/unit/confidence/test_review_completion_factor.py tests/unit/confidence/test_issue_coverage_cap.py tests/integration/review_question/test_real_confidence_semantics.py
```

Expected: FAIL.

**Step 4: Implement actual completion semantics**

Rules:

- no human decision != completed human review;
- unresolved required evidence roles reduce completeness;
- severe issue gaps cap the final confidence level/score;
- confidence remains descriptive and cannot change the finalizer's deterministic evidence status.

Keep the current confidence contract version unless serialized fields must change. If the output schema changes, version it explicitly and add codec/backward-compatibility tests.

**Step 5: Run GREEN + existing confidence tests**

```powershell
python -m pytest -q tests/unit/confidence tests/integration/review_question/test_real_confidence_semantics.py
```

Expected: PASS.

**Step 6: Commit**

```powershell
git add src/evidence_review/confidence tests/unit/confidence tests/integration/review_question/test_real_confidence_semantics.py
git commit -m "fix: bind confidence to review and issue coverage"
```

---

## Task 9 — Replace synthetic-only acceptance with a production-shaped full pipeline E2E

**Files:**
- Create: `tests/integration/review_question/test_real_parser_workspace_full_e2e.py`
- Modify: `tests/integration/retrieval/test_real_review_retrieval_relevance.py`
- Modify: `tests/integration/review_question/test_real_review_full_e2e.py`
- Reuse: `tests/fixtures/real_parser_workspace_retrieval/`

**Step 1: Write the full E2E before final cleanup**

The E2E must begin from an element-only parser-shaped snapshot. It must not manually construct the clauses/links that production code is supposed to derive.

Pipeline under test:

```text
parser-shaped elements
→ clause materialization/backfill
→ fresh clause index
→ QuestionPlan with contaminated/noisy requests
→ issue-aware retrieval
→ bounded sibling/reference expansion
→ issue coverage
→ Track A
→ Track B
→ finalizer
→ confidence
```

**Step 2: Assert the real acceptance outcomes**

At minimum:

```python
assert count("clauses") > 0
assert count("clause_retrieval_records") > 0
assert count("clause_fts") > 0

assert comparison("1500 >= 1000").satisfied
assert comparison("300 > 250").satisfied
assert comparison("300 <= 350").satisfied

assert issue("I2").status == "CONDITIONAL"
assert issue("I2").gap_codes != ("RETRIEVAL_MISS",)

assert has_local_rule_evidence("I3")
assert has_local_rule_evidence("I4")
assert has_local_rule_evidence("I7")
```

If external referenced authorities are deliberately absent, assert the appropriate source/reference gap rather than a fabricated detailed answer.

Also assert:

- all final claim citations overlap claim issue lineage;
- unrelated 364-household formula / unrelated contribution / non-residential-location evidence is excluded;
- retrieval trace contains the literal failed query plus successful bounded fallback and zero-hit stages;
- confidence is not HIGH when material required roles remain unresolved;
- page/bbox citation lineage points back to the original parser element.

**Step 3: Add a second reference-complete variant**

With minimal external-authority fixture elements ingested, prove that the same local Article 13 reference resolves and the issue can progress from source/reference gap to resolved/conditional as supported. This isolates retrieval correctness from source availability.

**Step 4: Run the new E2E**

```powershell
python -m pytest -q tests/integration/review_question/test_real_parser_workspace_full_e2e.py
```

Expected: PASS only after Tasks 1–8 are complete.

**Step 5: Run both old and new acceptance suites**

```powershell
python -m pytest -q tests/integration/retrieval/test_real_review_retrieval_relevance.py tests/integration/review_question/test_real_review_full_e2e.py tests/integration/review_question/test_real_parser_workspace_full_e2e.py
```

Expected: PASS. Keep the older synthetic tests as focused unit/integration guards, but treat the new production-shaped E2E as the merge acceptance authority for this failure.

**Step 6: Commit**

```powershell
git add tests/fixtures/real_parser_workspace_retrieval tests/integration/retrieval/test_real_review_retrieval_relevance.py tests/integration/review_question/test_real_review_full_e2e.py tests/integration/review_question/test_real_parser_workspace_full_e2e.py
git commit -m "test: verify real parser workspace review end to end"
```

---

## Task 10 — Documentation, exact-head preflight, and PR readiness

**Files:**
- Modify: `docs/plans/2026-08-16-real-review-retrieval-relevance-fix.md`
- Modify: `docs/superpowers/plans/2026-08-16-real-workspace-clause-retrieval-repair.md` only for final completion notes if needed
- Update PR #115 body/comment after observed verification

**Step 1: Run the affected slice on the exact candidate HEAD**

```powershell
python -m pytest -q `
  tests/unit/evidence/test_clause_materialization.py `
  tests/integration/evidence/test_parser_clause_materialization.py `
  tests/integration/migration/test_v4_clause_backfill.py `
  tests/integration/retrieval/test_clause_index_rebuild.py `
  tests/unit/retrieval/test_rule_query_compiler.py `
  tests/integration/retrieval/test_adaptive_fallback.py `
  tests/integration/retrieval/test_bounded_article_sibling_expansion.py `
  tests/integration/retrieval/test_external_reference_resolution.py `
  tests/integration/review_question/test_real_issue_gap_semantics.py `
  tests/integration/review_question/test_real_confidence_semantics.py `
  tests/integration/review_question/test_real_parser_workspace_full_e2e.py
```

Expected: all PASS.

**Step 2: Run static verification**

```powershell
python -m ruff check src tests
python -m mypy src/evidence_review
python -m compileall -q src
```

Expected: PASS/no output from compileall.

**Step 3: Run full Python 3.13 suite**

```powershell
python -m pytest -q
```

Record exact pass/skip counts and inspect every skip reason; do not infer success from an older HEAD.

**Step 4: Re-run repository acceptance gates**

Verify on the same HEAD:

- documentation integrity;
- SQLite integrity/FK;
- schema migration if schema changed;
- v4 element-only clause backfill;
- stale-index fail-closed behavior;
- clause retrieval rebuild/freshness;
- production-shaped E2E;
- partial-answer E2E;
- exact citation/page/bbox lineage.

Use the repository's existing commands/tests for these checks; do not invent a PASS for anything not observed.

**Step 5: Record exact-head evidence**

```powershell
git status --short
git rev-parse HEAD
```

Requirements:

- working tree clean;
- exact SHA recorded in PR #115;
- previous `eb7c626...` verification explicitly remains superseded;
- new test counts and static-check outputs recorded.

**Step 6: Update PR state only after all gates pass**

Move PR #115 from Draft back to Ready for review only after the exact-head results above are observed. Do not merge without an explicit user request.

**Step 7: Final commit for documentation/status files if changed**

```powershell
git add docs
 git commit -m "docs: record real workspace retrieval verification"
```

If this final documentation commit changes HEAD, repeat the exact-head verification needed by repository policy before calling the PR verified.

---

## Acceptance matrix

| Case | Required final behavior |
| --- | --- |
| Real parser workspace has elements but no clauses | Deterministic backfill derives clauses/links and builds fresh clause index |
| I2 query contains user fact `300m` | Literal attempt retained; fact-safe fallback retrieves 250m/350m rule |
| 1,500㎡ / 1,000㎡ | Deterministic comparison proves minimum-area condition |
| 300m / 250m / 350m | Deterministic comparisons support `CONDITIONAL` issue state |
| I3 wording differs from source terminology | Bounded query fallback retrieves local parking rule without unrestricted OR |
| I4 rule spans adjacent paragraphs | Same-article structural expansion retrieves both relevant paragraphs under budget |
| I7 includes `추가 ... 요건 절차` noise | Intent-pruned/core-token fallback retrieves district-unit-plan clause |
| Local clause cites missing external authority | Preserve local claim; emit `SOURCE_NOT_INGESTED` or `REFERENCE_TARGET_MISSING`, not `RETRIEVAL_MISS` |
| External authority is ingested | Resolve and traverse target with provenance under depth/node/fanout budgets |
| Human decision absent | Human-review completion factor is not 1.0 |
| 3/7 required issue roles covered | Confidence cannot report HIGH ~0.91 |
| Final claims | Every claim/citation retains issue-lineage overlap and unrelated evidence stays excluded |
| Final PR readiness | New exact-head full suite/static/docs/migration/rebuild/E2E evidence recorded |

## Completion definition

This repair is complete only when the production-shaped element-only E2E passes without manually seeding clauses or links, the actual contaminated planner query still retrieves the correct rule thresholds, I3/I4/I7 retrieve their local clauses, external source gaps are diagnosed precisely, confidence reflects unresolved coverage, and all repository gates pass on one exact final HEAD.
