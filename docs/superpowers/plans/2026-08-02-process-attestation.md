# Named Reviewer Process Attestation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the misleading `signature` acceptance field with a strict named-reviewer process attestation whose guarantees and release status are explicit.

**Architecture:** Define a new `evidence-review/human-attestation` contract, validate exact release and packet hashes plus required checklist evidence, and report `PROCESS_ATTESTATION` with `cryptographic_identity_verified=false`. Keep the old `ansim/human-acceptance` format behind a read-only inspection adapter that cannot authorize a new release.

**Tech Stack:** Python 3.11 standard library, dataclasses, pathlib, canonical JSON, JSON Schema documents, pytest.

## Global Constraints

- Runtime dependencies remain empty.
- This implementation does not add cryptographic signing or key management.
- The system does not claim to authenticate the human reviewer.
- Candidate hash and packet hash must exactly match current release inputs.
- Attestation records are append-only and must not overwrite an existing file.
- Missing, malformed, stale, or mismatched attestation keeps the release `BLOCKED`.
- New documentation and artifacts do not use `signature` terminology for human approval.
- PR #26 assurance vocabulary must already be merged.

---

## File Map

### Create

- `schemas/human-attestation.schema.json`: strict version 1 external contract.
- `src/ansim_review/release/attestation.py`: decoder, validator, canonical document, and append-only writer.
- `src/ansim_review/release/legacy_acceptance.py`: read-only decoder for old `ansim/human-acceptance` records.
- `tests/unit/release/test_attestation.py`: strict contract and writer tests.
- `tests/unit/release/test_legacy_acceptance.py`: inspection-only compatibility tests.

### Modify

- `src/ansim_review/release/acceptance.py`: compatibility re-export or deprecation shim only; no new release authorization.
- `src/ansim_review/release/validator.py`: release status and assurance fields.
- `src/ansim_review/cli.py`: attestation validation/status command if acceptance is currently CLI-driven.
- `tests/integration/release/test_acceptance_record.py`: migrate to attestation semantics.
- `tests/integration/release/test_release_validator.py`: `BLOCKED`/`RELEASE_READY` integration.
- `tests/unit/contracts/test_schema_documents.py`: schema validation registration.
- `README.md`: exact guarantee and operator workflow.
- `docs/REVIEWER_WORKFLOW.md`: reviewer attestation procedure.
- `docs/OFFLINE_ASSURANCE.md`: clarify that process attestation is separate from offline assurance.

## Public Interfaces

```python
AttestationStatement = Literal["REVIEWED_AND_ACCEPTED_FOR_RELEASE"]
AttestationAssurance = Literal["PROCESS_ATTESTATION"]

@dataclass(frozen=True, slots=True)
class HumanAttestation:
    reviewer_id: str
    reviewed_at: datetime
    attestation: AttestationStatement
    release_candidate_hash: str
    packet_hash: str
    checks: tuple[AttestationCheck, ...]


def decode_attestation(value: object) -> HumanAttestation:
    ...


def validate_attestation(
    path: Path,
    *,
    expected_candidate_hash: str,
    expected_packet_hash: str,
) -> HumanAttestation:
    ...


def write_attestation(path: Path, attestation: HumanAttestation) -> str:
    """Write with exclusive creation and return canonical SHA-256."""
```

Required output semantics:

```json
{
  "release_status": "RELEASE_READY",
  "attestation_assurance": "PROCESS_ATTESTATION",
  "cryptographic_identity_verified": false
}
```

---

### Task 1: Define the strict attestation schema and decoder

**Files:**
- Create: `schemas/human-attestation.schema.json`
- Create: `src/ansim_review/release/attestation.py`
- Create: `tests/unit/release/test_attestation.py`
- Modify: `tests/unit/contracts/test_schema_documents.py`

**Interfaces:**
- Produces: `HumanAttestation`, `AttestationCheck`, `decode_attestation()`

- [ ] **Step 1: Write a valid fixture helper**

```python
def _attestation(candidate_hash: str = "a" * 64, packet_hash: str = "b" * 64) -> dict[str, object]:
    return {
        "format": "evidence-review/human-attestation",
        "version": 1,
        "assurance_level": "PROCESS_ATTESTATION",
        "reviewer_id": "reviewer@example.com",
        "reviewed_at": "2026-08-02T02:00:00+09:00",
        "attestation": "REVIEWED_AND_ACCEPTED_FOR_RELEASE",
        "release_candidate_hash": candidate_hash,
        "packet_hash": packet_hash,
        "checks": [
            {"check_id": check_id, "status": "PASS", "evidence": f"evidence/{check_id}"}
            for check_id in REQUIRED_CHECK_IDS
        ],
    }
```

- [ ] **Step 2: Write failing strict-contract tests**

Reject:

