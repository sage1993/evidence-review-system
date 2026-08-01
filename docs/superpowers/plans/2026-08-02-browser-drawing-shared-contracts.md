# Browser Review and Drawing Evidence Shared Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add versioned shared contracts for Review Packet v2, workflow state, drawing evidence, immutable attachments, and agent-mediated next actions while preserving byte-equivalent Review Packet v1 behavior.

**Architecture:** Keep the existing v1 dataclasses, codecs, finalizer, and renderer unchanged. Add focused v2/workflow/drawing contract modules with explicit encoders and strict decoders, then provide a deterministic v1-to-v2 adapter. JSON Schema files mirror the Python contracts for external validation and documentation.

**Tech Stack:** Python 3.11+, standard-library dataclasses and typing, canonical JSON utilities, JSON Schema Draft 2020-12 documents, pytest 8.3+, ruff 0.6+, mypy strict.

## Global Constraints

- Project code must not call OpenAI or another external model API.
- Existing Review Packet v1 canonical JSON output must remain unchanged.
- Machine packets must always contain `human_decision: null`.
- Workflow state, finalizer status, rule status, reason codes, and human decision must remain separate contracts.
- Every factual claim and confirmed drawing input must resolve to immutable source evidence.
- Unconfirmed or conflicting drawing candidates must not bind to engine inputs.
- Track A and Track B are agent-mediated file actions, not runtime API calls.
- New runtime dependencies are prohibited.
- Every task uses TDD and ends in one independently reviewable commit.

---

## File Structure

### Existing files preserved or extended

- `src/ansim_review/contracts/review.py` — existing Review Packet v1 types; only compatibility exports may be added.
- `src/ansim_review/contracts/codecs.py` — existing v1 decoders remain byte-for-byte behavior compatible; v2 decoding stays in a separate module.
- `src/ansim_review/abstention/finalizer.py` — existing v1 packet serialization remains unchanged.
- `src/ansim_review/review_packet/builder.py` — no v2 behavior until #5; M0 only confirms adapter compatibility.

### New focused modules

- `src/ansim_review/contracts/validation.py` — shared strict primitive validators for new contracts.
- `src/ansim_review/contracts/workflow.py` — workflow states, reason codes, state record, and next-action types.
- `src/ansim_review/contracts/drawing.py` — geometry, candidate, quality, trust, attachment, confirmation, and confirmed-input types.
- `src/ansim_review/contracts/review_v2.py` — v2 packet types, deterministic document encoder, and strict decoder.
- `src/ansim_review/contracts/adapters/__init__.py` — adapter package export.
- `src/ansim_review/contracts/adapters/review_v1_to_v2.py` — deterministic v1-to-v2 adapter.

### Schemas

- `schemas/review-packet-v2.schema.json`
- `schemas/workflow-state.schema.json`
- `schemas/reason-code.schema.json`
- `schemas/drawing-geometry.schema.json`
- `schemas/drawing-candidate.schema.json`
- `schemas/drawing-confirmation.schema.json`
- `schemas/confirmed-input.schema.json`
- `schemas/immutable-attachment.schema.json`
- `schemas/next-action.schema.json`

### Tests and fixtures

- `tests/golden/contracts/review-packet-v1-ready.json`
- `tests/golden/contracts/review-packet-v1-abstain.json`
- `tests/golden/contracts/review-packet-v2-from-v1-ready.json`
- `tests/golden/contracts/review-packet-v2-from-v1-abstain.json`
- `tests/unit/contracts/test_workflow_contracts.py`
- `tests/unit/contracts/test_drawing_contracts.py`
- `tests/unit/contracts/test_review_v2.py`
- `tests/unit/contracts/test_next_action_contract.py`
- `tests/integration/contracts/test_review_v1_to_v2.py`

---

### Task 1: Freeze Review Packet v1 canonical behavior

**Files:**
- Create: `tests/golden/contracts/review-packet-v1-ready.json`
- Create: `tests/golden/contracts/review-packet-v1-abstain.json`
- Create: `tests/integration/contracts/test_review_v1_golden.py`
- Read: `src/ansim_review/abstention/finalizer.py`
- Read: `src/ansim_review/contracts/codecs.py`

