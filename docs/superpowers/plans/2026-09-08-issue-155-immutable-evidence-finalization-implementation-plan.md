# Issue #155 Immutable Evidence Finalization Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Move all deterministic clause/link/index writes into corpus finalization, bind the exact finalized `evidence.sqlite` artifact, and make every successful formal-review path read-only so the active database SHA-256 remains stable through the complete review lifecycle.

**Architecture:** Preserve the current single schema-v4 evidence database. Introduce an explicit BUILDING → FINALIZED boundary owned by source-batch/corpus preparation. Complete clause, structural-link, legal-reference, and retrieval materialization before committing the final logical snapshot hash. Rebuild retrieval against that final hash, close the writer, publish create-only, then hash the exact on-disk database bytes. Active workspace binding and all post-bind review readers open the finalized database read-only and fail closed instead of repairing it.

**Tech Stack:** Python 3.13, SQLite/FTS5, pytest, Ruff, strict mypy, canonical JSON/SHA-256, existing `EvidenceStore`, source-batch v2, QuestionPlan/review-question flow, protected loopback Review Workspace.

**Approved design:** `docs/superpowers/specs/2026-09-08-issue-155-immutable-evidence-finalization-design.md`

**Reviewed design baseline:** `main@55362c9217046f4c1fd7e756b5aca7792e543b4e`

**Issue:** #155

---

## 1. Non-negotiable invariants

Implementation is correct only if all of these hold:

```text
snapshot_meta.snapshot_hash
== compute_snapshot_hash(final canonical snapshot tables)
== retrieval_meta.snapshot_hash

snapshot_meta.lifecycle_state == FINALIZED
snapshot_meta.finalization_version == 1

active-workspace.evidence_db_sha256
== SHA256(exact finalized on-disk evidence.sqlite bytes)

successful review-time evidence DB writes == 0
```

`evidence_snapshot_hash` and `evidence_db_sha256` remain separate authorities:

- `evidence_snapshot_hash`: canonical logical evidence state.
- `evidence_db_sha256`: exact frozen SQLite artifact selected by the active workspace.

Do not use `connection.serialize()` as the authoritative physical file hash. Compute the physical hash from the verified database file after the writer connection is closed.

Do not introduce schema v5 solely for lifecycle metadata. Use existing `snapshot_meta` key/value storage.

Do not silently upgrade or repair an unfinalized workspace during review. Recovery is a new `$ERS_PDF`/source-batch preparation unless a separate migration feature is later approved.

---

## 2. Execution discipline

At execution time, first re-confirm repository state. Do not assume this planning branch is still based on the latest `main`.

```powershell
git fetch origin
git rev-parse origin/main
git rev-parse design/issue-155-immutable-evidence-finalization
git status --short
```

Create an isolated implementation worktree/branch named:

```text
fix/issue-155-immutable-evidence-finalization
```

If `origin/main` has moved, start from the new `origin/main` and port the approved design/plan documents before production work. Do not reset, discard, or include unrelated dirty user changes.

Every implementation Task below follows this sequence:

1. write/modify the smallest failing test;
2. run that test and record the expected RED reason;
3. implement the smallest root-cause correction;
4. run the focused test to GREEN;
5. run adjacent regression suites;
6. `git diff --check`;
7. commit the task.

Do not weaken an existing test simply because it encodes the old review-time repair behavior. Where the old oracle is now invalid, replace it with the approved frozen-authority contract and explain the oracle change in the commit/PR.

---

# Task 0 — Bootstrap the exact implementation baseline

**Files:** none.

### Step 1: Create the isolated worktree

Use the repository's standard worktree flow. Record:

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
git log -1 --oneline
```

Expected: clean implementation worktree, exact base recorded.

### Step 2: Verify the approved design is present

```powershell
Test-Path docs/superpowers/specs/2026-09-08-issue-155-immutable-evidence-finalization-design.md
Test-Path docs/superpowers/plans/2026-09-08-issue-155-immutable-evidence-finalization-implementation-plan.md
```

Expected: both `True`.

### Step 3: Record the pre-change focused baseline

Run only existing relevant suites; this is not final acceptance.

```powershell
py -3.13 -m pytest -q tests/unit/evidence/test_store.py tests/unit/evidence/test_snapshot.py tests/unit/parsing/test_source_batch_importer.py tests/unit/review_question/test_planned_snapshot_provenance.py tests/integration/review_question/test_real_workspace_clause_repair_e2e.py
```

Record actual result. Do not claim overall PASS from this baseline subset.

---

# Task 1 — RED: lock the lifecycle defect and new fail-closed contract

**Files:**

- Modify: `tests/integration/review_question/test_real_workspace_clause_repair_e2e.py`
- Create: `tests/integration/evidence/test_frozen_evidence_lifecycle.py`

### Step 1: Replace the old review-time-repair oracle

The existing `test_element_only_real_workspace_reaches_finalizer_with_all_issue_lineage` currently proves the defect: it creates an element-only DB, calls `prepare_planned_review_question()`, then asserts that review created clauses.

Split that behavior into two tests:

1. an **unfinalized legacy workspace** test that records the DB file SHA/bytes, calls planned review, expects a stable finalized-database failure, and proves the DB bytes did not change;
2. a **finalized workspace** E2E test where clause/index derivation has already happened before planned review and the existing issue-lineage/retrieval assertions continue to pass.

The unfinalized assertion should converge on this contract:

```python
before = hashlib.sha256(database.read_bytes()).hexdigest()

