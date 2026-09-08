# ERS ReviewMatter Architecture Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a persistent ReviewMatter/Workbench workflow in front of the existing immutable Formal Review core without weakening evidence, Track A/B, finalizer, packet, or Human Decision authority.

**Architecture:** Add a separate mutable Matter store and canonical ReviewScope, then promote one exact Matter revision through an immutable FormalizationSnapshot into the existing formal engine. Existing finalized evidence and Formal Run artifacts stay immutable; Workbench and Evidence Navigation remain explicitly non-authoritative.

**Tech Stack:** Python 3.13, SQLite, stdlib HTTP loopback server, existing ERS contracts/retrieval/finalizer/rendering, pytest, Ruff, mypy, python packaging/wheel smoke.

**Spec:** `docs/REVIEW_MATTER_ARCHITECTURE.md` (created by MIG-01)

## Global Constraints

- Baseline for this plan: main a42167ef6d2e8bf23f557bf12995398f79669b7b.
- Finalized `evidence.sqlite` remains immutable and separate from Matter storage.
- `ReviewMatter`/`matter_id` is distinct from existing drawing `CaseManifest`/`case_id`.
- Formalization is one-way: Matter → immutable FormalizationSnapshot → existing Formal Run.
- Formal Run code must never mutate Matter history.
- Human Decision remains append-only and packet-hash-bound.
- Production changes use TDD: RED → minimal GREEN → regression → full exact-HEAD gate.
- Direct push/force push to main is prohibited; PR-only integration policy applies.
- GitHub Actions not run is reported as `ACTIONS_NOT_RUN`, never PASS.

---

## Existing-Issue prerequisite graph

```text
#154 CLOSED → #155 CLOSED
#160 → #166
#159 → #156
#165 + #166 → #156 → #152
#153 + #158 → retrieval/semantic readiness
#157 → multi-run/formalization readiness
#161 → release-semantic readiness → #163 release-state closure
#162 + #169 → governance baseline
```

## MIG dependency graph

```text
MIG-01 → MIG-02 → MIG-03 → MIG-04 → MIG-05 ─┬→ MIG-06 ─────────┐
                                                ├→ MIG-09 ─┐      │
MIG-02 → MIG-07 → MIG-08 ───────────────────────┘         ├→ MIG-10 → MIG-11 → MIG-12 → MIG-13 → MIG-14 ─┐
                                                         │                                                ├→ MIG-17 ─┐
#157 CLOSED ──────────────────────────────────────────────┘                                                │          │
MIG-05 + MIG-07 + MIG-14 + #160/#165/#166 → MIG-15 → MIG-16 ─────────────────────────────────────────────┘          │
MIG-11 → MIG-18 ────────────────────────────────────────────────────────────────────────────────────────────────┐   │
MIG-17 + MIG-18 + #161 → MIG-19 ───────────────────────────────────────────────────────────────────────────────┼→ MIG-20
MIG-16 ────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### MIG-01: Architecture contract freeze and ReviewMatter naming

**Dependencies:** #154 CLOSED, #155 CLOSED, #162 governance gate, #169 policy

**Files:**
- Create: `docs/REVIEW_MATTER_ARCHITECTURE.md`
- Create: `tests/integration/documentation_integrity/test_review_matter_architecture_docs.py`
- Modify: `docs/CONTRACT_GOVERNANCE.md`
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `AGENTS.md`
- Modify: `documentation-integrity.json`

**Interfaces:**
- Consumes: current `docs/CONTRACT_GOVERNANCE.md`, `docs/CODEX_WORKFLOW.md`, current drawing `case_id`/`CaseManifest` semantics.
- Produces: `docs/REVIEW_MATTER_ARCHITECTURE.md` as the normative migration spec; `ReviewMatter`/`matter_id` is the only new mutable-work identity.

- [x] **Step 1: Add the focused RED test/contract before production implementation**

A documentation contract test must fail while the repository still lacks an explicit ReviewMatter authority boundary and while a new persistent domain could be confused with existing drawing case_id semantics.

```python
from pathlib import Path