**Interfaces:**
- Consumes: `review_packet_document(packet: ReviewPacket) -> dict[str, object]`, `decode_review_packet(value: object) -> ReviewPacket`, `dump_bytes(value: object) -> bytes`.
- Produces: two immutable v1 fixtures and a regression test used by Tasks 3 and 6.

- [ ] **Step 1: Create a ready-state v1 fixture**

Use the exact current v1 field set:

```json
{
  "abstention_reasons": [],
  "calculations": [],
  "claims": [{"citation_ids":["CIT-E1"],"claim_id":"C1","numeric_tokens":[],"text":"검토 주장"}],
  "confidence": null,
  "human_decision": null,
  "question": "검토 질문",
  "rules": [],
  "run_id": "RUN-V1-READY",
  "status": "READY_FOR_HUMAN_REVIEW"
}
```

- [ ] **Step 2: Create an abstain-state v1 fixture**

Use the same field set with `status: ABSTAIN` and `abstention_reasons: ["MISSING_REQUIRED_INPUT"]`.

- [ ] **Step 3: Write the failing golden regression test**

```python
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.codecs import decode_review_packet
from ansim_review.abstention.finalizer import review_packet_document

FIXTURES = Path(__file__).parents[2] / "golden" / "contracts"


def test_v1_golden_packets_round_trip_byte_equivalent() -> None:
    for name in ("review-packet-v1-ready.json", "review-packet-v1-abstain.json"):
        raw = (FIXTURES / name).read_bytes()
        packet = decode_review_packet(__import__("json").loads(raw))
        assert dump_bytes(review_packet_document(packet)) == raw.rstrip(b"\n")
```

- [ ] **Step 4: Run the focused test**

Run: `pytest tests/integration/contracts/test_review_v1_golden.py -v`

Expected: PASS. If it fails, correct fixture ordering/content; do not modify production v1 code.

- [ ] **Step 5: Run existing v1 tests**

Run: `pytest tests/unit/review_packet tests/integration/review_packet -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/golden/contracts tests/integration/contracts/test_review_v1_golden.py
git commit -m "test: freeze review packet v1 contracts"
```

---

### Task 2: Add shared strict validation primitives and workflow contracts

**Files:**
- Create: `src/ansim_review/contracts/validation.py`
- Create: `src/ansim_review/contracts/workflow.py`
- Create: `schemas/workflow-state.schema.json`
- Create: `schemas/reason-code.schema.json`
- Create: `tests/unit/contracts/test_workflow_contracts.py`

**Interfaces:**
- Produces: `WorkflowState`, `ReasonCode`, `WorkflowStateRecord`, `workflow_state_document`, `decode_workflow_state_record`.
- Later tasks consume: `expect_mapping`, `expect_sequence`, `expect_string`, `expect_int`, `expect_literal`, `expect_sha256`, `reject_unknown` from `validation.py`.

- [ ] **Step 1: Write failing workflow tests**

Cover:

```python
def test_reason_code_cannot_be_used_as_workflow_state() -> None:
    with pytest.raises(ValueError, match="unsupported workflow_state"):
        decode_workflow_state_record({
            "format": "ansim/workflow-state",
            "version": 1,
            "run_id": "RUN-1",
            "workflow_state": "SOURCE_HASH_MISMATCH",
            "finalizer_status": None,
            "reason_codes": [],
            "resumable": False,
        })


def test_review_completed_is_not_a_machine_workflow_state() -> None:
    with pytest.raises(ValueError, match="unsupported workflow_state"):
        decode_workflow_state_record({... "workflow_state": "REVIEW_COMPLETED", ...})


def test_ready_for_review_requires_finalizer_status() -> None:
    with pytest.raises(ValueError, match="finalizer_status is required"):
        decode_workflow_state_record({... "workflow_state": "READY_FOR_REVIEW", "finalizer_status": None, ...})
```