with pytest.raises(EvidenceDatabaseNotFinalized, match="EVIDENCE_DATABASE_NOT_FINALIZED"):
    prepare_planned_review_question(workspace, plan)

after = hashlib.sha256(database.read_bytes()).hexdigest()
assert after == before
```

Use the final exception type/API introduced in Task 2; until then import through `importlib` or assert the stable reason string so this test can be committed RED without fake production stubs.

### Step 2: Add source/corpus finalization expectations

In `tests/integration/evidence/test_frozen_evidence_lifecycle.py`, construct a parser-shaped/element-only schema-v4 DB and specify the target state after finalization:

```text
clauses > 0
clause_retrieval_records > 0
snapshot_meta.lifecycle_state == FINALIZED
snapshot_meta.finalization_version == 1
stored snapshot hash == recomputed snapshot hash
retrieval hash == stored snapshot hash
PRAGMA integrity_check == ok
PRAGMA foreign_key_check == []
```

Also assert that a finalized read does not change the file SHA.

### Step 3: Run RED

```powershell
py -3.13 -m pytest -v tests/integration/review_question/test_real_workspace_clause_repair_e2e.py tests/integration/evidence/test_frozen_evidence_lifecycle.py
```

Expected current-code failure class:

- planned review still repairs/mutates the element-only DB; and/or
- explicit finalization lifecycle APIs/metadata do not exist.

Do not proceed if the tests fail for fixture syntax or unrelated setup errors; correct the test until RED demonstrates the intended old behavior.

### Step 4: Commit the RED contract

```powershell
git add tests/integration/review_question/test_real_workspace_clause_repair_e2e.py tests/integration/evidence/test_frozen_evidence_lifecycle.py
git commit -m "test: lock frozen evidence lifecycle regression"
```

---

# Task 2 — Add one explicit evidence finalization authority

**Files:**

- Create: `src/evidence_review/evidence/finalization.py`
- Create: `tests/unit/evidence/test_finalization.py`
- Modify as needed only for narrow reusable primitives: `src/evidence_review/evidence/clause_rebuild.py`

### Step 1: Write unit RED for finalization ordering

Create a parser-shaped element-only snapshot containing text that derives at least one legal clause and one explicit legal reference. Assert finalization produces the final canonical state before committing the snapshot hash.

Required cases:

- element-only DB becomes finalized with derived clauses;
- legal-reference `links` exist before final snapshot hash is committed;
- final snapshot hash equals `compute_snapshot_hash(store)`;
- retrieval hash equals final snapshot hash;
- lifecycle metadata is exact;
- a second `validate_finalized_evidence()` is read-only/idempotent;
- missing lifecycle metadata raises `EVIDENCE_DATABASE_NOT_FINALIZED`;
- canonical-row tamper raises `EVIDENCE_LOGICAL_SNAPSHOT_MISMATCH`;
- retrieval hash tamper raises `EVIDENCE_INDEX_STALE`.

Run and confirm RED:

```powershell
py -3.13 -m pytest -v tests/unit/evidence/test_finalization.py
```

### Step 2: Implement the finalization API

Use an API equivalent to:

```python
FINALIZATION_VERSION = "1"

@dataclass(frozen=True, slots=True)
class FinalizedEvidenceState:
    snapshot_hash: str
    schema_version: int
    retrieval_record_count: int
    clause_record_count: int

class EvidenceDatabaseNotFinalized(RuntimeError): ...
class EvidenceLogicalSnapshotMismatch(RuntimeError): ...
class EvidenceIndexStale(RuntimeError): ...


def finalize_evidence_database(store: EvidenceStore) -> FinalizedEvidenceState:
    ...


def validate_finalized_evidence(store: EvidenceStore) -> FinalizedEvidenceState:
    ...
