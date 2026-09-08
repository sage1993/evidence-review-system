# Issue #155 — Immutable Evidence Finalization and Read-Only Review Design

## 1. Purpose

Issue #155 identified a trust-boundary defect in the Evidence Review System lifecycle: the active workspace binds the exact `evidence/evidence.sqlite` physical identity, but a later planned-review preparation mutates that same database by materializing derived clauses, links, and retrieval state.

The approved architecture is **Option A**:

> Complete all deterministic derived evidence/retrieval materialization before the workspace is bound, then treat the bound evidence database as immutable and read-only for the entire review lifecycle.

This design keeps the current single-database architecture and avoids introducing a separate retrieval database or a phase-specific physical hash model.

Base reviewed for this design:

```text
main = 55362c9217046f4c1fd7e756b5aca7792e543b4e
issue = #155
```

---

## 2. Proven Failure

The current lifecycle has two incompatible contracts.

### Active workspace contract

`ActiveWorkspaceBinding` records both:

- logical evidence snapshot identity;
- exact evidence database SHA-256.

The binding therefore asserts that the selected workspace points to one exact evidence database artifact.

### Planned review contract

`prepare_planned_review_question()` currently opens the bound database and executes `ensure_clause_index(connection)` before retrieval.

`ensure_clause_index()` can write:

- derived rows in `clauses`;
- derived rows in `links`;
- rebuilt retrieval/index state;
- derived legal-reference links.

Therefore a normal review can change the physical bytes of the database after the exact database SHA was bound.

Observed production evidence from Issue #155:

```text
initial corpus DB SHA-256:
a959e22dc1436c1a119e7ce3172cd2c9bed3486b541167f363651e9946d128e

post-review-materialization DB SHA-256:
9b9ee6218207ae24b6ec0d9ef3a89332481237bc419695fac483cb317629df01

repeated stored snapshot identity:
e2b11cf36fc55ae80f3cae5f3206268b9422f2d0753992bd065c9686aeacf5dc
```

The SQLite database remained structurally valid. The defect is lifecycle ownership, not proven corruption.

---

## 3. Design Decision

The evidence database has two phases only:

```text
BUILDING
  ↓
FINALIZED / FROZEN
```

All write-capable evidence operations occur before `FINALIZED`.

After finalization:

```text
$ERS_PDF / corpus preparation
    → parser evidence ingest
    → derived clause/link materialization
    → retrieval/index materialization
    → final logical snapshot hash
    → final index freshness verification
    → SQLite integrity verification
    → close database
    → publish exact DB artifact
    → compute exact on-disk DB SHA-256
    → bind active workspace
    → FREEZE

$ERS_REVIEW
    → resolve active workspace
    → open evidence DB read-only
    → verify finalization + snapshot + index + exact file SHA
    → retrieve
    → Track A
    → Track B
    → finalizer
    → viewer/server
    → no evidence DB writes
```

The review path must never repair, backfill, migrate, rebuild, checkpoint, normalize, or otherwise mutate the bound evidence database.

---

## 4. Authority and Identity Model

### 4.1 Source identity

Existing revision/source hashes continue to identify exact ingested source bytes.

They are not replaced by the database hash.

### 4.2 Logical evidence snapshot identity

`evidence_snapshot_hash` represents the canonical logical evidence state after deterministic evidence-layer derivation is complete.

For the current schema, the canonical logical state includes the existing `SNAPSHOT_TABLES` set, including:

- `documents`
- `revisions`
- `pages`
- `elements`
- `clauses`
- `tables`
- `visuals`
- `links`
- `review_flags`

It excludes purely derived retrieval storage such as FTS/index tables and metadata tables.

A finalized database is invalid if:

```text
snapshot_meta['snapshot_hash'] != compute_snapshot_hash(current logical rows)
```

This closes the current gap where clauses/links may be added after the stored logical snapshot hash was produced.