Also test that `BLOCKED` is resumable only when explicitly `true`, `FAILED` cannot be resumable, and non-blocked states reject reason codes except finalizer abstention reasons.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/contracts/test_workflow_contracts.py -v`

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement `validation.py`**

Implement strict helpers matching the existing codec style, including lowercase 64-character SHA-256 validation and unknown-field rejection. Do not import private helpers from `contracts/codecs.py`.

- [ ] **Step 4: Implement `workflow.py`**

Define literals:

```python
WorkflowState = Literal[
    "RECEIVED", "CLASSIFYING_INPUTS", "ROLE_CONFIRMATION_REQUIRED",
    "PENDING_REFERENCE_INGESTION", "PENDING_DRAWING_INGESTION",
    "INPUT_CONFIRMATION_REQUIRED", "READY_TO_EVALUATE",
    "RETRIEVING_EVIDENCE", "RUNNING_MATH", "RUNNING_RULES",
    "WAITING_TRACK_A", "WAITING_TRACK_B", "FINALIZING",
    "READY_FOR_REVIEW", "BLOCKED", "FAILED",
]

ReasonCode = Literal[
    "SOURCE_CONFLICT", "SOURCE_HASH_MISMATCH", "MISSING_REQUIRED_INPUT",
    "UNAPPROVED_RULE", "MISSING_FORMULA", "STALE_SNAPSHOT",
    "MATH_ENGINE_ERROR", "CITATION_AUDIT_FAILED", "TRACK_B_REJECTED",
    "ROLE_CONFIRMATION_REQUIRED", "DRAWING_QUALITY_REJECTED",
    "DRAWING_CONFIRMATION_REQUIRED",
]
```

Define a frozen dataclass with `format`, `version`, `run_id`, `workflow_state`, `finalizer_status`, `reason_codes`, and `resumable`. Enforce cross-field rules in the decoder.

- [ ] **Step 5: Add JSON Schemas**

Use Draft 2020-12, `additionalProperties: false`, exact enums, and `if/then` constraints for `READY_FOR_REVIEW`, `BLOCKED`, and `FAILED`.

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/unit/contracts/test_workflow_contracts.py -v`

Expected: PASS.

- [ ] **Step 7: Run lint and type checks**

Run:

```bash
ruff check src/ansim_review/contracts/validation.py src/ansim_review/contracts/workflow.py tests/unit/contracts/test_workflow_contracts.py
mypy src/ansim_review/contracts/validation.py src/ansim_review/contracts/workflow.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ansim_review/contracts/validation.py src/ansim_review/contracts/workflow.py schemas/workflow-state.schema.json schemas/reason-code.schema.json tests/unit/contracts/test_workflow_contracts.py
git commit -m "feat: separate workflow and review statuses"
```

---

### Task 3: Define Review Packet v2 contracts and provenance validation

**Files:**
- Create: `src/ansim_review/contracts/review_v2.py`
- Create: `schemas/review-packet-v2.schema.json`
- Create: `tests/unit/contracts/test_review_v2.py`

**Interfaces:**
- Consumes: existing `Citation`, `CalculationResult`, `RuleResult`, `ConfidenceResult`; validation helpers from Task 2.
- Produces: `EvidenceRecord`, `ReviewPacketV2`, `review_packet_v2_document`, `decode_review_packet_v2`.

- [ ] **Step 1: Write failing v2 tests**

Test at minimum:

```python
def test_v2_rejects_non_null_human_decision() -> None: ...
def test_v2_rejects_claim_without_citations() -> None: ...
def test_v2_rejects_unknown_fields() -> None: ...
def test_v2_rejects_invalid_manifest_hash() -> None: ...
def test_v2_rejects_unregistered_numeric_token() -> None: ...
def test_v2_document_is_canonical_and_round_trips() -> None: ...
```