def test_review_matter_architecture_declares_distinct_identity() -> None:
    text = Path("docs/REVIEW_MATTER_ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "ReviewMatter" in text
    assert "matter_id" in text
    assert "CaseManifest" in text
    assert "ReviewCase" not in text
    assert "evidence.sqlite" in text
    assert "Human Decision" in text
```

- [x] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/documentation_integrity/test_review_matter_architecture_docs.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [x] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [x] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/documentation_integrity/test_review_matter_architecture_docs.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Documentation validator PASS with errors=0
- No production code behavior change
- ReviewMatter is the only new mutable work-domain name; existing case_id/CaseManifest semantics remain unchanged
- Formal evidence, Formal Run, Review Packet, Human Decision authority order remains explicit
- Full pytest/Ruff/mypy/compileall unchanged

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add docs/REVIEW_MATTER_ARCHITECTURE.md tests/integration/documentation_integrity/test_review_matter_architecture_docs.py docs/CONTRACT_GOVERNANCE.md docs/CODEX_WORKFLOW.md AGENTS.md documentation-integrity.json
git commit -m "docs(mig-01): freeze ReviewMatter architecture boundaries"
git rev-parse HEAD
git status --short
```

Branch: `refactor/mig-01-review-matter-contract-freeze`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-02: Canonical ReviewMatter contracts and identifiers

**Dependencies:** MIG-01

**Files:**
- Create: `src/evidence_review/review_matter/__init__.py`
- Create: `src/evidence_review/review_matter/contracts.py`
- Create: `tests/unit/review_matter/test_contracts.py`
- Modify: `src/evidence_review/contracts/formats.py`

**Interfaces:**
- Consumes: `evidence_review.contracts.identifiers.validate_identifier` and canonical format conventions.
- Produces: `decode_review_matter(value) -> ReviewMatter`, `review_matter_document(matter) -> dict[str, object]`, `MatterIssue`, `MatterIssueState`, and `MatterSourceBinding`.

- [x] **Step 1: Add the focused RED test/contract before production implementation**

Strict decoder tests fail because ReviewMatter, MatterIssue, MatterSourceBinding and MatterIssueState formats do not exist; unknown fields, duplicate issue IDs, invalid identifiers and formal-status vocabulary in work-state fields must be rejected.

```python
import pytest

from evidence_review.review_matter.contracts import decode_review_matter


def test_matter_issue_rejects_formal_issue_status_as_work_state() -> None:
    document = {
        "format": "evidence-review/review-matter",
        "version": 1,
        "matter_id": "MATTER-001",
        "title": "Accessible toilet review",
        "revision": 1,
        "issues": [{
            "issue_id": "ISSUE-001",
            "question": "Is the entrance width sufficient?",
            "work_state": "RESOLVED",
            "depends_on": [],
        }],
        "source_bindings": [],
    }
    with pytest.raises(ValueError, match="work_state"):
        decode_review_matter(document)
```

- [x] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/unit/review_matter/test_contracts.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [x] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [x] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/unit/review_matter/test_contracts.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Canonical format/version constants exist
- All contracts round-trip through strict decoders
- Unknown/missing fields fail closed
- Matter work states are distinct from contracts.review.IssueStatus
- matter_id cannot be confused with CASE-VIS case_id
- Focused unit suite PASS + full static gates

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/review_matter/__init__.py src/evidence_review/review_matter/contracts.py tests/unit/review_matter/test_contracts.py src/evidence_review/contracts/formats.py
git commit -m "feat(mig-02): add ReviewMatter contracts"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-02-review-matter-contracts`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-03: ReviewMatter SQLite store with optimistic concurrency

**Dependencies:** MIG-02

**Files:**
- Create: `src/evidence_review/review_matter/schema.sql`
- Create: `src/evidence_review/review_matter/store.py`
- Create: `tests/unit/review_matter/test_store.py`
- Create: `tests/integration/review_matter/test_concurrency.py`

**Interfaces:**
- Consumes: MIG-02 `ReviewMatter` contracts.
- Produces: `MatterStore(path)`, `MatterStore.create(...)`, `MatterStore.load(matter_id)`, and `MatterStore.rename(matter_id, expected_revision, title)` with compare-and-swap revision semantics.

- [x] **Step 1: Add the focused RED test/contract before production implementation**

Two writers updating the same matter revision must currently be able to race because no Matter store exists. Tests first require expected_revision semantics: writer A succeeds from rev 3→4 and writer B using expected rev 3 fails with MATTER_REVISION_CONFLICT.

```python
import pytest

from evidence_review.review_matter.store import MatterRevisionConflict, MatterStore


def test_stale_writer_cannot_overwrite_newer_matter_revision(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    created = store.create(matter_id="MATTER-001", title="Initial")
    assert created.revision == 1
    updated = store.rename("MATTER-001", expected_revision=1, title="Writer A")
    assert updated.revision == 2
    with pytest.raises(MatterRevisionConflict, match="MATTER_REVISION_CONFLICT"):
        store.rename("MATTER-001", expected_revision=1, title="Writer B")
    assert store.load("MATTER-001").title == "Writer A"
```

- [x] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_concurrency.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [x] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [x] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_concurrency.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Store is physically separate from evidence/evidence.sqlite
- BEGIN IMMEDIATE or equivalent transaction boundary serializes mutation
- expected_revision is mandatory on mutation
- Rollback leaves neither partial row nor revision increment
- Database schema version is explicit
- Concurrent stale writer test PASS on supported platform

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/review_matter/schema.sql src/evidence_review/review_matter/store.py tests/unit/review_matter/test_store.py tests/integration/review_matter/test_concurrency.py
git commit -m "feat(mig-03): add transactional ReviewMatter store"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-03-review-matter-store`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-04: Append-only Matter events and transactionally consistent projections

**Dependencies:** MIG-03

**Files:**
- Create: `src/evidence_review/review_matter/events.py`
- Create: `src/evidence_review/review_matter/projection.py`
- Create: `tests/unit/review_matter/test_events.py`
- Create: `tests/integration/review_matter/test_event_projection_atomicity.py`
- Modify: `src/evidence_review/review_matter/schema.sql`
- Modify: `src/evidence_review/review_matter/store.py`

**Interfaces:**
- Consumes: MIG-03 transactional `MatterStore`.
- Produces: `MatterEvent`, `append_matter_event(store, matter_id, expected_revision, event) -> MatterProjection`, and `rebuild_projection(store, matter_id)`.

- [x] **Step 1: Add the focused RED test/contract before production implementation**

A test injects an exception between event append and projection update; the transaction must roll back both. Duplicate sequence numbers, non-contiguous event order, and event/matter revision mismatch must fail closed.

```python
import pytest

from evidence_review.review_matter.events import MatterEvent, append_matter_event
from evidence_review.review_matter.store import MatterStore


def test_event_and_projection_roll_back_together(tmp_path, monkeypatch) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(matter_id="MATTER-001", title="Initial")
    event = MatterEvent(kind="TITLE_CHANGED", payload={"title": "Changed"})
    monkeypatch.setattr(store, "apply_projection", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        append_matter_event(store, "MATTER-001", expected_revision=1, event=event)
    assert store.load("MATTER-001").revision == 1
    assert store.list_events("MATTER-001") == ()
```

- [x] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_event_projection_atomicity.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [x] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [x] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_event_projection_atomicity.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Matter events are append-only
- Event and projection update commit in one DB transaction
- Projection can be rebuilt from events for a test fixture
- Rollback produces no half-applied event
- Matter event authority remains separate from workflow/events.py Formal Run journal

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/review_matter/events.py src/evidence_review/review_matter/projection.py tests/unit/review_matter/test_events.py tests/integration/review_matter/test_event_projection_atomicity.py src/evidence_review/review_matter/schema.sql src/evidence_review/review_matter/store.py
git commit -m "feat(mig-04): add Matter event authority"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-04-matter-event-authority`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-05: Exact evidence/source binding and stale invalidation foundation

**Dependencies:** MIG-04, #155 CLOSED

**Files:**
- Create: `src/evidence_review/review_matter/source_binding.py`
- Create: `src/evidence_review/review_matter/invalidation.py`
- Create: `tests/unit/review_matter/test_source_binding.py`
- Create: `tests/integration/review_matter/test_evidence_binding.py`
- Modify: `src/evidence_review/review_matter/contracts.py`
- Modify: `src/evidence_review/review_matter/schema.sql`

**Interfaces:**
- Consumes: MIG-04 Matter event authority and existing `finalized_evidence_provenance`.
- Produces: `bind_finalized_evidence(...)`, `register_issue_source_dependency(...)`, and `invalidate_source_dependents(...)` without writing to `evidence.sqlite`.

- [x] **Step 1: Add the focused RED test/contract before production implementation**

Binding a matter to an unfinalized evidence DB, a different exact DB SHA, a changed logical snapshot, or a missing revision must fail. Rebinding a source must mark dependent issues stale rather than silently retaining READY_TO_FORMALIZE.

```python
import pytest

from evidence_review.review_matter.source_binding import bind_finalized_evidence
from evidence_review.review_matter.store import MatterStore


def test_unfinalized_evidence_cannot_be_bound_to_matter(tmp_path) -> None:
    matter_db = tmp_path / "review-matters.sqlite"
    evidence_db = tmp_path / "evidence.sqlite"
    evidence_db.write_bytes(b"not-a-finalized-sqlite")
    store = MatterStore(matter_db)
    store.create(matter_id="MATTER-001", title="Review")
    with pytest.raises(ValueError, match="MATTER_EVIDENCE_BINDING_INVALID"):
        bind_finalized_evidence(
            store,
            matter_id="MATTER-001",
            expected_revision=1,
            evidence_db=evidence_db,
        )
```

- [x] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_evidence_binding.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [x] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_evidence_binding.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Uses finalized_evidence_provenance() rather than duplicate hashing logic
- Stores logical snapshot hash and exact evidence_db_sha256
- No write path into evidence.sqlite
- Source-binding changes emit invalidation events
- Unknown dependency impact invalidates rather than retains

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/review_matter/source_binding.py src/evidence_review/review_matter/invalidation.py tests/unit/review_matter/test_source_binding.py tests/integration/review_matter/test_evidence_binding.py src/evidence_review/review_matter/contracts.py src/evidence_review/review_matter/schema.sql
git commit -m "feat(mig-05): bind matters to exact evidence authority"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-05-matter-source-binding`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-06: Evidence Navigation service and explicit promotion boundary

**Dependencies:** MIG-05, #153 CLOSED

**Files:**
- Create: `src/evidence_review/navigation/__init__.py`
- Create: `src/evidence_review/navigation/models.py`
- Create: `src/evidence_review/navigation/service.py`
- Create: `src/evidence_review/navigation/promotion.py`
- Create: `tests/unit/navigation/test_models.py`
- Create: `tests/integration/navigation/test_evidence_navigation.py`
- Create: `tests/integration/navigation/test_promotion.py`

**Interfaces:**
- Consumes: finalized evidence binding from MIG-05 and existing deterministic retrieval primitives after #153.
- Produces: `navigate_evidence(evidence_db, query, limit=20) -> NavigationResult` and `promote_navigation_hit(...) -> MatterProjection`.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

Navigation of a known bounded phrase must return traceable evidence without creating a RUN, Track handoff, ReviewPacket or formal status. Promotion from a stale navigation result must be rejected after evidence identity changes.

```python
from evidence_review.navigation.service import navigate_evidence


def test_navigation_returns_traceable_hits_without_creating_formal_run(finalized_workspace) -> None:
    runs_before = tuple((finalized_workspace / "runs").glob("RUN-*"))
    result = navigate_evidence(
        finalized_workspace / "evidence" / "evidence.sqlite",
        "안심주택 최소 대지면적",
    )
    assert result.hits
    assert all(hit.citation.source_hash for hit in result.hits)
    assert result.formal_status is None
    assert tuple((finalized_workspace / "runs").glob("RUN-*")) == runs_before
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/navigation/test_promotion.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/navigation/test_promotion.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Navigation result contains citation/source/revision/page/bbox/hash identity
- No READY_FOR_HUMAN_REVIEW/ABSTAIN/compliance status in navigation contract
- Search does not create runs/<RUN_ID>
- Promotion revalidates evidence against current Matter binding
- Negative no-evidence result remains non-authoritative and explicit

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/navigation/__init__.py src/evidence_review/navigation/models.py src/evidence_review/navigation/service.py src/evidence_review/navigation/promotion.py tests/unit/navigation/test_models.py tests/integration/navigation/test_evidence_navigation.py tests/integration/navigation/test_promotion.py
git commit -m "feat(mig-06): add non-authoritative evidence navigation"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-06-evidence-navigation`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-07: Canonical ReviewScope independent of planner authority

**Dependencies:** MIG-02, #153 CLOSED, #158 CLOSED

**Files:**
- Create: `src/evidence_review/review_matter/scope.py`
- Create: `tests/unit/review_matter/test_review_scope.py`
- Modify: `src/evidence_review/contracts/formats.py`

**Interfaces:**
- Consumes: current `QuestionIssue`, `QuestionFact`, `LegalAnchor`, and `SearchRequest` semantics.
- Produces: canonical `ReviewScope`, `decode_review_scope`, `review_scope_document`, `review_scope_from_question_plan`, and `build_explicit_review_scope`.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

Equivalent planner-derived and explicit-user scope inputs must canonicalize to the same downstream issue/search structure where their semantics are equal, while preserving origin metadata. Invalid dependency cycles and empty required evidence roles must fail.

```python
from evidence_review.review_matter.scope import (
    build_explicit_review_scope,
    review_scope_from_question_plan,
    review_scope_document,
)


def test_equivalent_explicit_and_planner_scope_share_downstream_structure(valid_question_plan) -> None:
    planner_scope = review_scope_from_question_plan(valid_question_plan)
    explicit_scope = build_explicit_review_scope(
        question=valid_question_plan.original_question,
        issues=valid_question_plan.issues,
        facts=valid_question_plan.facts,
        assumptions=valid_question_plan.assumptions,
        legal_anchors=valid_question_plan.legal_anchors,
        search_requests=valid_question_plan.search_requests,
    )
    left = review_scope_document(planner_scope)
    right = review_scope_document(explicit_scope)
    for key in ("question", "issues", "facts", "assumptions", "legal_anchors", "search_requests"):
        assert left[key] == right[key]
    assert left["origin"] == "PLANNER"
    assert right["origin"] == "EXPLICIT_USER"
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/unit/review_matter/test_review_scope.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/unit/review_matter/test_review_scope.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- ReviewScope is canonical downstream control input
- Planner output is one producer, not the downstream type
- Explicit user scope is another producer
- Issue/search IDs remain stable and unique
- No evidence or final decision can be embedded in ReviewScope

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/review_matter/scope.py tests/unit/review_matter/test_review_scope.py src/evidence_review/contracts/formats.py
git commit -m "feat(mig-07): add canonical ReviewScope"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-07-review-scope-contract`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-08: Planner and explicit-scope adapters; decouple planned review orchestration

**Dependencies:** MIG-07

**Files:**
- Create: `src/evidence_review/scoped_review.py`
- Create: `tests/integration/review_question/test_scoped_review_flow.py`
- Modify: `src/evidence_review/question_planning.py`
- Modify: `src/evidence_review/planned_review_question.py`
- Modify: `src/evidence_review/question_planner_cli.py`

**Interfaces:**
- Consumes: MIG-07 `ReviewScope`.
- Produces: `prepare_scoped_review_question(workspace, scope, ...) -> PreparedReviewQuestion`; planner and explicit-user adapters both terminate at this interface.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

The same canonical scope must produce equivalent deterministic retrieval/review-request semantics whether sourced from validated QuestionPlan or explicit ReviewScope. Planner lineage may differ, but downstream evidence selection cannot diverge merely because the producer differs.

```python
from evidence_review.planned_review_question import prepare_planned_review_question
from evidence_review.review_matter.scope import review_scope_from_question_plan
from evidence_review.scoped_review import prepare_scoped_review_question


def test_planner_adapter_and_scoped_path_produce_same_formal_request(finalized_workspace, valid_question_plan) -> None:
    planned = prepare_planned_review_question(finalized_workspace, valid_question_plan)
    scope = review_scope_from_question_plan(valid_question_plan)
    scoped = prepare_scoped_review_question(finalized_workspace, scope)
    assert planned.run_id == scoped.run_id
    assert (planned.run_id, planned.status) == (scoped.run_id, scoped.status)
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/review_question/test_scoped_review_flow.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/review_question/test_scoped_review_flow.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- prepare_planned_review_question delegates through ReviewScope
- Legacy planner CLI behavior preserved
- Explicit-scope preparation path exists without pretending planner output exists
- question_plan_sha256 remains compatibility lineage when planner was used
- Downstream no planner/else branching outside adapter boundary

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/scoped_review.py tests/integration/review_question/test_scoped_review_flow.py src/evidence_review/question_planning.py src/evidence_review/planned_review_question.py src/evidence_review/question_planner_cli.py
git commit -m "refactor(mig-08): route formal preparation through ReviewScope"
git rev-parse HEAD
git status --short
```

Branch: `refactor/mig-08-scoped-review-orchestration`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-09: Immutable FormalizationSnapshot with exact Matter revision gate

**Dependencies:** MIG-05, MIG-07

**Files:**
- Create: `src/evidence_review/review_matter/snapshot.py`
- Create: `tests/unit/review_matter/test_formalization_snapshot.py`
- Create: `tests/integration/review_matter/test_formalization_race.py`
- Modify: `src/evidence_review/review_matter/contracts.py`
- Modify: `src/evidence_review/review_matter/schema.sql`
- Modify: `src/evidence_review/review_matter/store.py`

**Interfaces:**
- Consumes: MIG-05 exact Matter/evidence binding and MIG-07 ReviewScope.
- Produces: `FormalizationSnapshot` and `create_formalization_snapshot(store, matter_id, expected_revision, evidence_db) -> FormalizationSnapshot`.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

Formalization requested for expected revision 42 must fail if the Matter becomes revision 43 before snapshot creation. Snapshot creation must also fail with any required stale issue or mismatched evidence DB SHA.

```python
import pytest

from evidence_review.review_matter.snapshot import create_formalization_snapshot


def test_formalization_rejects_stale_expected_matter_revision(matter_store, finalized_evidence_db) -> None:
    matter_store.create(matter_id="MATTER-001", title="Review")
    matter_store.rename("MATTER-001", expected_revision=1, title="Changed")
    with pytest.raises(ValueError, match="MATTER_CHANGED_DURING_FORMALIZATION"):
        create_formalization_snapshot(
            matter_store,
            matter_id="MATTER-001",
            expected_revision=1,
            evidence_db=finalized_evidence_db,
        )
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_formalization_race.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_formalization_race.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Snapshot is canonical and immutable once recorded
- Snapshot contains exact matter_id/revision, ReviewScope, source/evidence bindings and selected promoted evidence
- Unpromoted drafts are excluded
- Required STALE/NEEDS_EVIDENCE issue blocks formalization
- Concurrent revision change produces MATTER_CHANGED_DURING_FORMALIZATION

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/review_matter/snapshot.py tests/unit/review_matter/test_formalization_snapshot.py tests/integration/review_matter/test_formalization_race.py src/evidence_review/review_matter/contracts.py src/evidence_review/review_matter/schema.sql src/evidence_review/review_matter/store.py
git commit -m "feat(mig-09): freeze exact Matter formalization snapshots"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-09-formalization-snapshot`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-10: Formalization adapter into existing Formal Review core

**Dependencies:** MIG-08, MIG-09, #157 CLOSED

**Files:**
- Create: `src/evidence_review/review_matter/formalization.py`
- Create: `tests/integration/review_matter/test_formalization_adapter.py`
- Modify: `src/evidence_review/review_question.py`
- Modify: `src/evidence_review/review_run.py`

**Interfaces:**
- Consumes: MIG-09 immutable `FormalizationSnapshot` and MIG-08 scoped formal preparation.
- Produces: `formalize_snapshot(workspace, snapshot, ...) -> PreparedReviewQuestion`; no reverse mutation of Matter is permitted.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

A formalization snapshot with an unpromoted draft numeric observation must not inject that observation into evidence, calculation, rule or claim authority. A valid snapshot must create exactly one existing formal RUN using current Track A/B/finalizer boundaries.

```python
from evidence_review.review_matter.formalization import formalize_snapshot


def test_formalization_does_not_promote_unselected_draft_text(formalizable_snapshot, finalized_workspace) -> None:
    assert "approximately 900 mm" not in formalizable_snapshot.selected_evidence_text
    prepared = formalize_snapshot(finalized_workspace, formalizable_snapshot)
    request = (prepared.run_directory / "review-request.json").read_text(encoding="utf-8")
    assert "approximately 900 mm" not in request
    assert prepared.run_id.startswith("RUN-")
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_formalization_adapter.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_formalization_adapter.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Matter→Formal is one-way
- Existing evidence validation, Track A/B and finalizer semantics unchanged
- Adapter verifies exact snapshot + current finalized evidence before run creation
- No Final Run code writes Matter state directly
- Direct formal review compatibility path remains operational

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/review_matter/formalization.py tests/integration/review_matter/test_formalization_adapter.py src/evidence_review/review_question.py src/evidence_review/review_run.py
git commit -m "feat(mig-10): connect Matter snapshots to formal review core"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-10-formalization-adapter`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-11: Matter-to-FormalRun lineage, multi-run history and current-review pointer

**Dependencies:** MIG-10, #157 CLOSED

**Files:**
- Create: `src/evidence_review/review_matter/formal_run_binding.py`
- Create: `src/evidence_review/current_review_binding.py`
- Create: `tests/integration/review_matter/test_multi_run_history.py`
- Create: `tests/unit/test_current_review_binding.py`
- Modify: `src/evidence_review/review_matter/schema.sql`
- Modify: `src/evidence_review/review_run.py`

**Interfaces:**
- Consumes: MIG-10 formal RUN identity and #157 run-local packet authority.
- Produces: `bind_formal_run(...)`, `list_formal_runs(...)`, `bind_current_review(...)`, and `resolve_current_review(...)`.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

Two different Matter revisions must be able to finalize to two immutable RUNs without overwriting either packet. A stale/missing current-review pointer or packet hash mismatch must fail closed. Prior Human Decision must not be projected onto the new run.

```python
from evidence_review.current_review_binding import bind_current_review, resolve_current_review
from evidence_review.review_matter.formal_run_binding import bind_formal_run, list_formal_runs


def test_one_matter_can_bind_two_immutable_runs_without_overwrite(matter_store, repository_root, finalized_run_v1, finalized_run_v2) -> None:
    bind_formal_run(matter_store, "MATTER-001", finalized_run_v1.snapshot_id, finalized_run_v1.run_id, finalized_run_v1.packet_sha256)
    bind_formal_run(matter_store, "MATTER-001", finalized_run_v2.snapshot_id, finalized_run_v2.run_id, finalized_run_v2.packet_sha256)
    runs = list_formal_runs(matter_store, "MATTER-001")
    assert [item.run_id for item in runs] == [finalized_run_v1.run_id, finalized_run_v2.run_id]
    bind_current_review(repository_root, finalized_run_v2.run_id, finalized_run_v2.packet_sha256)
    assert resolve_current_review(repository_root).run_id == finalized_run_v2.run_id
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/unit/test_current_review_binding.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/unit/test_current_review_binding.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- RUN-local final-review-packet.json remains authority
- Matter stores append-only run bindings
- .ers/current-review.json, if used, contains exact run_id + packet SHA only
- No workspace-global packet copy/overwrite
- Packet-hash-bound decisions remain isolated per run

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/review_matter/formal_run_binding.py src/evidence_review/current_review_binding.py tests/integration/review_matter/test_multi_run_history.py tests/unit/test_current_review_binding.py src/evidence_review/review_matter/schema.sql src/evidence_review/review_run.py
git commit -m "feat(mig-11): add multi-run Matter lineage"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-11-matter-run-lineage`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-12: ReviewMatter application service and CLI surface

**Dependencies:** MIG-06, MIG-11

**Files:**
- Create: `src/evidence_review/review_matter/service.py`
- Create: `tests/integration/review_matter/test_cli_flow.py`
- Modify: `src/evidence_review/cli_parser.py`
- Modify: `src/evidence_review/cli_handlers.py`
- Modify: `src/evidence_review/command_dispatch.py`

**Interfaces:**
- Consumes: MIG-06 navigation and MIG-11 formal-run lineage.
- Produces: `ReviewMatterService` plus `review-matter` CLI commands for create/status/add-issue/bind-evidence/search/select-evidence/formalize.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

End-to-end CLI test must fail before commands exist: create matter → add issue → bind evidence → navigation search → select evidence → status → formalize. Invalid expected revision must return a stable non-zero failure without partial mutation.

```python
from evidence_review.command_dispatch import main


def test_review_matter_cli_requires_expected_revision(tmp_path, capsys) -> None:
    workspace = tmp_path / "workspace"
    assert main(["review-matter", "create", "--workspace", str(workspace), "--matter-id", "MATTER-001", "--title", "Review"]) == 0
    code = main(["review-matter", "add-issue", "--workspace", str(workspace), "--matter-id", "MATTER-001", "--expected-revision", "0", "--issue-id", "ISSUE-001", "--question", "Check width"])
    assert code == 2
    assert "MATTER_REVISION_CONFLICT" in capsys.readouterr().err
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_cli_flow.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_cli_flow.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Commands: review-matter create/status/add-issue/bind-evidence/search/select-evidence/formalize
- Every mutation requires expected revision or equivalent ETag token
- CLI never fabricates timestamps/hashes supplied by user
- Formalize returns immutable snapshot/run identities
- Existing review-question/review-run commands remain compatible

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/review_matter/service.py tests/integration/review_matter/test_cli_flow.py src/evidence_review/cli_parser.py src/evidence_review/cli_handlers.py src/evidence_review/command_dispatch.py
git commit -m "feat(mig-12): expose ReviewMatter application workflow"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-12-review-matter-cli`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-13: Protected Workbench server on shared HTTP transport

**Dependencies:** MIG-12, #159 CLOSED, #164 CLOSED

**Files:**
- Create: `src/evidence_review/workbench/__init__.py`
- Create: `src/evidence_review/workbench/local_server.py`
- Create: `src/evidence_review/workbench/routes.py`
- Create: `tests/unit/workbench/test_routes.py`
- Create: `tests/integration/workbench/test_local_server_security.py`
- Modify: `src/evidence_review/command_dispatch.py`

**Interfaces:**
- Consumes: MIG-12 application service plus the exact shared transport helper delivered by #159 and reviewer provenance contract from #164.
- Produces: `serve_workbench(...)` and tokenized Workbench routes that enforce Matter expected revision.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

Workbench duplicate Host/Origin, oversized/full/partial body, invalid token, stale expected revision and reviewer mismatch tests must fail before the server exists. Transport semantics must match the canonical helper introduced by #159 rather than copied code.

```python
import http.client

from evidence_review.workbench.local_server import serve_workbench


def test_workbench_rejects_duplicate_host_headers(workbench_workspace) -> None:
    server = serve_workbench(workbench_workspace, "MATTER-001", reviewer_id="reviewer-01", detach=True)
    conn = http.client.HTTPConnection("127.0.0.1", server.port)
    conn.putrequest("GET", server.path, skip_host=True)
    conn.putheader("Host", "127.0.0.1")
    conn.putheader("Host", "localhost")
    conn.endheaders()
    response = conn.getresponse()
    assert response.status == 400
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/workbench/test_local_server_security.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/workbench/test_local_server_security.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Loopback-only/tokenized server
- Canonical shared Host/Origin/body-drain/security-header primitives reused
- Reviewer identity is explicit; no maintainer-specific default
- Mutation endpoints enforce expected Matter revision
- Windows transport stress inherited from #159 plus Workbench route coverage

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/workbench/__init__.py src/evidence_review/workbench/local_server.py src/evidence_review/workbench/routes.py tests/unit/workbench/test_routes.py tests/integration/workbench/test_local_server_security.py src/evidence_review/command_dispatch.py
git commit -m "feat(mig-13): add protected ReviewMatter workbench server"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-13-protected-workbench-server`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-14: Workbench UI for MatterIssue, navigation and draft/formal separation

**Dependencies:** MIG-13

**Files:**
- Create: `src/evidence_review/workbench/view_model.py`
- Create: `src/evidence_review/workbench/html_renderer.py`
- Create: `src/evidence_review/workbench/assets/workbench.css`
- Create: `src/evidence_review/workbench/assets/workbench.js`
- Create: `tests/unit/workbench/test_view_model.py`
- Create: `tests/unit/workbench/test_html_renderer.py`
- Modify: `src/evidence_review/packaging/file_selection.py`

**Interfaces:**
- Consumes: MIG-13 protected Workbench server.
- Produces: `build_workbench_view_model(...)` and `render_workbench_html(...)` with explicit work/draft/stale/formal-run-history presentation states.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

Rendered Workbench must not use Formal statuses for draft findings; navigation result, draft observation, stale issue and formal run history must be visibly distinct. A draft PASS-like wording cannot render as final approval badge.

```python
from evidence_review.workbench.html_renderer import render_workbench_html
from evidence_review.workbench.view_model import build_workbench_view_model


def test_workbench_draft_cannot_render_as_formal_approval(matter_with_draft) -> None:
    model = build_workbench_view_model(matter_with_draft)
    html = render_workbench_html(model)
    assert 'data-surface="workbench"' in html
    assert "검토 초안" in html
    assert "READY_FOR_HUMAN_REVIEW" not in html
    assert "human-decision" not in html
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/unit/workbench/test_html_renderer.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/unit/workbench/test_html_renderer.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- MatterIssue work states visible
- Evidence citations open with exact provenance
- Draft/Unverified/Needs confirmation labels explicit
- Formalize disabled when blockers exist
- Keyboard focus/desktop responsive/browser console manual QA PASS
- No Human Decision form in mutable Workbench

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/workbench/view_model.py src/evidence_review/workbench/html_renderer.py src/evidence_review/workbench/assets/workbench.css src/evidence_review/workbench/assets/workbench.js tests/unit/workbench/test_view_model.py tests/unit/workbench/test_html_renderer.py src/evidence_review/packaging/file_selection.py
git commit -m "feat(mig-14): add ReviewMatter workbench UI"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-14-review-matter-workbench-ui`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-15: Drawing/visual workflow integration with ReviewMatter and ReviewScope

**Dependencies:** MIG-05, MIG-07, MIG-14, #160 CLOSED, #165 CLOSED, #166 CLOSED

**Files:**
- Create: `src/evidence_review/review_matter/visual_binding.py`
- Create: `tests/integration/review_matter/test_visual_binding.py`
- Modify: `src/evidence_review/case_visual.py`
- Modify: `src/evidence_review/drawing_review/visual_handoff.py`
- Modify: `src/evidence_review/drawing_review/visual_pages.py`

**Interfaces:**
- Consumes: MIG-05 Matter source binding, MIG-07 ReviewScope, existing visual confirmation contracts, and #160/#165/#166 closures.
- Produces: `bind_visual_case_to_matter(...)`; `prepare_visual_analysis_handoff` accepts ReviewScope-derived issue context while preserving candidate/confirmation authority.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

A Matter must not resolve a visual attachment by basename or attach a DrawingCandidate from another visual case/source hash. Visual analysis generated from ReviewScope must remain observation/candidate authority only until existing confirmation paths promote values.

```python
import pytest

from evidence_review.review_matter.visual_binding import bind_visual_case_to_matter


def test_visual_candidate_from_other_source_cannot_bind_to_matter(matter_store, visual_case_a, candidate_from_visual_case_b) -> None:
    with pytest.raises(ValueError, match="VISUAL_SOURCE_BINDING_MISMATCH"):
        bind_visual_case_to_matter(
            matter_store,
            matter_id="MATTER-001",
            expected_revision=1,
            visual_case=visual_case_a,
            candidates=(candidate_from_visual_case_b,),
        )
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_visual_binding.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_visual_binding.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Matter→CASE-VIS→attachment_id→source SHA lineage exact
- ReviewScope accepted by visual handoff without mandatory QuestionPlan object
- No visual AI estimate becomes ConfirmedInput automatically
- Existing drawing confirmation/calibration append-only semantics preserved
- Duplicate basename, MIME mismatch and decoder boundary regressions inherited from #165/#166

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/review_matter/visual_binding.py tests/integration/review_matter/test_visual_binding.py src/evidence_review/case_visual.py src/evidence_review/drawing_review/visual_handoff.py src/evidence_review/drawing_review/visual_pages.py
git commit -m "feat(mig-15): bind visual review to ReviewMatter"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-15-matter-visual-integration`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-16: Conservative source revision impact and issue invalidation

**Dependencies:** MIG-05, MIG-15

**Files:**
- Create: `src/evidence_review/review_matter/impact.py`
- Create: `tests/unit/review_matter/test_impact.py`
- Create: `tests/integration/review_matter/test_revision_invalidation.py`
- Modify: `src/evidence_review/review_matter/invalidation.py`
- Modify: `src/evidence_review/review_matter/service.py`

**Interfaces:**
- Consumes: MIG-05 dependency records and MIG-15 visual/source bindings.
- Produces: `evaluate_source_change_impact(before, after, dependencies) -> ImpactReport` and service-level invalidation application.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

Rev.3→Rev.4 of a source used by Issue A must never retain Issue A as READY_TO_FORMALIZE unless exact source identity is unchanged. Unknown or unmodelled impact must invalidate rather than retain.

```python
from evidence_review.review_matter.impact import evaluate_source_change_impact


def test_changed_source_hash_invalidates_every_dependent_issue() -> None:
    report = evaluate_source_change_impact(
        before={"source_id": "SRC-1", "sha256": "a" * 64},
        after={"source_id": "SRC-1", "sha256": "b" * 64},
        dependencies={"ISSUE-1": {"SRC-1"}, "ISSUE-2": {"SRC-2"}},
    )
    assert report.stale_issue_ids == ("ISSUE-1",)
    assert "ISSUE-1" not in report.retained_issue_ids
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_revision_invalidation.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_revision_invalidation.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Exact same source hash may retain binding
- Changed source hash invalidates all issues dependent on that source in v1
- Unknown dependency graph is treated as affected
- No AI-based geometric impact heuristic in v1
- Re-formalization impossible until stale required issues are re-reviewed

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/review_matter/impact.py tests/unit/review_matter/test_impact.py tests/integration/review_matter/test_revision_invalidation.py src/evidence_review/review_matter/invalidation.py src/evidence_review/review_matter/service.py
git commit -m "feat(mig-16): invalidate affected Matter issues conservatively"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-16-source-revision-impact`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-17: Shared presentation primitives without Workbench/Formal authority collapse

**Dependencies:** MIG-14, MIG-15, #152 CLOSED, #156 CLOSED

**Files:**
- Create: `src/evidence_review/presentation/__init__.py`
- Create: `src/evidence_review/presentation/tokens.py`
- Create: `tests/unit/presentation/test_presentation_contract.py`
- Modify: `src/evidence_review/review_packet/html_renderer.py`
- Modify: `src/evidence_review/review_packet/presentation.py`
- Modify: `src/evidence_review/workbench/html_renderer.py`
- Modify: `src/evidence_review/workbench/assets/workbench.css`

**Interfaces:**
- Consumes: MIG-14 Workbench UI and current Formal Review renderer after #152/#156.
- Produces: shared presentation tokens only; Workbench and Formal Review retain separate route/state authorities.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

A structural test must prove that Workbench can share visual tokens with Formal Review while Formal Review still rejects mutable Matter actions and Workbench still cannot persist Human Decision. Protected asset routes remain Formal Review specific unless explicitly authorized.

```python
from evidence_review.presentation.tokens import presentation_tokens
from evidence_review.review_packet.html_renderer import render_review_html
from evidence_review.workbench.html_renderer import render_workbench_html


def test_shared_visual_tokens_do_not_collapse_surface_authority(formal_model, workbench_model) -> None:
    assert presentation_tokens()["control_height_px"] >= 36
    formal = render_review_html(formal_model, page_images=None)
    workbench = render_workbench_html(workbench_model)
    assert 'data-surface="formal-review"' in formal
    assert 'data-surface="workbench"' in workbench
    assert "human-decision" in formal
    assert "human-decision" not in workbench
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/unit/presentation/test_presentation_contract.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/unit/presentation/test_presentation_contract.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Typography/control tokens shared where safe
- Distinct DOM authority markers: data-surface=workbench vs formal-review
- Formal Review remains packet-derived/read-only except Human Decision
- Workbench remains Matter-derived and has no packet decision endpoint
- #152/#156 browser acceptance remains PASS

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/presentation/__init__.py src/evidence_review/presentation/tokens.py tests/unit/presentation/test_presentation_contract.py src/evidence_review/review_packet/html_renderer.py src/evidence_review/review_packet/presentation.py src/evidence_review/workbench/html_renderer.py src/evidence_review/workbench/assets/workbench.css
git commit -m "refactor(mig-17): share review presentation primitives safely"
git rev-parse HEAD
git status --short
```

Branch: `refactor/mig-17-shared-review-presentation`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-18: Legacy formal-run association without historical reconstruction

**Dependencies:** MIG-11

**Files:**
- Create: `src/evidence_review/migration/review_matter.py`
- Create: `tests/unit/migration/test_review_matter_legacy.py`
- Create: `tests/integration/review_matter/test_legacy_run_reference.py`

**Interfaces:**
- Consumes: existing immutable RUN/packet/decision artifacts.
- Produces: `LegacyFormalReviewReference` and `legacy_reference_from_run(run_directory)` without reconstructing missing Matter history.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

Importing a historical RUN that lacks Matter history must not invent MatterIssue, DraftFinding, Matter revision, or source-impact history. Test expects a read-only LegacyFormalReviewReference with only verifiable run/packet identities.

```python
from evidence_review.migration.review_matter import legacy_reference_from_run


def test_legacy_run_reference_does_not_invent_matter_history(legacy_run_directory) -> None:
    reference = legacy_reference_from_run(legacy_run_directory)
    assert reference.run_id.startswith("RUN-")
    assert reference.packet_sha256
    assert reference.matter_revision is None
    assert reference.matter_issue_ids == ()
    assert reference.compatibility_status == "LEGACY_FORMAL_RUN"
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_legacy_run_reference.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_legacy_run_reference.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- No invented historical state
- Legacy packet/decision bytes unchanged
- Unknown historical fields remain absent/None with explicit compatibility status
- Legacy association cannot be edited as native Matter history
- Existing migration adapters remain untouched unless required

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add src/evidence_review/migration/review_matter.py tests/unit/migration/test_review_matter_legacy.py tests/integration/review_matter/test_legacy_run_reference.py
git commit -m "feat(mig-18): reference legacy runs without reconstructing Matter state"
git rev-parse HEAD
git status --short
```

Branch: `feat/mig-18-legacy-formal-reference`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-19: Packaging, release validation, skills, docs and AGENTS finalization

**Dependencies:** MIG-17, MIG-18, #161 CLOSED

**Files:**
- Create: `tests/integration/packaging/test_review_matter_runtime_package.py`
- Create: `tests/integration/release/test_review_matter_release_validation.py`
- Modify: `src/evidence_review/packaging/file_selection.py`
- Modify: `src/evidence_review/packaging/runtime_packages.py`
- Modify: `src/evidence_review/release/validator.py`
- Modify: `.agents/skills/ers-review/SKILL.md`
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `docs/CONTRACT_GOVERNANCE.md`
- Modify: `docs/REVIEWER_WORKFLOW.md`
- Modify: `docs/MANUAL_ACCEPTANCE_POLICY.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: all runtime modules from MIG-17/MIG-18 and canonical release semantics after #161.
- Produces: wheel/package completeness, release validation for the new runtime assets, final user-facing skill/docs, and migration-aware AGENTS.md.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

Wheel/runtime smoke must initially fail if review_matter/navigation/workbench assets or schema are missing. Documentation test must fail if it still says every natural-language interaction requires Planner or conflates Workbench draft state with Formal Review.

```python
from importlib import resources


def test_installed_package_contains_review_matter_schema_and_workbench_assets() -> None:
    matter_root = resources.files("evidence_review.review_matter")
    workbench_root = resources.files("evidence_review.workbench")
    assert matter_root.joinpath("schema.sql").is_file()
    assert workbench_root.joinpath("assets", "workbench.css").is_file()
    assert workbench_root.joinpath("assets", "workbench.js").is_file()
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/release/test_review_matter_release_validation.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/release/test_review_matter_release_validation.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Wheel contains all new Python modules/schema/assets
- Source checkout and installed wheel behavior parity
- Release validator checks Matter schema/runtime package completeness without user Matter data
- ERS skill describes Navigation/Matter/Formalization modes accurately
- Documentation integrity errors=0
- Full Python 3.13 packaging and offline smoke PASS

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add tests/integration/packaging/test_review_matter_runtime_package.py tests/integration/release/test_review_matter_release_validation.py src/evidence_review/packaging/file_selection.py src/evidence_review/packaging/runtime_packages.py src/evidence_review/release/validator.py .agents/skills/ers-review/SKILL.md README.md docs/README.md docs/CODEX_WORKFLOW.md docs/CONTRACT_GOVERNANCE.md docs/REVIEWER_WORKFLOW.md docs/MANUAL_ACCEPTANCE_POLICY.md AGENTS.md
git commit -m "docs(mig-19): integrate ReviewMatter into release and agent guidance"
git rev-parse HEAD
git status --short
```

Branch: `docs/mig-19-review-matter-release-integration`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

### MIG-20: Exact-HEAD real-environment migration acceptance and Epic closure

**Dependencies:** MIG-16, MIG-17, MIG-18, MIG-19

**Files:**
- Create: `docs/REVIEW_MATTER_ACCEPTANCE_2026-09-08.md`
- Create: `tests/integration/review_matter/test_end_to_end_matrix.py`

**Interfaces:**
- Consumes: merged MIG-01..MIG-19 and all prerequisite issue closures.
- Produces: executable end-to-end acceptance matrix and exact-HEAD closure report; no new product behavior is intentionally introduced.

- [ ] **Step 1: Add the focused RED test/contract before production implementation**

The acceptance matrix is written first as executable scenarios and must expose any remaining gap: navigation-only, planner formalization, explicit scope, partial multi-issue, visual confirmation, source revision invalidation, two formal runs, packet-specific Human Decision, restart/recovery, installed-wheel runtime.

```python
import pytest

SCENARIOS = (
    "navigation_only",
    "planner_formal_review",
    "explicit_scope_formal_review",
    "partial_multi_issue",
    "drawing_confirmation",
    "source_revision_invalidation",
    "two_formal_runs",
    "packet_specific_human_decision",
    "restart_recovery",
    "installed_wheel_runtime",
)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_review_matter_end_to_end_acceptance(scenario, acceptance_runner) -> None:
    result = acceptance_runner.run(scenario)
    assert result.status == "PASS", result.details
```

- [ ] **Step 2: Run only the new focused test and confirm the expected RED is the missing contract, not an unrelated host failure**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_end_to_end_matrix.py`
Expected: FAIL only for the stated RED contract; any unrelated collection/host failure is `HOLD` and must be resolved before implementation continues.

- [ ] **Step 3: Implement the smallest production boundary that satisfies the contract**

Implementation rules:
- use existing shared identifier/canonical-json/filesystem-trust primitives instead of duplicating them;
- do not weaken finalized evidence, Formal Run, Track A/B, finalizer, Rule/Math or Human Decision semantics;
- do not edit files outside the issue list unless `SCOPE_EXPANSION_REQUIRED = YES` is recorded and reviewed;
- preserve deterministic/canonical serialization at every authority boundary.

- [ ] **Step 4: Re-run focused GREEN and adjacent regression**

Run: `py -3.13 -m pytest -v tests/integration/review_matter/test_end_to_end_matrix.py`
Expected: PASS.

- [ ] **Step 5: Run issue-specific acceptance gates**

- Exact candidate SHA and clean worktree recorded
- Full pytest/Ruff/mypy/mypy-win32/compileall/documentation PASS
- Python 3.13 isolated wheel/runtime smoke PASS
- Real protected Workbench + Formal Review browser QA PASS
- 17-page CASE_DRAWING + text/reference-only scenarios PASS
- No SQLite sidecars; evidence DB exact SHA unchanged through review lifecycle
- ACTIONS state reported exactly, never inferred
- Epic can close only with no Critical/Important migration blocker

- [ ] **Step 6: Commit candidate, then verify exact HEAD before push**

```powershell
git status --short
git diff --check
git add docs/REVIEW_MATTER_ACCEPTANCE_2026-09-08.md tests/integration/review_matter/test_end_to_end_matrix.py
git commit -m "test(mig-20): close ReviewMatter migration acceptance"
git rev-parse HEAD
git status --short
```

Branch: `test/mig-20-review-matter-acceptance`

- [ ] **Step 7: Run full exact-HEAD acceptance, push only the feature branch, verify remote SHA, then open PR**

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output "$env:TEMP\ers-documentation-integrity.json"
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
git diff --check
```

Record `TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA`. Any post-acceptance edit invalidates the full gate.

---

## Epic closure gates

- All current prerequisite issues used by MIG dependencies are CLOSED or explicitly NOT_PLANNED with documented safety rationale.
- MIG-01 through MIG-20 are merged in dependency order; no required migration invariant is bypassed.
- Exact main acceptance after final merge passes full pytest/Ruff/mypy/mypy-win32/compileall/documentation.
- Installed Python 3.13 wheel/runtime smoke passes for Navigation, Matter CLI, Workbench and Formal Review.
- Real browser acceptance passes for Workbench, text/reference Formal Review and 17-page CASE_DRAWING.
- Evidence DB finalized lifecycle/logical hash/exact file SHA/no-sidecars remain invariant across the complete workflow.
- Multi-run Matter history and packet-specific Human Decision are demonstrated.
- Source revision change invalidates dependent MatterIssues conservatively.
- No unresolved Critical/Important migration blocker remains.

## Deliberately out of scope for this Epic

- Selective/risk-based removal of universal Track B audit. Keep current Track B semantics through this migration.
- AI-based automatic source-revision impact classification.
- Microservice split, graph database migration, cloud collaboration or external model API calls inside the ERS runtime.
- Rewriting finalized evidence storage or Human Decision authority.