```text
format ansim/human-acceptance
unknown field signature
unknown top-level field
wrong assurance_level
free-text attestation
blank reviewer_id
timestamp without timezone
uppercase or malformed SHA-256
duplicate check_id
missing required check
unknown check status
empty evidence path
```

- [ ] **Step 3: Run focused tests**

Run: `pytest tests/unit/release/test_attestation.py tests/unit/contracts/test_schema_documents.py -v`

Expected: FAIL because the new module/schema do not exist.

- [ ] **Step 4: Implement dataclasses and strict decoder**

Use the existing contract validation helpers. Required top-level fields must equal exactly:

```python
{
    "format",
    "version",
    "assurance_level",
    "reviewer_id",
    "reviewed_at",
    "attestation",
    "release_candidate_hash",
    "packet_hash",
    "checks",
}
```

Parse timestamps with `datetime.fromisoformat()` and require `tzinfo is not None`.

- [ ] **Step 5: Add JSON Schema and schema-document registration**

Use `additionalProperties: false` at every object level and constants for format, version, assurance, statement, and `PASS` status.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/unit/release/test_attestation.py tests/unit/contracts/test_schema_documents.py -v
git add schemas/human-attestation.schema.json src/ansim_review/release/attestation.py tests/unit/release/test_attestation.py tests/unit/contracts/test_schema_documents.py
git commit -m "feat: define named reviewer process attestation"
```

### Task 2: Validate exact release hashes and required checks

**Files:**
- Modify: `src/ansim_review/release/attestation.py`
- Modify: `tests/unit/release/test_attestation.py`

**Interfaces:**
- Produces: `validate_attestation(path, expected_candidate_hash, expected_packet_hash)`

- [ ] **Step 1: Add failing hash and checklist tests**

```text
candidate hash differs by one character -> reject
packet hash differs by one character    -> reject
check status PENDING                    -> reject
check status FAIL                       -> reject
required evidence blank                 -> reject
same required check twice               -> reject
```

- [ ] **Step 2: Run tests and confirm failure**

- [ ] **Step 3: Implement exact comparison after structural decoding**

Raise stable errors:

```text
RELEASE_CANDIDATE_HASH_MISMATCH
PACKET_HASH_MISMATCH
MISSING_ATTESTATION_CHECK:<id>
DUPLICATE_ATTESTATION_CHECK:<id>
ATTESTATION_CHECK_NOT_PASSED:<id>
```

Do not use case-insensitive hash comparison.

- [ ] **Step 4: Return the typed attestation, not a weakened summary dict**

Downstream release code must consume the validated object and cannot reread unvalidated JSON.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/unit/release/test_attestation.py -v
git add src/ansim_review/release/attestation.py tests/unit/release/test_attestation.py
git commit -m "fix: bind release attestation to exact artifacts"
```

### Task 3: Add canonical append-only attestation writing

**Files:**
- Modify: `src/ansim_review/release/attestation.py`
- Modify: `tests/unit/release/test_attestation.py`

**Interfaces:**
- Produces: `attestation_document(attestation) -> dict[str, object]`
- Produces: `write_attestation(path, attestation) -> str`

- [ ] **Step 1: Add failing writer tests**

Assert:

```text
first write succeeds
second write to same path raises FileExistsError
written bytes equal canonical dump_bytes(document)
returned hash equals SHA-256 of written bytes
check ordering is deterministic by REQUIRED_CHECK_IDS
```

- [ ] **Step 2: Implement exclusive binary write**

```python
path.parent.mkdir(parents=True, exist_ok=True)
content = dump_bytes(attestation_document(attestation))
with path.open("xb") as stream:
    stream.write(content)
return hashlib.sha256(content).hexdigest()
```

- [ ] **Step 3: Run tests and commit**

```bash
pytest tests/unit/release/test_attestation.py -v
git add src/ansim_review/release/attestation.py tests/unit/release/test_attestation.py
git commit -m "feat: write append-only release attestations"
```

### Task 4: Isolate old acceptance records as inspection-only legacy data

**Files:**
- Create: `src/ansim_review/release/legacy_acceptance.py`
- Modify: `src/ansim_review/release/acceptance.py`
- Create: `tests/unit/release/test_legacy_acceptance.py`

**Interfaces:**
- Produces: `inspect_legacy_acceptance(path: Path) -> LegacyAcceptanceSummary`
- No function in this module returns release authorization.

- [ ] **Step 1: Write failing legacy inspection tests**

Load the old format with `signature` and assert the summary includes:

```text
format
reviewer_id
reviewed_at
candidate hash
packet hash
warning = LEGACY_UNVERIFIED_ACCEPTANCE
can_authorize_release = false
```

- [ ] **Step 2: Assert old records cannot pass the new validator**