Numeric provenance rule: every claim `numeric_tokens` entry must appear in either an evidence record `numeric_tokens` collection or a calculation `raw_result`/`display_result` value referenced by the claim.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/contracts/test_review_v2.py -v`

Expected: FAIL because `review_v2.py` does not exist.

- [ ] **Step 3: Implement focused v2 dataclasses**

Define:

```python
@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    citation: Citation
    quote: str
    numeric_tokens: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class ReviewPacketV2:
    format: Literal["ansim/review-packet"]
    version: Literal[2]
    run_id: str
    case_id: str
    question: str
    finalizer_status: FinalizerStatus
    snapshot_sha256: str
    rule_manifest_sha256: str
    formula_manifest_sha256: str
    claims: tuple[Claim, ...]
    evidence: tuple[EvidenceRecord, ...]
    drawing_evidence: tuple[DrawingEvidence, ...]
    confirmed_inputs: tuple[ConfirmedInput, ...]
    calculations: tuple[CalculationResult, ...]
    rule_evaluations: tuple[RuleResult, ...]
    exceptions: tuple[str, ...]
    conflicts: tuple[str, ...]
    confidence: ConfidenceResult | None
    abstention_reasons: tuple[str, ...]
    human_decision: None
    compatibility_source_version: int | None = None
```

Use explicit encoder functions; do not use `dataclasses.asdict`.

- [ ] **Step 4: Implement strict decoding and cross-reference validation**

Validate citation IDs against evidence records, calculation IDs against packet calculations, rule citations through existing citation decoders, unique IDs, and numeric-token provenance.

- [ ] **Step 5: Add the v2 JSON Schema**

Mirror the Python contract, require all fields, reject additional properties, require `human_decision` to be JSON `null`, and reference inline definitions for citations, claims, calculations, rules, evidence, drawing evidence, and confirmed inputs.

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/unit/contracts/test_review_v2.py -v`

Expected: PASS.

- [ ] **Step 7: Run lint and type checks**

Run:

```bash
ruff check src/ansim_review/contracts/review_v2.py tests/unit/contracts/test_review_v2.py
mypy src/ansim_review/contracts/review_v2.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ansim_review/contracts/review_v2.py schemas/review-packet-v2.schema.json tests/unit/contracts/test_review_v2.py
git commit -m "feat: define review packet v2 contract"
```

---

### Task 4: Define drawing geometry, candidates, confirmations, and confirmed inputs

**Files:**
- Create: `src/ansim_review/contracts/drawing.py`
- Create: `schemas/drawing-geometry.schema.json`
- Create: `schemas/drawing-candidate.schema.json`
- Create: `schemas/drawing-confirmation.schema.json`
- Create: `schemas/confirmed-input.schema.json`
- Create: `tests/unit/contracts/test_drawing_contracts.py`

**Interfaces:**
- Produces: `Geometry`, `DrawingEvidence`, `DrawingCandidate`, `DrawingConfirmation`, `ConfirmedInput`, decoder and document functions.
- Consumed by: Review Packet v2 and downstream issue #6.

- [ ] **Step 1: Write failing geometry and input tests**

Test all geometry types and both coordinate systems. Add failures for malformed coordinates, inverted BBOX, polygons with fewer than four positions or an unclosed ring, non-decimal input values, and unconfirmed/conflicting input binding.

Required tests:

```python
def test_geometry_round_trips_point_bbox_linestring_polygon() -> None: ...
def test_reviewer_created_candidate_is_distinguishable() -> None: ...
def test_metadata_only_cannot_automatically_pass_quality_gate() -> None: ...
def test_unconfirmed_candidate_cannot_decode_as_confirmed_input() -> None: ...
def test_conflicting_candidate_cannot_decode_as_confirmed_input() -> None: ...
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/contracts/test_drawing_contracts.py -v`

Expected: FAIL because drawing contracts do not exist.

- [ ] **Step 3: Implement geometry contracts**

Store coordinates as immutable tuples. Validate:

- `POINT`: exactly two finite numbers.
- `BBOX`: exactly four finite numbers ordered left/bottom/right/top or left/top/right/bottom according to declared coordinate system, with non-inverted axes.
- `LINESTRING`: at least two two-number positions.
- `POLYGON`: one exterior ring with at least four positions and first position equal to last.

- [ ] **Step 4: Implement candidate and quality contracts**

Require stable IDs, source SHA-256, positive page number, origin, type, geometry, extractor metadata for extractor candidates, and reviewer metadata only in separate confirmation records. Reject `origin=REVIEWER_MANUAL` with `status=UNCONFIRMED` unless it has a stable reviewer-created annotation ID.

- [ ] **Step 5: Implement confirmation and confirmed-input contracts**