```

Keep stable reason tokens in exception messages:

```text
EVIDENCE_DATABASE_NOT_FINALIZED
EVIDENCE_LOGICAL_SNAPSHOT_MISMATCH
EVIDENCE_INDEX_STALE
```

### Step 3: Implement the BUILDING-only ordering exactly

The finalizer must perform this sequence:

```text
A. parser rows already ingested
B. derive clauses + source/structural links
C. provisional build_fts_index if reference resolution requires clause projections
D. materialize_legal_reference_links
E. all canonical SNAPSHOT_TABLES mutations are now complete
F. final_snapshot_hash = compute_snapshot_hash(store)
G. INSERT OR REPLACE snapshot_meta.snapshot_hash = final_snapshot_hash
H. retain/update database_snapshot_hash to the same final value while compatibility requires it
I. set lifecycle_state=FINALIZED and finalization_version=1
J. final build_fts_index(connection)
K. require_fresh_index(connection) == final_snapshot_hash
L. recompute compute_snapshot_hash(store) and require equality
M. PRAGMA integrity_check == ok
N. PRAGMA foreign_key_check == []
```

Important: `materialize_legal_reference_links()` writes canonical `links`; therefore it must occur **before** step F. A final retrieval rebuild after step I may mutate retrieval/FTS projection tables but must not change any `SNAPSHOT_TABLES` row.

`ensure_clause_index()` may be reused internally while the DB is BUILDING, but it must not be treated as a post-finalization repair API.

### Step 4: Implement read-only validation

`validate_finalized_evidence()` must not rebuild or repair anything. It verifies:

- supported schema;
- lifecycle metadata;
- stored snapshot hash vs recomputed current canonical hash;
- retrieval hash vs stored snapshot hash;
- SQLite integrity/foreign keys;
- counts needed by provenance.

It must work against a query-only/read-only connection introduced in Task 4.

### Step 5: Run focused GREEN

```powershell
py -3.13 -m pytest -v tests/unit/evidence/test_finalization.py tests/unit/evidence/test_clause_rebuild.py tests/unit/evidence/test_snapshot.py
```

### Step 6: Commit

```powershell
git add src/evidence_review/evidence/finalization.py src/evidence_review/evidence/clause_rebuild.py tests/unit/evidence/test_finalization.py
git diff --check
git commit -m "feat: add evidence database finalization boundary"
```

---

# Task 3 — Finalize source-batch DB before create-only publication

**Files:**

- Modify: `src/evidence_review/parsing/source_batch_importer.py`
- Modify: `tests/unit/parsing/test_source_batch_importer.py`

### Step 1: Write RED in the existing source-batch test

Extend `test_arbitrary_pdf_and_parser_create_searchable_evidence_database` or add a focused sibling test with parser text that can produce a clause.

After `import_source_batch()` returns, assert the published DB already contains:

```python
assert clauses > 0
assert lifecycle_state == "FINALIZED"
assert finalization_version == "1"
assert stored_snapshot_hash == recomputed_snapshot_hash
assert retrieval_snapshot_hash == stored_snapshot_hash
assert report.snapshot_hash == stored_snapshot_hash
```

Also assert `report.counts` is taken after final derivation so its `clauses`/`links` counts match the published DB.

Run RED:

```powershell
py -3.13 -m pytest -v tests/unit/parsing/test_source_batch_importer.py
```

### Step 2: Replace the current manual ingest/hash/index sequence

Current `import_source_batch()` computes a snapshot hash and builds FTS before review-time clauses exist. Replace that portion with the centralized finalizer.

Target shape:

```python
with EvidenceStore(temporary_db, create=True) as store:
    ingest_snapshot(store, snapshot)
    finalized = finalize_evidence_database(store)
    counts = snapshot_counts(store)

# writer is now closed
_publish_create_only(temporary_db, output)
```

Return `finalized.snapshot_hash` as `report.snapshot_hash`.

Do not compute the physical DB SHA here for active binding while the DB is still temporary/open. The exact physical identity is a path-level concern after publication and closure.

Preserve `_publish_create_only()` and its no-overwrite behavior.

### Step 3: Focused GREEN and publication regressions

```powershell
py -3.13 -m pytest -v tests/unit/parsing/test_source_batch_importer.py tests/unit/evidence/test_finalization.py
```

Then:

```powershell
py -3.13 -m pytest -q tests/unit/parsing tests/integration/parsing
```

Record actual test counts.

### Step 4: Commit

```powershell
git add src/evidence_review/parsing/source_batch_importer.py tests/unit/parsing/test_source_batch_importer.py
git diff --check
git commit -m "fix: finalize evidence database before source-batch publish"
```

---

# Task 4 — Add an explicit read-only EvidenceStore mode

**Files:**

- Modify: `src/evidence_review/evidence/store.py`
- Modify: `tests/unit/evidence/test_store.py`

### Step 1: Write RED for storage-level enforcement

Add tests for:

1. read-only existing DB supports SELECT;
2. `PRAGMA query_only` returns `1`;
3. INSERT/UPDATE/DELETE raises `sqlite3.OperationalError`;
4. missing DB with `read_only=True` is not created;
5. `create=True, read_only=True` is rejected;
6. opening/closing read-only leaves exact DB bytes unchanged.

Example target:

```python
with EvidenceStore(path, read_only=True) as store:
    assert store.scalar("PRAGMA query_only") == 1
    with pytest.raises(sqlite3.OperationalError):
        store.require_connection().execute("INSERT INTO documents(id, title) VALUES('X', 'X')")