### 4.3 Retrieval index identity

`retrieval_meta['snapshot_hash']` must equal the final logical `evidence_snapshot_hash`.

The retrieval index is valid only for that exact logical snapshot.

Required invariant:

```text
retrieval_meta.snapshot_hash
== snapshot_meta.snapshot_hash
== compute_snapshot_hash(database logical rows)
```

### 4.4 Physical evidence database identity

`evidence_db_sha256` identifies the exact finalized SQLite file artifact used by the active workspace and release/package binding.

It must be computed from the **exact on-disk file bytes after the writer connection is closed**.

It must not be defined as `connection.serialize()` and must not be stored inside the same database as a self-referential physical hash.

The exact file SHA belongs in external control/provenance state such as:

- `.ers/active-workspace.json`;
- release/package manifests;
- acceptance evidence.

### 4.5 Identity roles

The two main hashes have different authoritative purposes:

| Identity | Authoritative meaning |
| --- | --- |
| `evidence_snapshot_hash` | canonical logical evidence equivalence |
| `evidence_db_sha256` | exact frozen SQLite artifact identity |

Two independently rebuilt databases may legitimately have the same logical snapshot hash while having different physical SQLite byte layouts. That is not an integrity failure by itself.

However, once one exact database artifact is bound as active, its `evidence_db_sha256` must remain unchanged for the complete active review lifetime.

---

## 5. Finalization Boundary

Introduce one explicit evidence finalization boundary owned by corpus preparation.

A centralized finalization operation should own the following sequence. Existing `ensure_clause_index()` logic may be reused or decomposed inside this BUILDING-only boundary, but it is no longer permitted as a review-time repair operation.

### Phase 1 — parser/source ingest

Create the temporary database and ingest parser-produced source truth.

At this point the database is still mutable and must not be bound as active.

### Phase 2 — deterministic clause and structural-link materialization

Materialize deterministic evidence-layer state that does not require the clause retrieval projection, including:

- legal clauses/subclauses derived from elements;
- source-element links;
- structural parent/sibling relationships;
- other deterministic clause/link artifacts that can be derived directly from parser evidence.

Parser elements remain source truth. Derived clauses and links remain deterministic projections with provenance.

### Phase 3 — provisional retrieval build and reference-link materialization

Some legal-reference resolution currently depends on `clause_retrieval_records` and `clause_evidence_links`. Therefore, while the database is still in BUILDING state:

1. build the provisional retrieval/clause projection needed for reference resolution;
2. materialize explicit legal-reference links such as `rule_source`, `source_not_ingested`, and `reference_target_missing`;
3. complete any remaining deterministic `links` mutations.

This provisional retrieval state has no authority outside finalization. The resulting reference links are canonical snapshot rows and therefore must exist before the final logical snapshot hash is committed.

### Phase 4 — final logical snapshot commit

After all snapshot-table mutations are complete:

1. compute `compute_snapshot_hash()` from the resulting logical rows;
2. replace `snapshot_meta['snapshot_hash']` with this final logical hash;
3. mark the database finalized with lifecycle metadata:

```text
snapshot_meta['lifecycle_state'] = 'FINALIZED'
snapshot_meta['finalization_version'] = '1'
```

No schema version bump is required because `snapshot_meta` already supports arbitrary key/value metadata.

### Phase 5 — final retrieval rebuild

Rebuild the retrieval/index projection using the final logical snapshot hash.

Then require:

```text
require_fresh_index(connection) == final_snapshot_hash
```

The final retrieval rebuild may change retrieval/FTS tables but must not change any canonical snapshot table.

### Phase 6 — final consistency verification

Before the database writer is closed, verify:

- `compute_snapshot_hash()` still equals the final stored snapshot hash;
- `retrieval_meta.snapshot_hash` equals the final snapshot hash;
- current schema is supported;
- `PRAGMA integrity_check` returns `ok`;
- `PRAGMA foreign_key_check` returns no violations;
- finalization metadata is present and valid.

