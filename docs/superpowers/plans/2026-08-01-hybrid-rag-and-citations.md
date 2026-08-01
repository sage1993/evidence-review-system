# Hybrid RAG and Citation Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retrieve evidence through lexical, structured, and relation channels, fuse results deterministically, and reject uncited or unresolved factual claims.

**Architecture:** SQLite FTS5 handles BM25 lexical retrieval; structured filters search exact metadata; bounded graph traversal adds parent, exception, cited clause, table, visual, and rule-source records. Optional LLM query expansions are untrusted inputs and cannot bypass deterministic ranking.

**Tech Stack:** Python 3.11+, SQLite FTS5, Unicode NFC normalization, JSON, pytest.

## Global Constraints

- Retrieval returns evidence records, not final answers.
- Ranking ties use stable IDs.
- Every hit includes source identity, page, bbox, hash, channel score, and final score.
- Every factual claim requires one or more resolvable citation IDs.

---

### Task 1: FTS5 Index

**Files:** Create `src/ansim_review/retrieval/index.py`; modify `src/ansim_review/evidence/schema.sql`; test `tests/integration/retrieval/test_fts_retrieval.py`.

- [ ] Write a Korean query test for `이면도로 차량 진출입` returning page-resolved hits.
- [ ] Run and observe missing FTS table failure.
- [ ] Index raw text, normalized text, and title; record evidence snapshot hash; normalize to NFC.
- [ ] Run retrieval and stale-index tests.
- [ ] Commit: `git commit -m "feat: index evidence with sqlite fts5"`.

### Task 2: Query Normalization and Expansion Contract

**Files:** Create `src/ansim_review/retrieval/query.py`; test `tests/unit/retrieval/test_query_normalization.py`.

- [ ] Test whitespace collapse, NFC, exact deduplication, and separation of approved synonyms from `origin=llm` expansions.
- [ ] Run and observe failure.
- [ ] Implement `normalize_query(primary, expansions, synonym_manifest)` without stemming guesses.
- [ ] Run tests.
- [ ] Commit: `git commit -m "feat: normalize traceable retrieval queries"`.

### Task 3: Structured and Relation Retrieval

**Files:** Create `src/ansim_review/retrieval/structured.py`, `src/ansim_review/retrieval/graph.py`; test `tests/integration/retrieval/test_structured_graph_retrieval.py`.

- [ ] Test a seed clause expands to its linked exception and related visual/table.
- [ ] Run and observe failure.
- [ ] Implement depth-limited traversal (default 1, maximum 3), visited-set, relation priorities, and stable ordering.
- [ ] Run tests.
- [ ] Commit: `git commit -m "feat: retrieve structured and linked evidence"`.

### Task 4: Deterministic Fusion

**Files:** Create `src/ansim_review/retrieval/fusion.py`; test `tests/integration/retrieval/test_hybrid_fusion.py`.

**V1 weights:** structured exact 1.00, clause-ID match 0.95, rule-source relation 0.90, FTS normalized rank 0.70, linked visual/table 0.60.

- [ ] Write a tie test proving `E1` sorts before `E2` at equal score.
- [ ] Run and observe failure.
- [ ] Implement channel score preservation and stable weighted fusion; unrelated documents must not reorder existing equal evidence.
- [ ] Run twice and compare JSON bytes.
- [ ] Commit: `git commit -m "feat: fuse hybrid evidence deterministically"`.

### Task 5: Citation Resolver and Claim Validator

**Files:** Create `src/ansim_review/retrieval/citations.py`, `src/ansim_review/retrieval/claims.py`; test `tests/unit/retrieval/test_claim_citations.py`.

- [ ] Test `UNCITED_CLAIM`, `CITATION_PAGE_MISMATCH`, `SOURCE_HASH_MISMATCH`, and bbox mismatch.
- [ ] Run and observe failure.
- [ ] Resolve exact document revision/page/evidence ID/hash and bbox within 0.01 points.
- [ ] Run tests.
- [ ] Commit: `git commit -m "feat: enforce source citations for claims"`.

### Task 6: Query CLI and Evidence Bundle

**Files:** Create `src/ansim_review/retrieval/bundle.py`; modify `src/ansim_review/cli.py`; test `tests/integration/retrieval/test_query_cli.py`.

**Interface:** `python -m ansim_review query --db evidence.sqlite --request question.json --output retrieved-evidence.json`.

- [ ] Test output includes query origins, channel scores, snapshot hash, and citations for every hit.
- [ ] Run and observe missing-command failure.
- [ ] Implement and refuse output when FTS and evidence snapshot hashes differ.
- [ ] Run all retrieval tests.
- [ ] Commit: `git commit -m "feat: export hybrid retrieval evidence bundles"`.