```

Run RED:

```powershell
py -3.13 -m pytest -v tests/unit/evidence/test_store.py
```

### Step 2: Implement the explicit mode

Extend `EvidenceStore.__init__` with a clear boolean such as:

```python
read_only: bool = False
```

Rules:

- `create and read_only` → `ValueError`;
- existing writable path remains `mode=rw` for build/migration code;
- read-only existing path uses SQLite URI `mode=ro`;
- immediately set `PRAGMA query_only = ON` on read-only connections;
- keep `PRAGMA foreign_keys = ON`;
- never retry a failed read-only open as writable;
- keep current schema validation behavior.

### Step 3: Focused GREEN

```powershell
py -3.13 -m pytest -v tests/unit/evidence/test_store.py
```

### Step 4: Commit

```powershell
git add src/evidence_review/evidence/store.py tests/unit/evidence/test_store.py
git diff --check
git commit -m "feat: add read-only evidence store mode"
```

---

# Task 5 — Make provenance hash the exact finalized file bytes

**Files:**

- Modify: `src/evidence_review/evidence/snapshot.py`
- Modify: `tests/unit/evidence/test_snapshot.py`
- Modify: `tests/unit/review_question/test_evidence_snapshot_binding.py`
- Modify: `tests/unit/review_question/test_planned_snapshot_provenance.py`

### Step 1: Write RED against `connection.serialize()` authority

Create a path-level provenance test that:

- finalizes and closes a DB;
- computes `hashlib.sha256(path.read_bytes()).hexdigest()`;
- requests evidence provenance;
- asserts `evidence_db_sha256` equals the exact file-byte hash.

The test must not define success as equality with `connection.serialize()`.

Run RED:

```powershell
py -3.13 -m pytest -v tests/unit/evidence/test_snapshot.py tests/unit/review_question/test_evidence_snapshot_binding.py tests/unit/review_question/test_planned_snapshot_provenance.py
```

### Step 2: Separate logical connection state from physical path identity

Introduce the smallest path-level helper, for example:

```python
def evidence_database_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
```

Prefer a path-level finalized provenance API so consumers cannot accidentally ask a connection for a file identity it does not own. One acceptable shape is:

```python
def finalized_evidence_provenance(database_path: Path) -> dict[str, object]:
    with EvidenceStore(database_path, read_only=True) as store:
        state = validate_finalized_evidence(store)
        ...
    return {
        "evidence_snapshot_hash": state.snapshot_hash,
        "evidence_db_sha256": evidence_database_file_sha256(database_path),
        ...
    }