Use decimal strings validated by `Decimal(value)` and reject NaN/infinity. Confirmed inputs require `status=CONFIRMED`, evidence references, and confirmation record path/hash. The decoder must reject source candidate states `UNCONFIRMED` and `CONFLICT` when supplied as binding context.

- [ ] **Step 6: Add JSON Schemas**

Use discriminated `oneOf` branches for geometry types. Add `if/then` rules for candidate origin, quality/trust combinations, confirmation actions, and confirmed-input status.

- [ ] **Step 7: Run focused tests**

Run: `pytest tests/unit/contracts/test_drawing_contracts.py -v`

Expected: PASS.

- [ ] **Step 8: Run lint and type checks**

Run:

```bash
ruff check src/ansim_review/contracts/drawing.py tests/unit/contracts/test_drawing_contracts.py
mypy src/ansim_review/contracts/drawing.py
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/ansim_review/contracts/drawing.py schemas/drawing-geometry.schema.json schemas/drawing-candidate.schema.json schemas/drawing-confirmation.schema.json schemas/confirmed-input.schema.json tests/unit/contracts/test_drawing_contracts.py
git commit -m "feat: define drawing evidence contracts"
```

---

### Task 5: Define immutable attachments and agent-mediated next actions

**Files:**
- Modify: `src/ansim_review/contracts/workflow.py`
- Modify: `src/ansim_review/contracts/drawing.py`
- Create: `schemas/immutable-attachment.schema.json`
- Create: `schemas/next-action.schema.json`
- Create: `tests/unit/contracts/test_next_action_contract.py`

**Interfaces:**
- Produces: `ImmutableAttachment`, `NextAction`, `decode_immutable_attachment`, `decode_next_action`, and document encoders.
- Consumed by downstream issue #7.

- [ ] **Step 1: Write failing attachment and next-action tests**

Test missing/invalid SHA-256, zero byte size, absolute paths, `..` path segments, unsupported MIME/role, malformed resume commands, and Track B emission without validated Track A.

```python
def test_attachment_rejects_external_absolute_path() -> None: ...
def test_attachment_rejects_parent_path_escape() -> None: ...
def test_track_b_action_requires_validated_track_a() -> None: ...
def test_next_action_round_trips_canonical_document() -> None: ...
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/contracts/test_next_action_contract.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement immutable attachment validation**

Require relative POSIX paths under `inputs/original/`, lowercase SHA-256, byte size greater than zero, non-empty MIME, and role from `REFERENCE_DOCUMENT | CASE_DRAWING | CASE_TABLE | SUPPORTING_IMAGE`.

- [ ] **Step 4: Implement next-action validation**

Actions are `PRODUCE_TRACK_A` and `PRODUCE_TRACK_B`. Enforce matching workflow state, relative artifact paths without traversal, a non-empty argv tuple beginning with `python`, and `track_a_validated=True` for Track B.

- [ ] **Step 5: Add JSON Schemas**

Mirror all Python validations that JSON Schema can express. Keep path traversal and command semantic checks in Python tests.

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/unit/contracts/test_next_action_contract.py -v`

Expected: PASS.

- [ ] **Step 7: Run lint and type checks**

Run:

```bash
ruff check src/ansim_review/contracts/workflow.py src/ansim_review/contracts/drawing.py tests/unit/contracts/test_next_action_contract.py
mypy src/ansim_review/contracts/workflow.py src/ansim_review/contracts/drawing.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ansim_review/contracts/workflow.py src/ansim_review/contracts/drawing.py schemas/immutable-attachment.schema.json schemas/next-action.schema.json tests/unit/contracts/test_next_action_contract.py
git commit -m "feat: define resumable agent action contracts"
```

---

### Task 6: Implement deterministic Review Packet v1-to-v2 adapter

**Files:**
- Create: `src/ansim_review/contracts/adapters/__init__.py`
- Create: `src/ansim_review/contracts/adapters/review_v1_to_v2.py`
- Create: `tests/golden/contracts/review-packet-v2-from-v1-ready.json`
- Create: `tests/golden/contracts/review-packet-v2-from-v1-abstain.json`
- Create: `tests/integration/contracts/test_review_v1_to_v2.py`