If any invariant fails, corpus preparation fails and the database is not published or bound.

### Phase 7 — publish and bind

After successful finalization:

1. close the SQLite writer connection;
2. publish the database through the existing create-only publication boundary;
3. compute SHA-256 over the exact published file bytes;
4. construct the active workspace binding using the final logical snapshot hash and exact file SHA;
5. only then expose the workspace to `$ERS_REVIEW`.

---

## 6. Read-Only Review Boundary

### 6.1 EvidenceStore read-only mode

The storage layer must support an explicit read-only open mode.

The intended SQLite boundary is:

```text
URI mode=ro
+
PRAGMA query_only = ON
```

`PRAGMA foreign_keys = ON` may remain connection-local.

Read-only mode must not silently fall back to `mode=rw`.

### 6.2 Review-owned readers

All evidence-database opens after active binding must use read-only mode, including at minimum the paths responsible for:

- planned review retrieval;
- legacy/deterministic review-question retrieval where it consumes an existing workspace;
- active workspace revalidation;
- final review packet/reference projection that reads the evidence DB;
- viewer/server paths that read evidence content.

Write-capable modes remain available only to explicit corpus creation, migration, or maintenance operations before a workspace is frozen.

### 6.3 No review-time repair

Remove `ensure_clause_index()` from planned review preparation.

If required derived state is absent or stale, review must fail closed rather than repairing the database in place.

A bound workspace is evidence authority, not a cache repair target.

---

## 7. Finalized Database Validation

Add one reusable validation boundary for a finalized evidence database.

It must verify at least:

1. supported schema;
2. `snapshot_meta.lifecycle_state == FINALIZED`;
3. supported `finalization_version`;
4. stored logical snapshot hash equals recomputed logical snapshot hash;
5. retrieval index hash equals logical snapshot hash;
6. SQLite integrity and required relational invariants;
7. when validating an active binding, exact on-disk file SHA equals the bound `evidence_db_sha256`.

Recommended stable failure classes:

```text
EVIDENCE_DATABASE_NOT_FINALIZED
EVIDENCE_LOGICAL_SNAPSHOT_MISMATCH
EVIDENCE_INDEX_STALE
ACTIVE_WORKSPACE_STALE
```

Existing more-specific schema or filesystem-trust errors remain valid where applicable.

---

## 8. Active Workspace Binding

`bind_active_workspace()` must only accept a finalized evidence database.

The binding sequence must not rely on a writable open.

The stored binding continues to include:

- workspace path;
- final logical evidence snapshot hash;
- exact on-disk evidence DB SHA-256;
- schema version;
- retrieval record count;
- clause record count.

`resolve_active_workspace()` must revalidate the same values without changing the database.

Any mismatch fails closed before substantive review begins.

---

## 9. Legacy Workspace Policy

Pre-fix workspaces are not silently upgraded during review.

A workspace without finalized lifecycle metadata, or with a stored logical snapshot hash that no longer matches its current logical rows, is treated as legacy/unfinalized authority.

The default recovery path is:

```text
rerun corpus preparation / $ERS_PDF
→ produce a newly finalized DB artifact
→ bind the new workspace state
→ review
```

An explicit in-place or copy-on-write migration command may be designed later if operational demand justifies it, but it is not required for Issue #155 closure.

This keeps automatic repair outside the review trust boundary.

---

## 10. Release and Attestation Contract

Issue #155 requires one unambiguous authoritative database identity for an exact release artifact.

The contract is:

```text
exact packaged evidence.sqlite identity
= SHA-256 of finalized on-disk file bytes
```

The logical snapshot hash remains the semantic/canonical evidence identity, but it is not a substitute for exact artifact hashing.

Release/package validation must therefore bind the physical DB SHA when the database file itself is part of the accepted artifact set.