```

If `evidence_snapshot_provenance(connection, ...)` is retained for compatibility, require an explicit verified database path for physical hash calculation and remove `connection.serialize()` from authority decisions.

### Step 3: Preserve the external provenance document shape

Do not add unnecessary fields to immutable review request contracts in this task. Continue returning:

```text
evidence_snapshot_hash
evidence_db_sha256
schema_version
retrieval_record_count
clause_record_count
```

### Step 4: Focused GREEN

```powershell
py -3.13 -m pytest -v tests/unit/evidence/test_snapshot.py tests/unit/review_question/test_evidence_snapshot_binding.py tests/unit/review_question/test_planned_snapshot_provenance.py
```

### Step 5: Commit

```powershell
git add src/evidence_review/evidence/snapshot.py tests/unit/evidence/test_snapshot.py tests/unit/review_question/test_evidence_snapshot_binding.py tests/unit/review_question/test_planned_snapshot_provenance.py
git diff --check
git commit -m "fix: bind provenance to exact evidence database bytes"
```

---

# Task 6 — Bind only finalized evidence and revalidate without writes

**Files:**

- Modify: `src/evidence_review/workspace_binding.py`
- Create: `tests/integration/evidence/test_active_workspace_binding.py`
- Modify only if CLI assertions require it: `src/evidence_review/command_dispatch.py`

### Step 1: Write RED for binding lifecycle

Required tests:

- finalized DB binds successfully;
- unfinalized DB is rejected with `ACTIVE_WORKSPACE_INVALID` containing `EVIDENCE_DATABASE_NOT_FINALIZED`;
- binding stores the exact on-disk file SHA;
- `resolve_active_workspace()` leaves DB SHA unchanged;
- replacing/tampering the DB after bind causes `ACTIVE_WORKSPACE_STALE` before review;
- repeated resolve returns the same binding and does not create WAL/journal artifacts.

Run RED:

```powershell
py -3.13 -m pytest -v tests/integration/evidence/test_active_workspace_binding.py
```

### Step 2: Update `_binding_for_workspace()`

Use the existing filesystem-trust boundary first:

```text
verified_regular_directory(workspace)
→ verified_regular_file_below(workspace, evidence/evidence.sqlite)
```

Then obtain finalized provenance through a read-only EvidenceStore/path-level physical hash. `bind_active_workspace()` must never turn a BUILDING/unfinalized DB into a valid one.

### Step 3: Keep the binding schema stable

Do not change `ActiveWorkspaceBinding` fields or binding format/version unless an existing serialization constraint forces it. The current fields are sufficient.

### Step 4: GREEN and CLI regression

```powershell
py -3.13 -m pytest -v tests/integration/evidence/test_active_workspace_binding.py
py -3.13 -m pytest -q tests/integration/review_question/test_question_planner_cli_flow.py tests/integration/review_question/test_review_question_cli.py
```

### Step 5: Commit

```powershell
git add src/evidence_review/workspace_binding.py src/evidence_review/command_dispatch.py tests/integration/evidence/test_active_workspace_binding.py
git diff --check
git commit -m "fix: require finalized evidence for active workspace binding"
```

If `command_dispatch.py` did not require a change, do not stage it.

---

# Task 7 — Remove planned-review repair and fail closed on legacy DBs

**Files:**

- Modify: `src/evidence_review/planned_review_question.py`
- Modify: `src/evidence_review/review_question.py`
- Modify: `tests/unit/review_question/test_planned_snapshot_provenance.py`
- Modify: `tests/unit/review_question/test_evidence_snapshot_binding.py`
- Modify: `tests/integration/review_question/test_real_workspace_clause_repair_e2e.py`
- Modify: `tests/integration/review_question/test_evidence_db_filesystem_trust.py`

### Step 1: Ensure RED proves `ensure_clause_index()` is still review-owned

Before production edits, run:

```powershell
py -3.13 -m pytest -v tests/integration/review_question/test_real_workspace_clause_repair_e2e.py
```

The new legacy test from Task 1 must still fail against the old repair behavior until this task.

### Step 2: Remove review-time materialization

In `planned_review_question.py`:

- remove the `ensure_clause_index` import;
- remove the call from `prepare_planned_review_question()`;
- open the existing evidence DB with `read_only=True`;
- validate finalized state before deterministic retrieval;
- obtain exact finalized provenance without writable access.

Target concept:

```python
database = _evidence_database(workspace)
with EvidenceStore(database, read_only=True) as store:
    state = validate_finalized_evidence(store)
    snapshot_hash = require_fresh_index(store.require_connection())
    provenance = finalized_evidence_provenance(database)
    ...