**Interfaces:**
- Consumes: `ReviewPacket`, `ReviewPacketV2`, `review_packet_v2_document`.
- Produces: `adapt_review_packet_v1_to_v2(packet: ReviewPacket, *, case_id: str, snapshot_sha256: str, rule_manifest_sha256: str, formula_manifest_sha256: str) -> ReviewPacketV2`.

- [ ] **Step 1: Write failing adapter tests**

Test ready and abstain fixtures, empty drawing collections, preserved claims/calculations/rules/confidence, `compatibility_source_version=1`, and byte-equivalent repeated output.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/integration/contracts/test_review_v1_to_v2.py -v`

Expected: FAIL because adapter does not exist.

- [ ] **Step 3: Implement the adapter**

Map v1 fields directly. Set:

```python
drawing_evidence=()
confirmed_inputs=()
evidence=()
exceptions=()
conflicts=()
compatibility_source_version=1
```

Do not synthesize evidence records from citation IDs because v1 does not contain resolved quote metadata. Allow compatibility-mode v2 packets to preserve claims while marking missing resolved evidence through `compatibility_source_version=1`; strict native-v2 decoding must still require resolved evidence.

- [ ] **Step 4: Create canonical golden outputs**

Use `dump_bytes(review_packet_v2_document(adapted))` to generate ready and abstain fixtures.

- [ ] **Step 5: Run adapter tests twice**

Run:

```bash
pytest tests/integration/contracts/test_review_v1_to_v2.py -v
pytest tests/integration/contracts/test_review_v1_to_v2.py -v
```

Expected: both PASS with identical hashes.

- [ ] **Step 6: Run all contract tests**

Run: `pytest tests/unit/contracts tests/integration/contracts -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ansim_review/contracts/adapters tests/golden/contracts/review-packet-v2-from-v1-*.json tests/integration/contracts/test_review_v1_to_v2.py
git commit -m "feat: adapt review packet v1 to v2"
```

---

### Task 7: Document integration gates and verify the complete repository

**Files:**
- Modify: `docs/superpowers/plans/2026-08-01-evidence-review-system-master-roadmap.md`
- Modify: `AGENTS.md`
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `docs/REVIEWER_WORKFLOW.md`

**Interfaces:**
- Consumes: all contracts from Tasks 1–6.
- Produces: explicit M0 completion gate for #5, #6, and #7.

- [ ] **Step 1: Update the master roadmap**

Insert M0 before existing milestones and state that #5, #6, and #7 must import shared contracts rather than define duplicate enums or schemas.

- [ ] **Step 2: Update AGENTS.md**

Add a contract-governance section:

```text
- Do not duplicate workflow, finalizer, reason-code, drawing, or human-decision enums.
- Review Packet v1 is frozen; use the adapter for v2 consumers.
- Machine packets always retain human_decision: null.
- Completion claims require pytest, ruff, mypy, and applicable human contract review.
```

- [ ] **Step 3: Update workflow documentation**

Document the `next-action.json` handoff and explain that project code never invokes Track A or Track B itself.

- [ ] **Step 4: Run the full automated suite**

Run:

```bash
pytest -q
ruff check .
mypy
```

Expected: all pass.

- [ ] **Step 5: Verify canonical fixtures**

Run a Python script that loads every JSON file in `tests/golden/contracts`, canonicalizes it with `dump_bytes`, and confirms the bytes match the stored file without trailing newline.

- [ ] **Step 6: Perform contract self-review**

Confirm no `TBD`, `TODO`, duplicate enum definitions, non-null machine human decisions, or v1 production changes exist.

- [ ] **Step 7: Commit**

```bash
git add AGENTS.md docs/CODEX_WORKFLOW.md docs/REVIEWER_WORKFLOW.md docs/superpowers/plans/2026-08-01-evidence-review-system-master-roadmap.md
git commit -m "docs: establish shared browser drawing contracts"
```

- [ ] **Step 8: Open a draft pull request**

Title:

```text
feat: define shared browser and drawing contracts
```

Body must reference `Closes #15`, list the seven task commits, record automated command results, and leave the three human contract approvals unchecked.