No release workflow may accept a database whose physical SHA differs from the bound/manifest value merely because its logical snapshot hash is unchanged.

---

## 11. Required Regression Coverage

### 11.1 Finalization tests

A fresh parser-shaped source batch must produce a published database where:

- derived clauses/links required by planned retrieval already exist;
- `snapshot_meta.snapshot_hash == compute_snapshot_hash()`;
- `retrieval_meta.snapshot_hash == snapshot_meta.snapshot_hash`;
- finalization metadata is present;
- integrity and foreign-key checks pass.

### 11.2 Review read-only tests

For a finalized workspace:

- planned review prepare succeeds without calling any evidence writer;
- a direct write attempted through a review-owned connection fails;
- no review stage creates persistent `-wal`, `-shm`, or `-journal` side effects or changes the authoritative database file bytes;
- absence/staleness of derived state causes fail-closed validation, not automatic repair.

### 11.3 Active binding tests

Record the final DB SHA at bind time and prove it is unchanged after:

```text
review prepare
Track A submission
Track B submission
finalization
review packet/viewer open
```

The binding must continue to resolve successfully at each stage.

### 11.4 Tamper tests

After binding, modify or replace the database artifact and verify that active workspace resolution or review preflight fails before retrieval.

### 11.5 Legacy tests

An old-style element-only/unfinalized workspace must fail with the finalized-database error and must not be mutated by review.

### 11.6 Existing regression suites

The implementation must preserve current retrieval, citation, Track A/Track B, reference-viewer, filesystem-trust, and schema behavior unless this design explicitly changes the lifecycle boundary.

---

## 12. Real-Environment Acceptance for Issue #155

Issue #155 is not closed on unit tests alone.

On a fresh real workspace, record the exact `evidence/evidence.sqlite` file SHA-256 at these checkpoints:

```text
A. corpus finalization complete, before active bind
B. immediately after active bind
C. review prepare complete
D. Track A accepted
E. Track B accepted
F. final review packet complete
G. viewer/server opened and closed
```

Acceptance requires:

```text
SHA_A == SHA_B == SHA_C == SHA_D == SHA_E == SHA_F == SHA_G
```

Also verify:

```text
stored logical snapshot hash == recomputed logical snapshot hash
retrieval index hash == logical snapshot hash
PRAGMA integrity_check == ok
PRAGMA foreign_key_check == []
```

The exact active binding DB SHA must equal the measured file SHA at every checkpoint.

---

## 13. Out of Scope

The following are intentionally excluded from Issue #155:

- splitting evidence and retrieval into separate SQLite databases;
- introducing schema v5 solely for finalization state;
- allowing phase-specific active-workspace DB hashes;
- review-time automatic migration or repair;
- unrelated retrieval ranking, planner, confidence, or UI changes;
- requiring byte-identical SQLite output across independent machines/builds when logical snapshot identity is equal.

The invariant is exact-byte stability **after one artifact is finalized and bound**, not universal SQLite reproducible-build equivalence.

---

## 14. Completion Criteria

Issue #155 is complete only when all of the following are true:

```text
ROOT_CAUSE = PROVEN
CORPUS_FINALIZATION_OWNS_DERIVED_WRITES = PASS
FINAL_LOGICAL_SNAPSHOT_HASH = VERIFIED
FINAL_RETRIEVAL_INDEX_BINDING = VERIFIED
ACTIVE_DB_PHYSICAL_SHA = AUTHORITATIVE
REVIEW_EVIDENCE_DB_MODE = READ_ONLY
REVIEW_TIME_DB_MUTATION = 0
LEGACY_UNFINALIZED_WORKSPACE = FAIL_CLOSED
REAL_WORKSPACE_HASH_STABILITY = PASS
RELEASE_DB_IDENTITY_CONTRACT = UNAMBIGUOUS
```

No bound evidence database may be mutated as part of a successful review lifecycle.