```

Avoid opening the same file multiple times where a single validated read object/path can be passed cleanly, but do not optimize by weakening the exact file identity check.

### Step 3: Make run snapshot revalidation read-only

Update `_assert_run_evidence_snapshot()` and other existing-workspace review readers in `review_question.py` to use finalized read-only evidence access. Preserve existing reason-code semantics for stale run snapshot mismatches.

### Step 4: Update fixtures to the corrected authority lifecycle

`test_planned_snapshot_provenance.py`, `test_evidence_snapshot_binding.py`, and filesystem-trust helpers currently construct ingest+FTS DBs that are not finalized. Explicitly finalize those fixtures so the test continues exercising its intended concern.

Do not globally auto-finalize a test helper that is also used to test unfinalized failure.

### Step 5: Preserve the real retrieval E2E

In `test_real_workspace_clause_repair_e2e.py`:

- rename/reframe the old “clause repair” expectation to corpus finalization;
- finalize before planned review;
- assert clauses/indices already exist before `prepare_planned_review_question()`;
- record DB SHA before planned review and after planned review;
- assert equality;
- retain existing seven-issue retrieval, citation, Track A/B and finalizer assertions.

Add a separate explicit legacy test asserting review fails and bytes remain unchanged.

### Step 6: Run focused GREEN

```powershell
py -3.13 -m pytest -v tests/unit/review_question/test_planned_snapshot_provenance.py tests/unit/review_question/test_evidence_snapshot_binding.py tests/integration/review_question/test_real_workspace_clause_repair_e2e.py tests/integration/review_question/test_evidence_db_filesystem_trust.py
```

Then:

```powershell
py -3.13 -m pytest -q tests/unit/review_question tests/integration/review_question
```

### Step 7: Commit

```powershell
git add src/evidence_review/planned_review_question.py src/evidence_review/review_question.py tests/unit/review_question/test_planned_snapshot_provenance.py tests/unit/review_question/test_evidence_snapshot_binding.py tests/integration/review_question/test_real_workspace_clause_repair_e2e.py tests/integration/review_question/test_evidence_db_filesystem_trust.py
git diff --check
git commit -m "fix: make formal review evidence access read-only"
```

---

# Task 8 — Audit every post-bind evidence reader; do not blanket-convert writers

**Files:** determined by the inventory below; change only files proven to read a frozen workspace after bind.

Potentially relevant directories/files:

- `src/evidence_review/review_packet/`
- `src/evidence_review/review_run.py`
- `src/evidence_review/review_question.py`
- `src/evidence_review/planned_review_question.py`
- `src/evidence_review/workspace_binding.py`
- direct query CLI reader in `src/evidence_review/cli_handlers.py`

### Step 1: Produce the call-site inventory

```powershell
rg -n "EvidenceStore\(" src/evidence_review
```

Classify every call into exactly one category:

```text
BUILD_CREATE
MIGRATION_WRITE
EXPLICIT_MAINTENANCE_WRITE
POST_BIND_REVIEW_READ
STANDALONE_QUERY_READ
```

Record the classification in the task notes/commit message or a short acceptance artifact; do not change a call merely because it opens an existing DB.

### Step 2: Convert post-bind readers to read-only

Every `POST_BIND_REVIEW_READ` path must use `read_only=True` and finalized validation where the authority contract requires a frozen workspace.

Keep explicit migration/build writers writable.

For the standalone `query` CLI, choose conservatively:

- opening the provided DB read-only is appropriate because query is retrieval-only;
- require finalized state only if current documented query semantics say it consumes canonical ready evidence. Do not accidentally break migration inspection paths by over-scoping #155.

### Step 3: Add only boundary-specific regressions

Extend the existing relevant tests rather than creating duplicate suites. At minimum cover any changed review-run/review-packet reader with an assertion that its DB SHA is unchanged.

Suggested suites:

```powershell
py -3.13 -m pytest -q tests/integration/review_run tests/integration/review_packet tests/unit/review_packet
```

### Step 4: Re-run inventory

```powershell
rg -n "EvidenceStore\(" src/evidence_review
```

Review the diff manually. No post-bind review read should remain writable; migration/build writers must remain intentionally writable.

### Step 5: Commit

```powershell
git add <only-files-classified-as-post-bind-readers-and-their-tests>
git diff --check
git commit -m "refactor: enforce read-only evidence access after binding"
```

---

# Task 9 — Prove automated DB byte stability through formal review lifecycle

**Files:**

- Create: `tests/integration/review_question/test_evidence_db_hash_stability.py`
- Reuse/refactor a small helper from existing review E2E tests only if necessary; do not duplicate the full real-corpus fixture unless isolation requires it.

### Step 1: Build one fully finalized test workspace

Create/finalize the DB through the same production boundary used by source/corpus preparation. Do not directly patch lifecycle metadata in the test.

Record:

```python
def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
```

### Step 2: Capture automated checkpoints

At minimum capture:

```text
A_test = finalized/published DB
B_test = after active workspace bind/resolve
C_test = after planned review prepare
D_test = after Track A submission
E_test = after Track B submission/finalization
```

If the existing protected viewer/server test can be exercised deterministically without flaky external browser launch, also capture:

```text
F_test = after protected server start/status/stop
```

The automated test must assert all captured hashes are identical.

Also assert no persistent sibling sidecars remain after each stage:

```text
evidence.sqlite-wal
evidence.sqlite-shm
evidence.sqlite-journal
```

Do not assume the automated F checkpoint substitutes for the mandatory real Windows A–G acceptance in Task 12.

### Step 3: Run the focused lifecycle test

```powershell
py -3.13 -m pytest -v tests/integration/review_question/test_evidence_db_hash_stability.py
```

### Step 4: Run adjacent full formal review suites

```powershell
py -3.13 -m pytest -q tests/integration/review_question tests/integration/review_run tests/integration/review_packet
```

### Step 5: Commit

```powershell
git add tests/integration/review_question/test_evidence_db_hash_stability.py <any-small-shared-test-helper-change>
git diff --check
git commit -m "test: prove review lifecycle preserves evidence database bytes"
```

---

# Task 10 — Update current authority docs and user-facing `$ERS_PDF` contract

**Files:**

- Modify: `AGENTS.md`
- Modify: `.agents/skills/ers-pdf/SKILL.md`
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `docs/MANUAL_ACCEPTANCE_POLICY.md` only if the exact DB hash acceptance rule needs to be made current merge authority
- Modify: `SECURITY.md` if needed to keep the immutable evidence trust-boundary claim accurate

### Step 1: Update the corpus workflow

Document:

```text
source-batch ingest
→ deterministic evidence finalization
→ final logical hash/index verification
→ writer close
→ create-only publish
→ exact file SHA
→ workspace bind
→ frozen/read-only review
```

Do not tell users to run a separate repair step.

### Step 2: Clarify the two hash authorities

Current docs must say:

- logical snapshot hash determines canonical evidence equivalence;
- exact DB file SHA binds the selected frozen artifact;
- review cannot mutate the bound DB;
- same logical hash does not require byte-identical separately rebuilt SQLite files;
- exact byte equality **is** required across the lifetime of one bound artifact.

### Step 3: Document legacy recovery

An unfinalized old workspace must be re-prepared through `$ERS_PDF`; `$ERS_REVIEW` does not repair it.

### Step 4: Validate docs

Use a fresh output path:

```powershell
$DocOut = Join-Path $env:TEMP ("ers-doc-integrity-" + [guid]::NewGuid() + ".json")
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output $DocOut
```

Expected: exit code 0, validator errors 0.

### Step 5: Commit

```powershell
git add AGENTS.md .agents/skills/ers-pdf/SKILL.md docs/CODEX_WORKFLOW.md docs/MANUAL_ACCEPTANCE_POLICY.md SECURITY.md
git diff --check
git commit -m "docs: document frozen evidence lifecycle"
```

Stage only documents actually changed.

---

# Task 11 — Exact-HEAD automated acceptance

Before this task, invoke `superpowers:verification-before-completion`. Do not reuse test output from an earlier commit after HEAD changes.

### Step 1: Prove clean exact HEAD

```powershell
git rev-parse HEAD
git status --short
git diff --check
py -3.13 --version
```

Record exact outputs.

### Step 2: Documentation integrity

```powershell
$DocOut = Join-Path $env:TEMP ("ers-doc-integrity-" + [guid]::NewGuid() + ".json")
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output $DocOut
```

### Step 3: Full pytest

```powershell
py -3.13 -m pytest -v
```

Record passed/skipped/failed counts exactly.

### Step 4: Static gates

```powershell
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
```

All required commands must exit 0.

### Step 5: Python 3.13 wheel/runtime smoke

Because package production code changes, build/install in an isolated environment and verify imports/CLI, including the finalization module and current package data. Record the exact wheel SHA-256.

Use the repository's current packaging commands rather than inventing a second packaging flow. At minimum demonstrate:

```text
wheel build = PASS
isolated install = PASS
import evidence_review = PASS
import evidence_review.evidence.finalization = PASS
evidence-review --help = PASS
```

### Step 6: Release validator smoke where applicable

On a valid finalized workspace:

```powershell
py -3.13 scripts/validate_release.py <workspace>
```

Do not call this PASS if the workspace lacks unrelated release-required artifacts; record the exact status and distinguish #155 DB-identity checks from unrelated release blockers.

### Step 7: GitHub Actions status

Per repository policy, Actions is not the default acceptance dependency. Record the observed state exactly, normally:

```text
ACTIONS_NOT_RUN
```

Do not translate local acceptance into Actions PASS.

---

# Task 12 — Mandatory real Windows A–G hash-stability acceptance

Issue #155 remains open until this gate passes on the exact implementation HEAD.

Use a **fresh real workspace** created from actual reference PDFs/parser artifacts. Do not reuse the historical mutated workspace as the primary acceptance artifact.

Record platform, Python version, exact commit, workspace path, source hashes, and every command/exit code.

### Checkpoint A — corpus finalization complete, before bind

After successful source-batch/corpus preparation and finalization:

```powershell
$Db = "<workspace>\evidence\evidence.sqlite"
$A = (Get-FileHash $Db -Algorithm SHA256).Hash.ToLower()
```

Verify via SQLite/Python probe:

```text
lifecycle_state = FINALIZED
finalization_version = 1
stored snapshot hash == recomputed snapshot hash
retrieval hash == stored snapshot hash
integrity_check == ok
foreign_key_check == []
```

### Checkpoint B — immediately after active bind

```powershell
py -3.13 -m evidence_review workspace bind --repository-root . --workspace <workspace>
$B = (Get-FileHash $Db -Algorithm SHA256).Hash.ToLower()
```

Verify binding `evidence_db_sha256 == $B`.

### Checkpoint C — after formal review prepare

Run current Question Planner handoff and planned review prepare using the same workspace, then:

```powershell
$C = (Get-FileHash $Db -Algorithm SHA256).Hash.ToLower()
```

### Checkpoint D — after Track A accepted

Submit valid Track A, then record `$D`.

### Checkpoint E — after Track B accepted

Submit valid Track B and complete finalization, then record `$E`.

### Checkpoint F — final review packet complete

After packet/HTML integrity verification, record `$F`.

If Track B submission already performs packet finalization, still record E and F as separate observed lifecycle checkpoints around the applicable verification commands; do not invent duplicate work solely to manufacture different stages.

### Checkpoint G — protected viewer/server opened and closed

Open the real protected route, verify it loads, use current `serve-status`/`serve-stop` or bounded idle lifecycle, then record `$G`.

Also verify no persistent `-wal`, `-shm`, or `-journal` exists next to the DB after shutdown.

### Mandatory equality

```text
A == B == C == D == E == F == G
```

And:

```text
active binding evidence_db_sha256 == A
stored logical snapshot hash == recomputed logical snapshot hash
retrieval index hash == logical snapshot hash
```

Any difference is a HOLD. Do not rebind after a mismatch and then call the same run PASS; investigate the writer first.

Create a date/commit-specific acceptance record under `docs/` only after this gate is actually executed. Do not pre-author a PASS record.

---

# Task 13 — Code review, PR, and issue closure gate

### Step 1: Review the complete diff

Use `superpowers:requesting-code-review` before opening/merging the PR. Specifically inspect:

- no review-time `ensure_clause_index()` call remains;
- no physical authority uses `connection.serialize()`;
- no post-bind review reader silently opens `mode=rw`;
- build/migration writers were not accidentally converted to read-only;
- final hash is computed after legal-reference links;
- final retrieval index is rebuilt against the final hash;
- old unfinalized workspace behavior is fail-closed and non-mutating.

### Step 2: Create the PR only after exact-HEAD automated gates

Suggested title:

```text
fix: freeze evidence database before formal review
```

PR body must explain that source/evidence authority and release/package integrity boundaries changed. Do not check the template's “No source/evidence authority changes” or “No release/package integrity changes” boxes as if there were no impact; explain the approved new fail-closed boundary instead.

Before the real A–G gate is complete, use `Refs #155` and keep closure readiness HOLD. After A–G passes and the acceptance evidence is committed, the final PR may use:

```text
Closes #155
```

### Step 3: Final closure conditions

Issue #155 can close only when all are evidenced on the final implementation HEAD:

```text
ROOT_CAUSE = PROVEN
CORPUS_FINALIZATION_OWNS_DERIVED_WRITES = PASS
FINAL_LOGICAL_SNAPSHOT_HASH = VERIFIED
FINAL_RETRIEVAL_INDEX_BINDING = VERIFIED
ACTIVE_DB_PHYSICAL_SHA = AUTHORITATIVE
REVIEW_EVIDENCE_DB_MODE = READ_ONLY
REVIEW_TIME_DB_MUTATION = 0
LEGACY_UNFINALIZED_WORKSPACE = FAIL_CLOSED
FULL_AUTOMATED_GATES = PASS
REAL_WORKSPACE_HASH_STABILITY_A_TO_G = PASS
RELEASE_DB_IDENTITY_CONTRACT = UNAMBIGUOUS
```

If any item is not executed, report `NOT_RUN` or `HOLD`; do not infer it from adjacent tests.

---

## 3. Expected commit sequence

Keep commits narrow and reviewable. A reasonable sequence is:

```text
test: lock frozen evidence lifecycle regression
feat: add evidence database finalization boundary
fix: finalize evidence database before source-batch publish
feat: add read-only evidence store mode
fix: bind provenance to exact evidence database bytes
fix: require finalized evidence for active workspace binding
fix: make formal review evidence access read-only
refactor: enforce read-only evidence access after binding
test: prove review lifecycle preserves evidence database bytes
docs: document frozen evidence lifecycle
```