```python
with pytest.raises(ValueError, match="unsupported attestation format"):
    validate_attestation(old_path, expected_candidate_hash=..., expected_packet_hash=...)
```

- [ ] **Step 3: Implement explicit legacy decoder**

Preserve only inspection fields. Do not rename `signature` to `attestation`, do not emit a new record automatically, and do not expose a boolean that can be mistaken for validation success.

- [ ] **Step 4: Make `acceptance.py` a compatibility import shim**

Either delete old authorization logic or make `validate_acceptance_record()` raise a deprecation error directing callers to the new validator. Update all internal callers in the same task.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/unit/release/test_legacy_acceptance.py tests/unit/release/test_attestation.py -v
git add src/ansim_review/release/legacy_acceptance.py src/ansim_review/release/acceptance.py tests/unit/release/test_legacy_acceptance.py
git commit -m "refactor: isolate legacy acceptance records"
```

### Task 5: Gate release status on the attestation assurance

**Files:**
- Modify: `src/ansim_review/release/validator.py`
- Modify: `tests/integration/release/test_acceptance_record.py`
- Modify: `tests/integration/release/test_release_validator.py`

**Interfaces:**
- Release validation accepts `attestation_path: Path | None` and current candidate/packet hashes.
- Missing or invalid attestation results in `BLOCKED`, not an uncaught success path.

- [ ] **Step 1: Add failing release-state tests**

Cases:

```text
automated checks pass + no attestation          -> BLOCKED
automated checks pass + malformed attestation   -> BLOCKED
automated checks pass + stale hashes            -> BLOCKED
automated checks pass + valid attestation        -> RELEASE_READY
automated checks fail + valid attestation        -> BLOCKED
```

- [ ] **Step 2: Add assurance assertions**

For a valid record:

```python
assert report["attestation_assurance"] == "PROCESS_ATTESTATION"
assert report["cryptographic_identity_verified"] is False
```

For missing/invalid records, include deterministic reason codes without copying sensitive arbitrary record text.

- [ ] **Step 3: Run integration tests and confirm current semantics fail**

- [ ] **Step 4: Implement release gate**

Calculate automated status first. Only when automated checks pass, validate the attestation against the already-calculated candidate and packet hashes. Set `RELEASE_READY` only when both conditions pass.

- [ ] **Step 5: Ensure offline assurance and attestation assurance remain separate fields**

Do not nest human identity claims inside `offline_assurance`.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/integration/release/test_acceptance_record.py tests/integration/release/test_release_validator.py -v
git add src/ansim_review/release/validator.py tests/integration/release
git commit -m "fix: gate release readiness on process attestation"
```

### Task 6: Update reviewer workflow and CLI terminology

**Files:**
- Modify: `src/ansim_review/cli.py`
- Modify: `README.md`
- Modify: `docs/REVIEWER_WORKFLOW.md`
- Modify: `docs/OFFLINE_ASSURANCE.md`
- Modify: `tests/unit/test_documentation_contracts.py`

- [ ] **Step 1: Add documentation terminology tests**

New user-facing docs must contain:

```text
PROCESS_ATTESTATION
cryptographic identity is not verified
candidate hash
packet hash
append-only
```

Reject new user-facing occurrences of:

```text
electronic signature verified
cryptographically signed approval
signature field
```

Legacy appendix paths are exempt only when labeled legacy and unverified.

- [ ] **Step 2: Add or rename CLI command**

Preferred command:

```powershell
evidence-review release validate-attestation \
  --attestation acceptance/20260802-reviewer.json \
  --candidate-hash <sha256> \
  --packet-hash <sha256>
```

Canonical output format:

```text
evidence-review/human-attestation-status
```

- [ ] **Step 3: Document reviewer action accurately**

The reviewer confirms checklist items and issues a named process record. State explicitly that possession of the JSON file is not proof of reviewer identity.

- [ ] **Step 4: Run tests and commit**

```bash
pytest tests/unit/test_documentation_contracts.py tests/integration/release -v
git add src/ansim_review/cli.py README.md docs tests
git commit -m "docs: align release approval with process attestation"
```

### Task 7: Full verification and issue closure

- [ ] **Step 1: Run focused suites**

```bash
pytest tests/unit/release -v
pytest tests/integration/release -v
```

- [ ] **Step 2: Search terminology**

```bash
git grep -n "signature\|전자서명\|cryptographic.*approval" -- ':!src/ansim_review/release/legacy_acceptance.py' ':!tests/unit/release/test_legacy_acceptance.py'
```

Every remaining result must be corrected or explicitly identified as legacy compatibility documentation.

- [ ] **Step 3: Run full quality gate**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

- [ ] **Step 4: Commit verification corrections**

```bash
git add -A
git commit -m "test: verify release process attestation"
```

- [ ] **Step 5: PR body**

Use `Closes #20` only after all gates pass.