Do not force this exact count if two adjacent tasks genuinely require one atomic commit, but do not combine unrelated Stabilization Round 2 issues (#152–#166) into #155.

---

## 4. Out of scope for this implementation

Do not include:

- Review HTML/UI redesign (#152);
- retrieval query-quality repair (#153);
- protected HTTP transport unification (#159);
- Pillow floor (#160);
- release rule-semantic validation (#161);
- repository branch protection (#162);
- reviewer default identity (#164);
- visual basename/MIME issues (#165/#166);
- split evidence/retrieval database architecture;
- automatic legacy in-place upgrade.

Those remain separate issues/PRs under Stabilization Closure Round 2.

---

## 5. Final executor report format

At the final stop, report at least:

```text
ISSUE_155 = PASS | HOLD
BASE_SHA = ...
FINAL_HEAD = ...
BRANCH = fix/issue-155-immutable-evidence-finalization
WORKTREE = ...

ROOT_CAUSE = PROVEN
CORPUS_FINALIZATION = PASS | FAIL | NOT_RUN
READ_ONLY_REVIEW = PASS | FAIL | NOT_RUN
LEGACY_FAIL_CLOSED = PASS | FAIL | NOT_RUN
AUTOMATED_HASH_STABILITY = PASS | FAIL | NOT_RUN
REAL_A_TO_G_HASH_STABILITY = PASS | FAIL | NOT_RUN

SHA_A = ...
SHA_B = ...
SHA_C = ...
SHA_D = ...
SHA_E = ...
SHA_F = ...
SHA_G = ...

FULL_PYTEST = <exact counts/result>
RUFF = ...
MYPY_LINUX = ...
MYPY_WIN32 = ...
COMPILEALL = ...
DOCUMENTATION = ...
WHEEL_RUNTIME_SMOKE = ...
RELEASE_VALIDATOR = ...
ACTIONS = ACTIONS_NOT_RUN | observed actual state

PUSH = ...
PR = ...
MERGE_READINESS = READY_FOR_REVIEW | HOLD
```

Never report `PASS` for a gate that was not executed on the final HEAD.