# Evidence Review System Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the confirmed correctness, immutable-authority, filesystem-trust, recovery/ownership, protected-presentation, and release-completeness defects identified in the 2026-09-05 forensic audit without rewriting the core architecture.

**Architecture:** Preserve the existing evidence-first / Track A / Track B / deterministic finalizer / immutable packet / separate human decision architecture. Repair the system by introducing explicit authority boundaries: audit-aware issue reduction, one-read verified artifact snapshots, attempt-owned recovery, canonical verified filesystem assets, separate archive/protected presentation projections, and complete release/runtime manifests. Each PR is independently testable and mergeable; later PRs depend only on interfaces explicitly produced by earlier PRs.

**Tech Stack:** Python 3.13, pytest, Ruff, mypy strict, SQLite, stdlib HTTP server, pypdf/pypdfium2/Pillow, Windows filesystem semantics (symlink/junction/reparse), canonical JSON and SHA-256.

**Spec:** Approved stabilization design is embedded in Sections 1-4 of this document. Audit baseline: `main@b2b485e9983a842c3b88090b2ebfe13882c0f1d0`.

**Repository destination:** `docs/superpowers/plans/2026-09-05-evidence-review-system-stabilization-implementation-plan.md`

## Global Constraints

- Baseline forensic reference is exactly `b2b485e9983a842c3b88090b2ebfe13882c0f1d0`; do not silently reinterpret a later `main` as the audited state.
- At execution time, first record `git rev-parse HEAD`, `git status --short`, branch name, and upstream SHA. Preserve unrelated local changes.
- If a finding has already been fixed on a later branch, reproduce RED on the audited baseline, then verify the existing fix against this plan instead of duplicating implementation.
- TDD is mandatory: every defect task starts with a test that fails for the audited reason, then the smallest root-cause fix, then focused GREEN, then adjacent regression.
- Do not weaken or delete an existing test merely because it conflicts with the corrected contract. If an existing test encodes the bug, replace its expected behavior and document why the old oracle was false-green.
- Machine finalization remains deterministic and offline. No model API call may be introduced into Python runtime code.
- `final-review-packet.json` remains immutable machine output; human decisions stay in separate append-only records.
- Verified input must be consumed from the same bytes/object that were hashed. A verified `Path` is not an authority object.
- Protected browser presentation must contain no base64 case/reference raster payload in HTML or JSON model; image bytes are served only through verified protected asset routes.
- Filesystem validation must reject symlinks and Windows reparse points/junctions when they cross or bypass the trusted root.
- Runtime publication is create-only where concurrent writers could otherwise overwrite a competing artifact.
- Python support remains `>=3.13,<3.14` unless a separate compatibility decision explicitly changes it.
- New runtime dependencies are forbidden except a security-driven update to an already-declared dependency.
- No stable release/tag is permitted until PR-1 through PR-6 and Stabilization Acceptance S1-S14 are all PASS.
- Each PR must end with `git diff --check`, Ruff, mypy, focused tests, adjacent subsystem tests, and the applicable platform acceptance. Full-suite execution is required before merge.

---

## 1. Baseline Evidence and Confirmed Defect Map

The audited baseline contains the following relevant contracts:

- `src/evidence_review/abstention/finalizer.py`
  - `_verify_manifest()` hashes artifact bytes but returns `Path` objects.
  - `expected_final_review_packet()` rereads those paths with `_json_file()`.
  - `partial_issue_resolution` suppresses `uncited_or_unresolved_claim` even when Track B marks a supposedly resolved claim incomplete/unsupported.
- `src/evidence_review/abstention/issue_policy.py`
  - `reconcile_issue_results()` sees Track A claims and missing inputs only; it does not see `ClaimAudit` / `TrackBAudit`.
- `src/evidence_review/review_question.py`
  - `submit_question_track_b()` treats only `READY_FOR_HUMAN_REVIEW` and `ABSTAIN` as terminal retry states; `PARTIALLY_RESOLVED` is omitted.
- `src/evidence_review/contracts/review_v2.py`
  - `_claim_document()` serializes claim id/text/citations/numeric tokens but drops `issue_ids`.
- `schemas/review-packet-v2.schema.json`
  - claim schema has no `issue_ids` property.
- `src/evidence_review/review_packet/builder.py`
  - v2 contains immutable `EvidenceRecord.quote`, but `_resolve_citation()` returns DB `raw_text` as display quote; `_v2_citations()` preserves citation identity only.
- `src/evidence_review/review_run.py`
  - `_recover_malformed_track_a_submission()` can delete `track-a-output.json` together with malformed downstream sidecars even after Track A was already validated.
- `src/evidence_review/parsing/source_batch_importer.py`
  - final publication is `if output.exists(): raise FileExistsError(output)` followed by `os.replace(temporary_db, output)`, which is not create-only and permits a check/publish race.
- `src/evidence_review/review_packet/page_image_verifier.py`
  - strong file verification exists, but it imports private `_mapping`, `_sequence`, `_page_assets` from `html_renderer`, so the verifier is not the sole authority.
- `src/evidence_review/review_packet/case_visual_projection.py`
  - `_resolve_visual_raster_path()` uses `Path.is_file()` and `read_bytes()` without canonical containment/reparse rejection.
  - untiled pages embed `data:image/png;base64,` payloads directly into the model.
- `src/evidence_review/review_packet/local_server.py`
  - `_protected_review_html()` rejects any remaining base64 anywhere in the protected HTML.
- `src/evidence_review/review_packet/decision_record.py`
  - imported `reviewed_at` timestamps have no future-bound policy; latest decision is selected by timestamp.
- `web_runtime/bootstrap.py`
  - required files are checked for existence, but manifest membership/completeness is not required; `files: []` can therefore pass hash coverage.
- `pyproject.toml`
  - baseline dependency range is `pypdf>=5,<6`, excluding the current patched 6.x line.

### Defect-to-PR mapping

| Finding / Risk | Target PR | Merge severity |
|---|---|---:|
| Track B unsupported claim can remain RESOLVED under partial policy | PR-1 | S1 HIGH |
| `PARTIALLY_RESOLVED` omitted from terminal retry | PR-1 | S2 MEDIUM |
| v2 claim `issue_ids` serialization loss | PR-1 | S2 MEDIUM |
| Manifest verify-then-reread TOCTOU (#128) | PR-2 | S1 HIGH |
| v2 immutable quote replaced by live DB quote (#129) | PR-2 | S1 HIGH |
| Track A recovery deletes valid canonical input | PR-3 | S1 HIGH |
| Source-batch `exists()` + `os.replace()` publication race | PR-3 | S1 HIGH |
| Duplicate/uneven filesystem verification (#126/#130) | PR-4 | S1 HIGH |
| CASE raster symlink/reparse escape (#127/#130) | PR-4 | S1 HIGH |
| Protected CASE base64 payload -> protected route failure | PR-5 | S1 HIGH |
| Run token asset scope ambiguous | PR-5 | S1/HIGH if per-run isolation is required |
| Human future timestamp can pin latest decision (#131) | PR-6 | S2 MEDIUM |
| Runtime manifest can omit hash coverage | PR-6 | S2 MEDIUM |
| pypdf safe-version policy blocked by `<6` | PR-6 | S2 MEDIUM / release blocker |

---

## 2. Approved Target Architecture

### 2.1 Decision authority pipeline

```text
validated Track A claims
        +
validated Track B claim_audits
        ↓
audit-aware issue reducer
        ↓
IssueResult[] after audit
        ↓
partial/global abstention gates
        ↓
FinalizerStatus
```

A claim audit with disposition other than `ACCEPT` makes every issue linked to that claim non-determinate for the purpose of `RESOLVED`/`CONDITIONAL`. If another independent issue remains determinate, the run may still be `PARTIALLY_RESOLVED`. If no determinate issue remains, the run must not be `PARTIALLY_RESOLVED`.

### 2.2 Verified artifact authority

```text
run-manifest.json
      ↓
read bytes once
      ↓
SHA-256 verify
      ↓
UTF-8 JSON decode once
      ↓
VerifiedRunSnapshot
      ↓
all finalizer consumers
```

No downstream finalizer code may reopen a manifest-bound JSON artifact after verification.

### 2.3 Attempt ownership

```text
external attempts                runtime-owned canonical/derived
track-a-attempt-N.json   ──────▶ track-a-output.json
                                  track-b-bundle.json
                                  next-action-track-b.json
                                  track-a-validation.json

track-b-attempt-N.json   ──────▶ track-b-output.json
                                  run-manifest.json
                                  final-review-packet.json
                                  review.html
```

Recovery may delete only artifacts that the current runtime operation owns and can prove it generated. Validated external/canonical inputs are preserved.

### 2.4 Presentation authority

```text
archive projection                  protected projection
------------------                  --------------------
may be self-contained               no raster bytes in HTML/model
immutable review packet             run-scoped asset allowlist
verified asset metadata             lazy protected routes
                                    actual HTTP + PNG decode acceptance
```

Archive and protected outputs are different explicit projections, not one HTML document rewritten by a sequence of regex assumptions.

---

## 3. PR Topology and Branch Policy

| Order | Branch | Purpose | Depends on |
|---:|---|---|---|
| 1 | `fix/stab-pr1-final-authority` | Track B → issue → final status + terminal status + v2 lineage | audited baseline |
| 2 | `fix/stab-pr2-verified-snapshot` | one-read verified artifacts + packet quote authority | PR-1 |
| 3 | `fix/stab-pr3-artifact-ownership` | recovery ownership + create-only DB publish | PR-2 |
| 4 | `fix/stab-pr4-filesystem-trust` | canonical verified asset/filesystem boundary | PR-3 |
| 5 | `fix/stab-pr5-protected-presentation` | protected DTO + run-scoped asset delivery | PR-4 |
| 6 | `fix/stab-pr6-release-completeness` | decision ordering + manifest completeness + dependency/release gate | PR-5 |

PR-4 and PR-5 may be developed in parallel only after PR-3 is merged and both branches start from the same PR-3 merge SHA. PR-5 must merge after PR-4 because its protected asset routes consume the canonical verified-asset interface.

### Commit discipline

- One defect-contract change per commit where possible.
- Preferred final commit sequence per PR:
  1. `test(finalizer): reproduce unsupported-claim partial false green` for the first PR defect
  2. `fix(finalizer): bind issue resolution to Track B claim audits` for the root-cause correction
  3. `test(finalizer): cover independent partial and retry regressions` for adjacent coverage
  4. `docs(stabilization): record final acceptance contract` only when documentation changes are needed.
- Do not squash away test provenance before review unless repository policy requires a squash merge; PR description must retain RED command/output.

---

# PR-1 — Final Decision Authority Convergence

**Goal:** Make final issue status consume Track B claim audits, centralize terminal finalizer status handling, and preserve claim-to-issue lineage in Review Packet v2.

**Primary files:**

- Modify: `src/evidence_review/abstention/issue_policy.py`
- Modify: `src/evidence_review/abstention/finalizer.py`
- Modify: `src/evidence_review/contracts/review.py`
- Modify: `src/evidence_review/contracts/review_v2.py`
- Modify: `schemas/review-packet-v2.schema.json`
- Modify: `src/evidence_review/review_question.py`
- Test: `tests/integration/abstention/test_finalizer.py`
- Test: `tests/unit/abstention/test_issue_reconciliation.py`
- Test: `tests/integration/review_question/test_review_question_cli.py`
- Test: `tests/unit/contracts/test_review_v2.py`
- Test: `tests/unit/contracts/test_schema_documents.py`

## Task 1.1: Replace the false-green partial-resolution oracle

**Interfaces:**

- Consumes: `Claim.issue_ids`, `TrackBAudit.claim_audits`, `IssueResult.status`.
- Produces: audit-aware `reconcile_issue_results(issue_results, *, claims, track_a_missing_inputs, claim_audits)` returning a sequence of `IssueResult`.
- Hard claim audit: any `ClaimAudit.disposition != "ACCEPT"`.
- Downgrade rule: if an issue is `RESOLVED` or `CONDITIONAL` and any linked claim has a non-ACCEPT audit, change that issue to `UNRESOLVED` while preserving evidence/facet/gap metadata.

- [ ] **Step 1: Change the existing integration oracle so the audited bug is RED**

In `tests/integration/abstention/test_finalizer.py`, replace the expectation that the unsupported claim remains resolved. The core assertion must be equivalent to:

```python
def test_partial_issue_coverage_does_not_preserve_track_b_unsupported_resolved_claim(tmp_path: Path) -> None:
    run_directory = _write_run(tmp_path, disposition="INCOMPLETE")

    packet = expected_final_review_packet(run_directory)

    by_issue = {item.issue_id: item for item in packet.issue_results}
    assert by_issue["I1"].status == "UNRESOLVED"
    assert packet.status == "ABSTAIN"
    assert "UNCITED_OR_UNRESOLVED_CLAIM" in packet.abstention_reasons
```

Do not add a special-case fixture that bypasses the real Track B validator.

- [ ] **Step 2: Run the single test and capture RED**

```bash
py -3.13 -m pytest -q tests/integration/abstention/test_finalizer.py::test_partial_issue_coverage_does_not_preserve_track_b_unsupported_resolved_claim
```

Expected audited-baseline result: FAIL because issue `I1` remains `RESOLVED` and final status is `PARTIALLY_RESOLVED`.

- [ ] **Step 3: Add unit RED for mixed accepted/unsupported issues**

Add to `tests/unit/abstention/test_issue_reconciliation.py` a two-issue case that creates claims `CL-I1`/`CL-I2`, audits `INCOMPLETE`/`ACCEPT`, and asserts final issue statuses `["UNRESOLVED", "RESOLVED"]` with `has_partial_issue_resolution(reconciled) is True`.

- [ ] **Step 4: Implement audit-aware issue reconciliation**

Modify `src/evidence_review/abstention/issue_policy.py`:

```python
from evidence_review.contracts.review import Claim, ClaimAudit, IssueResult, IssueStatus


def _nonaccepted_claim_ids(claim_audits: Sequence[ClaimAudit]) -> frozenset[str]:
    return frozenset(
        audit.claim_id for audit in claim_audits if audit.disposition != "ACCEPT"
    )
```

Extend `reconcile_issue_results()` with keyword-only `claim_audits: Sequence[ClaimAudit] = ()` and build `blocked_issue_ids` by joining audit claim ids to `Claim.issue_ids`. Apply the Track A missing-input logic first, then refuse to leave a blocked issue in `_SUPPORTED_STATUSES`.

The function must reject duplicate audit claim ids and audit claim ids absent from the supplied claim set with `ValueError`.

- [ ] **Step 5: Pass validated Track B audits into the reducer**

In `src/evidence_review/abstention/finalizer.py`:

```python
issue_results = reconcile_issue_results(
    _issue_results_from_inputs(bundle.inputs),
    claims=validated_a.draft.claims,
    track_a_missing_inputs=validated_a.draft.missing_inputs,
    claim_audits=audit.claim_audits,
)
```

Derive finding codes from `audit.claim_audits`, not by reparsing the raw Track B document for authority decisions. Compute `partial_issue_resolution` only after this reducer.

- [ ] **Step 6: Run focused GREEN**

```bash
py -3.13 -m pytest -q tests/unit/abstention/test_issue_reconciliation.py tests/unit/abstention/test_issue_partial_policy.py tests/integration/abstention/test_finalizer.py
```

- [ ] **Step 7: Commit**

```bash
git add src/evidence_review/abstention/issue_policy.py src/evidence_review/abstention/finalizer.py tests/unit/abstention/test_issue_reconciliation.py tests/integration/abstention/test_finalizer.py
git commit -m "fix(finalizer): bind issue resolution to Track B claim audits"
```

## Task 1.2: Centralize terminal finalizer statuses

**Interfaces:**

- Produces: `TERMINAL_FINALIZER_STATUSES` in `contracts/review.py`.
- Consumers: question resume/retry and any later state projection that needs terminal machine status.

- [ ] **Step 1: Add a RED retry test for `PARTIALLY_RESOLVED`**

Create a run whose final packet status is `PARTIALLY_RESOLVED`, call `submit_question_track_b()` a second time with the same canonical Track B, and assert packet bytes/event count remain unchanged.

```python
before_packet = packet_path.read_bytes()
before_events = tuple((run_directory / "events").iterdir())
retried = submit_question_track_b(workspace, run_id, canonical_track_b)
assert retried.packet.status == "PARTIALLY_RESOLVED"
assert packet_path.read_bytes() == before_packet
assert tuple((run_directory / "events").iterdir()) == before_events
```

- [ ] **Step 2: Run RED**

Expected baseline failure: `ValueError("review question run is not waiting for Track B")`.

- [ ] **Step 3: Define the terminal set once**

In `src/evidence_review/contracts/review.py`:

```python
TERMINAL_FINALIZER_STATUSES: frozenset[FinalizerStatus] = frozenset(
    {"READY_FOR_HUMAN_REVIEW", "PARTIALLY_RESOLVED", "ABSTAIN"}
)
```

- [ ] **Step 4: Replace terminal comparisons in `review_question.py`**

```python
if state in TERMINAL_FINALIZER_STATUSES:
    finalized = _existing_finalized_run(run_directory)
    if finalized is None:
        raise ValueError("final review artifacts are incomplete")
    return finalized
```

Audit direct string comparisons with:

```bash
git grep -nE 'READY_FOR_HUMAN_REVIEW|PARTIALLY_RESOLVED|ABSTAIN' -- src tests
```

- [ ] **Step 5: Run GREEN and commit**

```bash
py -3.13 -m pytest -q tests/integration/review_question tests/unit/workflow/test_resume.py tests/unit/contracts/test_review_issue_results.py
git add src/evidence_review/contracts/review.py src/evidence_review/review_question.py tests/integration/review_question
git commit -m "fix(workflow): treat all finalizer outcomes as terminal retries"
```

## Task 1.3: Preserve `Claim.issue_ids` in Review Packet v2

- [ ] **Step 1: Add serialization RED**

In `tests/unit/contracts/test_review_v2.py`, construct a `Claim` with `issue_ids=("I1", "I2")` and assert:

```python
document = review_packet_v2_document(packet)
assert document["claims"][0]["issue_ids"] == ["I1", "I2"]
round_tripped = decode_review_packet_v2(document)
assert round_tripped.claims[0].issue_ids == ("I1", "I2")
```

- [ ] **Step 2: Run RED**

Expected baseline failure: `issue_ids` missing from serialized claim.

- [ ] **Step 3: Extend serializer and schema**

In `src/evidence_review/contracts/review_v2.py` serialize `"issue_ids": list(claim.issue_ids)` for every v2 claim. In `schemas/review-packet-v2.schema.json`, make `issue_ids` required and define it as a unique array of non-empty strings. v1→v2 compatibility may use an empty array; do not omit the field.

- [ ] **Step 4: Regenerate v2 golden fixtures through the canonical serializer**

Do not hand-edit JSON formatting.

- [ ] **Step 5: Run GREEN and commit**

```bash
py -3.13 -m pytest -q tests/unit/contracts/test_review_v2.py tests/unit/contracts/test_schema_documents.py tests/integration/contracts/test_review_v1_to_v2.py tests/integration/contracts/test_review_v1_golden.py
git add src/evidence_review/contracts/review_v2.py schemas/review-packet-v2.schema.json tests/unit/contracts/test_review_v2.py tests/golden/contracts
git commit -m "fix(contracts): preserve issue lineage in review packet v2"
```

## PR-1 Merge Gate

```bash
py -3.13 -m pytest -q tests/unit/abstention tests/integration/abstention
py -3.13 -m pytest -q tests/unit/contracts tests/integration/contracts
py -3.13 -m pytest -q tests/unit/review_question tests/integration/review_question
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests
py -3.13 -m mypy src/evidence_review
git diff --check
```

Required acceptance:

- Unsupported/incomplete Track B claim cannot remain the basis of a `RESOLVED/CONDITIONAL` issue.
- Legitimate mixed good/bad issues still yield `PARTIALLY_RESOLVED` when at least one independent issue remains determinate.
- Repeating Track B on `PARTIALLY_RESOLVED` is idempotent.
- v2 claim lineage round-trips exactly.

---
# PR-2 — Immutable Verified Artifact Snapshot

**Goal:** Eliminate manifest verify-then-reread TOCTOU and make immutable Review Packet v2 evidence text the display authority.

**Files:**

- Create: `src/evidence_review/abstention/verified_artifacts.py`
- Modify: `src/evidence_review/abstention/finalizer.py`
- Modify: `src/evidence_review/review_packet/builder.py`
- Test: `tests/integration/abstention/test_finalizer.py`
- Create: `tests/unit/abstention/test_verified_artifacts.py`
- Modify: `tests/unit/review_packet/test_builder.py`
- Modify: `tests/integration/review_packet/test_view_model.py`

## Task 2.1: Introduce one-read verified JSON artifacts

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class VerifiedJsonArtifact:
    name: str
    sha256: str
    raw_bytes: bytes
    document: object

@dataclass(frozen=True, slots=True)
class VerifiedRunSnapshot:
    run_id: str
    artifacts: Sequence[VerifiedJsonArtifact]

    def _artifact(self, name: str) -> VerifiedJsonArtifact:
        for artifact in self.artifacts:
            if artifact.name == name:
                return artifact
        raise KeyError(name)

    def document(self, name: str) -> object:
        return self._artifact(name).document

    def raw_bytes(self, name: str) -> bytes:
        return self._artifact(name).raw_bytes
```

- [ ] **Step 1: Add unit RED for one-read decoding**

`tests/unit/abstention/test_verified_artifacts.py` must verify:

- bytes are read once,
- SHA mismatch fails before JSON is exposed,
- invalid UTF-8/JSON fails as `ValueError`,
- duplicate/missing required artifact names fail,
- returned snapshot exposes no mutable `Path` as content authority.

- [ ] **Step 2: Implement `verify_run_snapshot()`**

Move manifest parsing/hash verification out of `_verify_manifest()` into the new module. Decode JSON from the same `raw_bytes`:

```python
try:
    document = json.loads(raw_bytes.decode("utf-8"))
except (UnicodeDecodeError, json.JSONDecodeError) as error:
    raise ValueError(f"invalid JSON artifact: {name}") from error
```

The artifact path may remain only for diagnostics; consumers use `document`/`raw_bytes`.

- [ ] **Step 3: Replace finalizer path rereads**

In `expected_final_review_packet()`:

```python
snapshot = verify_run_snapshot(run_directory, required_artifacts=_REQUIRED_ARTIFACTS)
bundle = _decode_bundle(snapshot.document("track-a-bundle.json"))
track_a_output = snapshot.document("track-a-output.json")
track_b_output = snapshot.document("track-b-output.json")
confidence_input = snapshot.document("confidence-input.json")
```

Delete every manifest-bound reread such as `_json_file(paths["track-a-bundle.json"])`, `_json_file(paths["track-a-output.json"])`, `_json_file(paths["track-b-output.json"])`, and `_json_file(paths["confidence-input.json"])`.

- [ ] **Step 4: Add integration mutation test**

Extract the current deterministic derivation body into a pure internal helper named `expected_final_review_packet_from_snapshot(snapshot: VerifiedRunSnapshot) -> ReviewPacket`. The wrapper `expected_final_review_packet(run_directory)` must do only `verify_run_snapshot(run_directory, required_artifacts=_REQUIRED_ARTIFACTS)` and then call that helper. The extracted helper must receive no artifact paths and must call `snapshot.document("track-a-bundle.json")`, `snapshot.document("track-a-output.json")`, `snapshot.document("track-b-output.json")`, and `snapshot.document("confidence-input.json")`.

Test sequence:

1. verify snapshot,
2. overwrite one artifact path with different valid JSON,
3. derive packet from the already-verified snapshot,
4. assert the result still reflects verified bytes,
5. verify a new snapshot and assert manifest hash mismatch.

- [ ] **Step 5: Run GREEN and commit**

```bash
py -3.13 -m pytest -q tests/unit/abstention/test_verified_artifacts.py tests/integration/abstention/test_finalizer.py
git add src/evidence_review/abstention tests/unit/abstention tests/integration/abstention/test_finalizer.py
git commit -m "fix(finalizer): consume manifest-verified bytes without reread"
```

## Task 2.2: Make Review Packet v2 quote the display authority

**Interfaces:**

- v2 packet record: `EvidenceRecord(evidence_id, citation, quote, numeric_tokens)`.
- DB remains authoritative only for page/reference metadata needed for rendering.
- v1 compatibility may continue using DB text because v1 has no immutable evidence record.

- [ ] **Step 1: Add RED for packet quote invariance**

In `tests/unit/review_packet/test_builder.py`:

1. build a v2 packet whose evidence quote is `"PACKET QUOTE"`,
2. DB row `raw_text` is `"DATABASE QUOTE"`,
3. call `build_review_view_model(packet, evidence_db)`,
4. assert claim citation quote is `"PACKET QUOTE"`.

Baseline must fail by returning DB text.

- [ ] **Step 2: Replace `_v2_citations()` with a v2 evidence-record index**

Add:

```python
def _v2_evidence_records(
    document: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    if document.get("version") != 2:
        return {}
    records: dict[str, Mapping[str, object]] = {}
    for index, item in enumerate(_sequence(document.get("evidence", []), "evidence")):
        record = _mapping(item, f"evidence[{index}]")
        citation = _mapping(record.get("citation"), f"evidence[{index}].citation")
        citation_id = _string(
            citation.get("citation_id"),
            f"evidence[{index}].citation.citation_id",
        )
        _string(record.get("quote"), f"evidence[{index}].quote")
        prior = records.get(citation_id)
        if prior is not None and dict(prior) != dict(record):
            raise ValueError("conflicting v2 evidence record")
        records[citation_id] = record
    return records
```

Index by citation id and retain both `citation` and `quote`. Reject conflicting duplicate citation ids/evidence ids.

- [ ] **Step 3: Split database resolution from display quote**

At projection time:

```python
resolved = _resolve_citation(connection, citation_id)
provided = provided_records.get(citation_id)
if provided is not None:
    _verify_citation_identity(_mapping(provided["citation"], "citation"), resolved)
    resolved = {**resolved, "quote": _string(provided["quote"], "evidence.quote")}
```

Do not compare packet quote to DB text and then prefer DB. Packet quote is the immutable v2 display authority.

- [ ] **Step 4: Add packet/database snapshot provenance check**

For v2, compare packet `snapshot_sha256` with evidence DB snapshot provenance. Prefer an existing evidence snapshot helper. If unavailable, read `snapshot_meta.database_snapshot_hash` through a focused builder helper. A mismatch fails before claim projection.

Add matching, mismatching, and v1 compatibility tests.

- [ ] **Step 5: Run GREEN and commit**

```bash
py -3.13 -m pytest -q tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_view_model.py
git add src/evidence_review/review_packet/builder.py tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_view_model.py
git commit -m "fix(review-packet): bind displayed evidence to immutable packet v2"
```

## PR-2 Merge Gate

```bash
py -3.13 -m pytest -q tests/integration/abstention tests/unit/abstention
py -3.13 -m pytest -q tests/unit/review_packet tests/integration/review_packet
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests
py -3.13 -m mypy src/evidence_review
git diff --check
```

Acceptance invariants:

- Every required finalizer artifact is read/hash-verified/decoded once per snapshot.
- Mutating its path after verification cannot affect the packet derived from that snapshot.
- v2 displayed quote is packet-bound.
- DB identity/snapshot mismatch fails closed.

---

# PR-3 — Recovery and Artifact Ownership

**Goal:** Prevent recovery from deleting validated inputs and make canonical DB publication create-only under concurrent writers.

**Files:**

- Modify: `src/evidence_review/review_run.py`
- Modify: `src/evidence_review/review_question.py`
- Create: `src/evidence_review/workflow/artifact_ownership.py`
- Modify: `src/evidence_review/parsing/source_batch_importer.py`
- Modify: `tests/integration/test_task8_attempt_ownership_red.py`
- Modify: `tests/integration/review_run/test_review_run.py`
- Modify: `tests/unit/parsing/test_source_batch_atomicity.py`
- Modify: `tests/unit/parsing/test_source_batch_importer.py`

## Task 3.1: Formalize runtime-owned artifact groups

**Interfaces:**

```python
IMMUTABLE_INPUTS = frozenset({
    "track-a-output.json",
    "track-b-output.json",
})
TRACK_A_DERIVED = frozenset({
    "track-b-bundle.json",
    "next-action-track-b.json",
    "track-a-validation.json",
})
FINALIZATION_DERIVED = frozenset({
    "run-manifest.json",
    "final-review-packet.json",
    "review.html",
})
```

Canonical Track A/Track B files are runtime-bound validated inputs. Cleanup may not delete them merely because downstream sidecars are malformed.

- [ ] **Step 1: Add RED preserving valid canonical Track A**

Extend `tests/integration/test_task8_attempt_ownership_red.py`:

```python
def test_malformed_track_a_sidecar_recovery_preserves_valid_canonical_track_a(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_id = prepared.run_id
    run_directory = workspace / "runs" / run_id
    first_attempt = _track_a(run_directory)
    canonical = run_directory / "track-a-output.json"
    canonical.write_bytes(first_attempt.read_bytes())
    (run_directory / "track-b-bundle.json").write_text("{broken", encoding="utf-8")

    submitted = submit_question_track_a(workspace, run_id, canonical)

    assert canonical.read_bytes() == first_attempt.read_bytes()
    assert submitted.next_action_path.is_file()
```

Baseline expected failure: recovery unlinks canonical Track A and same-path publication raises `FileNotFoundError`.

- [ ] **Step 2: Implement ownership-scoped cleanup**

Replace `_recover_malformed_track_a_submission()` behavior so it:

1. validates canonical Track A separately,
2. scans only `TRACK_A_DERIVED` for malformed JSON,
3. deletes only `TRACK_A_DERIVED`,
4. never deletes canonical Track A.

If canonical Track A itself is malformed, fail explicitly; do not delete it as “recovery.”

- [ ] **Step 3: Extend finalization recovery to the same rule**

In `review_question._recover_incomplete_finalization()`, preserve canonical Track B that entered `FINALIZING` when its identity matches the event journal. Delete only `FINALIZATION_DERIVED` for retry.

Add failure-injection where `final-review-packet.json` is malformed but canonical Track B is valid and journal-bound; retry must reuse exactly the same Track B bytes.

- [ ] **Step 4: Run GREEN and commit**

```bash
py -3.13 -m pytest -q tests/integration/test_task8_attempt_ownership_red.py tests/integration/review_run/test_review_run.py tests/integration/review_question/test_review_question_cli.py
git add src/evidence_review/review_run.py src/evidence_review/review_question.py src/evidence_review/workflow/artifact_ownership.py tests/integration/test_task8_attempt_ownership_red.py tests/integration/review_run/test_review_run.py tests/integration/review_question/test_review_question_cli.py
git commit -m "fix(recovery): preserve validated inputs by artifact ownership"
```

## Task 3.2: Make source-batch DB publication create-only

**Interface:**

```python
def _publish_create_only(source: Path, destination: Path) -> None:
    """Publish source atomically and fail if destination already exists."""
```

- [ ] **Step 1: Add barrier-based RED at exact race window**

In `tests/unit/parsing/test_source_batch_atomicity.py`, create a competing destination after the last pre-publish existence check but before publish. Required assertions:

```python
with pytest.raises(FileExistsError):
    import_source_batch(batch_root, batch, output_db, registry=registry)
assert output_db.read_bytes() == competitor_bytes
```

Baseline fails because `os.replace()` overwrites the competitor.

- [ ] **Step 2: Implement no-replace publication**

Reuse the repository's create-only publication primitive from lineage migration where possible. On same-filesystem volumes, `os.link(source, destination)` is an appropriate atomic create-only primitive. `FileExistsError` must be preserved as the public conflict signal.

Do not use another `exists()` check as the safety mechanism.

- [ ] **Step 3: Test Windows and POSIX semantics**

Acceptance is semantic: a competing output is never overwritten. If a hard-link primitive is unavailable on a target volume, use an OS-specific create-only operation; do not fall back to overwrite-then-verify.

- [ ] **Step 4: Run GREEN and commit**

```bash
py -3.13 -m pytest -q tests/unit/parsing/test_source_batch_atomicity.py tests/unit/parsing/test_source_batch_importer.py tests/integration/parsing/test_source_batch_cli.py
git add src/evidence_review/parsing/source_batch_importer.py tests/unit/parsing/test_source_batch_atomicity.py tests/unit/parsing/test_source_batch_importer.py
git commit -m "fix(parsing): publish evidence snapshots without overwrite races"
```

## PR-3 Merge Gate

```bash
py -3.13 -m pytest -q tests/integration/test_task8_attempt_ownership_red.py tests/integration/review_run tests/integration/review_question
py -3.13 -m pytest -q tests/unit/parsing tests/integration/parsing
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests
py -3.13 -m mypy src/evidence_review
git diff --check
```

Required failure-injection acceptance:

- malformed Track A sidecar -> valid canonical Track A preserved,
- interrupted finalization -> canonical Track B preserved/reused,
- competing source-batch output at publication boundary -> competitor preserved and importer fails.

---

# PR-4 — Canonical Filesystem Trust Boundary

**Goal:** Replace duplicated path/file checks with one canonical verified-asset boundary correct for POSIX symlinks and Windows reparse points/junctions.

**Files:**

- Create: `src/evidence_review/filesystem_trust.py`
- Modify: `src/evidence_review/review_packet/page_image_verifier.py`
- Modify: `src/evidence_review/review_packet/html_renderer.py`
- Modify: `src/evidence_review/review_packet/reference_pages.py`
- Modify: `src/evidence_review/review_packet/case_visual_projection.py`
- Modify: `src/evidence_review/review_packet/case_visual_asset_server.py`
- Modify: `src/evidence_review/review_packet/local_server.py`
- Modify: `src/evidence_review/contracts/run_context.py`
- Modify: `src/evidence_review/workspace_binding.py`
- Test: `tests/integration/review_packet/test_protected_image_delivery.py`
- Test: `tests/unit/review_packet/test_case_visual_projection.py`
- Test: `tests/unit/review_packet/test_reference_page_projection.py`
- Test: `tests/unit/test_active_workspace_binding.py`
- Add: `tests/unit/test_filesystem_trust.py`

## Task 4.1: Introduce canonical regular-file/regular-directory verification

**Interfaces:**

```python
REPARSE_POINT_ATTRIBUTE = 0x400


def verified_regular_directory(path: Path, *, field: str) -> Path:
    """Return strict resolved path or fail on symlink/reparse/non-directory."""


def verified_regular_file_below(
    root: Path,
    relative_parts: Sequence[str],
    *,
    field: str,
) -> Path:
    """lstat every component, reject links/reparse, resolve strict, require containment."""
```

- [ ] **Step 1: Write unit RED matrix**

`tests/unit/test_filesystem_trust.py` must cover:

- normal file below normal root -> PASS,
- final file symlink -> reject,
- intermediate directory symlink -> reject,
- traversal (`..`) -> reject,
- Windows junction/reparse intermediate component -> reject when creatable,
- Windows reparse final component -> reject when creatable,
- regular file outside root reached through a link -> reject.

Do not silently skip Windows link tests when environment can create them. If creation is impossible due host policy, record the exact OS error as acceptance evidence rather than treating it as PASS.

- [ ] **Step 2: Implement shared primitive**

Use `lstat()` component-by-component before `resolve(strict=True)`. Reject `stat.S_ISLNK()` and `st_file_attributes & 0x400`.

- [ ] **Step 3: Run GREEN and commit**

```bash
py -3.13 -m pytest -q tests/unit/test_filesystem_trust.py
git add src/evidence_review/filesystem_trust.py tests/unit/test_filesystem_trust.py
git commit -m "feat(filesystem): add canonical trusted path verification"
```

## Task 4.2: Make page image verification the only page-image authority

- [ ] **Step 1: Add structural RED**

Add a test that fails if `page_image_verifier.py` imports private verification helpers from `html_renderer` or if `html_renderer` contains a second path/hash verifier. Prefer AST/import inspection over brittle string checks.

- [ ] **Step 2: Remove verifier dependency on renderer internals**

Change `verify_review_page_images(view_model, page_image_root)` to return a `Sequence[VerifiedPageImage]`. Its implementation must enumerate each distinct `(revision_id, page_number, source_hash)` referenced by the view model, call `read_verified_page_image()` exactly once per distinct identity, preserve deterministic first-use order, and return the verified objects. The renderer consumes those objects and does not reopen/reverify their files.

- [ ] **Step 3: Delete duplicate renderer verification after callers migrate**

Before deletion:

```bash
git grep -n "_verified_page_image\|_page_assets\|read_verified_page_image" -- src tests
```

No dead verifier copy may remain.

- [ ] **Step 4: Run page-image suites and commit**

```bash
py -3.13 -m pytest -q tests/unit/review_packet/test_reference_page_projection.py tests/unit/review_packet/test_reference_viewer_authority_invariance.py tests/integration/review_packet/test_multi_document_viewer.py tests/integration/review_packet/test_protected_image_delivery.py
git add src/evidence_review/review_packet/page_image_verifier.py src/evidence_review/review_packet/html_renderer.py src/evidence_review/review_packet/reference_pages.py tests/unit/review_packet tests/integration/review_packet/test_protected_image_delivery.py
git commit -m "refactor(viewer): make page image verifier the sole asset authority"
```

## Task 4.3: Bind CASE raster resolution to the same trust boundary

- [ ] **Step 1: Add RED reproducing outside-root CASE raster symlink**

Create a valid PNG outside workspace, create expected cache path as symlink/junction to it, set matching SHA, call real case visual projection, and expect `ValueError` rather than successful projection.

- [ ] **Step 2: Replace `_resolve_visual_raster_path()` path logic**

Call `verified_regular_file_below()` against the specific case cache root, then hash the verified regular file. A valid path must remain below either the HQ cache root or normal CASE image cache root.

- [ ] **Step 3: Migrate CASE asset server and workspace binding**

Replace local regular-file/regular-child variants where they enforce the same filesystem contract. Keep route parsing/authorization separate.

For `contracts/run_context.py`, reject runs root/run directory if symlink/reparse before creating children. For `workspace_binding.py`, use `verified_regular_directory()` so junction semantics match the rest of the repository.

- [ ] **Step 4: Run Windows acceptance and commit**

```bash
py -3.13 -m pytest -q tests/unit/test_filesystem_trust.py tests/unit/test_active_workspace_binding.py tests/unit/review_packet/test_case_visual_projection.py tests/unit/review_packet/test_case_visual_asset_server.py tests/integration/review_packet/test_protected_image_delivery.py
git add src/evidence_review/filesystem_trust.py src/evidence_review/review_packet src/evidence_review/contracts/run_context.py src/evidence_review/workspace_binding.py tests/unit tests/integration/review_packet/test_protected_image_delivery.py
git commit -m "fix(filesystem): enforce canonical trust boundary for visual assets"
```

## PR-4 Merge Gate

```bash
py -3.13 -m pytest -q tests/unit/test_filesystem_trust.py tests/unit/test_active_workspace_binding.py
py -3.13 -m pytest -q tests/unit/review_packet tests/integration/review_packet
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests
py -3.13 -m mypy src/evidence_review
git diff --check
```

Record how many link/junction/reparse tests executed and how many skipped. A blanket “tests passed” without this count is insufficient evidence.

---
# PR-5 — Explicit Protected Presentation Contract

**Goal:** Stop deriving protected safety from archival HTML regex cleanup; produce a protected model with no raster payload and authorize only assets explicitly referenced by that run.

**Files:**

- Create: `src/evidence_review/review_packet/protected_projection.py`
- Modify: `src/evidence_review/review_packet/case_visual_projection.py`
- Modify: `src/evidence_review/review_packet/render_case_visual_lazy.py`
- Modify: `src/evidence_review/review_packet/case_visual_asset_server.py`
- Modify: `src/evidence_review/review_packet/local_server.py`
- Modify: `src/evidence_review/review_packet/html_renderer.py`
- Modify: `src/evidence_review/review_packet/browser_launcher.py`
- Test: `tests/integration/review_packet/test_protected_image_delivery.py`
- Test: `tests/integration/review_packet/test_local_server.py`
- Test: `tests/unit/review_packet/test_case_visual_lazy_projection.py`
- Test: `tests/unit/review_packet/test_browser_launcher.py`
- Add: `tests/integration/review_packet/test_protected_review_readiness.py`

## Task 5.1: Split archive and protected CASE visual projection

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ProtectedAssetRef:
    asset_kind: Literal["reference-page", "case-page", "case-tile"]
    route_key: str
    sha256: str

@dataclass(frozen=True, slots=True)
class ProtectedReviewProjection:
    model: dict[str, object]
    assets: Sequence[ProtectedAssetRef]
```

- [ ] **Step 1: Add RED for untiled CASE model payload**

Use the real untiled path in `test_protected_image_delivery.py`. Assert protected response is HTTP 200 and:

```python
assert b"data:image/png;base64," not in body
model = extract_review_model(body)
serialized_model = json.dumps(model, sort_keys=True)
assert "data_uri" not in serialized_model
```

On the audited baseline this fails because `case_visual_review.pages[].data_uri` remains in the JSON model and the protected transform rejects the response.

- [ ] **Step 2: Keep archive behavior explicit**

Do not remove self-contained raster support from archive projection unless a separate product decision deprecates it. Implement `build_protected_review_projection()` that copies only metadata required by browser JS and replaces raster payload fields with route metadata.

Untiled protected page shape:

```json
{
  "asset_key": "ATTACHMENT-p1",
  "attachment_id": "ATTACHMENT",
  "page": 1,
  "image_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "protected_asset": {
    "kind": "case-page",
    "route_key": "case-page/ATTACHMENT/1/0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  }
}
```

There is no `data_uri`, `image_bytes`, base64 field, or raw tile payload.

- [ ] **Step 3: Make local server render the protected projection directly**

`_protected_review_html()` may retain a final “no base64” assertion for defense in depth, but it must no longer discover/remove CASE raster payload via regex. The `review-model` inserted into protected HTML is safe before serialization.

Reference page routes should be represented in the same protected projection so all protected assets come from one asset list.

- [ ] **Step 4: Run focused GREEN and commit**

```bash
py -3.13 -m pytest -q tests/unit/review_packet/test_case_visual_lazy_projection.py tests/integration/review_packet/test_protected_image_delivery.py tests/integration/review_packet/test_local_server.py
git add src/evidence_review/review_packet/protected_projection.py src/evidence_review/review_packet/case_visual_projection.py src/evidence_review/review_packet/render_case_visual_lazy.py src/evidence_review/review_packet/local_server.py src/evidence_review/review_packet/html_renderer.py tests/unit/review_packet/test_case_visual_lazy_projection.py tests/integration/review_packet/test_protected_image_delivery.py tests/integration/review_packet/test_local_server.py
git commit -m "fix(viewer): build protected presentation without raster payloads"
```

## Task 5.2: Add explicit per-run protected asset allowlist

**Policy fixed by this plan:** a run token authorizes only image assets referenced by that run's protected projection. It is not a workspace-wide page-image capability.

- [ ] **Step 1: Add authorization RED**

Create runs A/B with distinct verified page assets. Start one server with both tokens. Request B's page identity using A's token and A's route prefix.

Corrected behavior: 404 or 403 without revealing asset existence. The audited baseline may return 200 if the workspace cache contains the requested identity.

- [ ] **Step 2: Build allowlists from `ProtectedReviewProjection.assets`**

When server configuration is created, store:

```python
run_asset_allowlists: Mapping[str, frozenset[tuple[str, str, str, str]]]
```

Use normalized route identities, never filesystem paths. Page/CASE handlers validate membership before touching the filesystem.

- [ ] **Step 3: Preserve hash verification after authorization**

Required order:

```text
route parse -> run token -> run allowlist -> canonical filesystem verification -> hash verification -> bytes
```

Authorization does not replace `read_verified_page_image()` or the CASE verified asset reader.

- [ ] **Step 4: Run GREEN and commit**

```bash
py -3.13 -m pytest -q tests/integration/review_packet/test_protected_image_delivery.py tests/integration/review_packet/test_local_server.py
git add src/evidence_review/review_packet/local_server.py src/evidence_review/review_packet/case_visual_asset_server.py src/evidence_review/review_packet/protected_projection.py tests/integration/review_packet
git commit -m "fix(server): scope protected image capabilities to each review run"
```

## Task 5.3: Distinguish dispatch from actual protected readiness

**Interface:**

```python
ReviewOpenStatus = Literal["DISPATCHED", "HTTP_READY", "VISUAL_READY", "FAILED"]
```

Do not claim visual readiness from browser/process dispatch alone.

- [ ] **Step 1: Add real-server readiness integration test**

`tests/integration/review_packet/test_protected_review_readiness.py` must start the production server entrypoint and verify:

1. protected review GET returns 200,
2. review model parses,
3. every initially required image route returns 200,
4. returned bytes decode with Pillow as PNG,
5. decoded route bytes hash equals model/metadata hash,
6. tiled and untiled CASE pages are both covered,
7. server exits cleanly after idle shutdown.

- [ ] **Step 2: Update launcher status semantics**

Keep browser dispatch result separate from server/readiness state. If browser automation is unavailable, automated result may stop at `HTTP_READY`; `VISUAL_READY` requires browser/manual evidence.

- [ ] **Step 3: Run GREEN and commit**

```bash
py -3.13 -m pytest -q tests/unit/review_packet/test_browser_launcher.py tests/integration/review_packet/test_protected_review_readiness.py tests/integration/review_packet/test_server_idle_timeout.py
git add src/evidence_review/review_packet/browser_launcher.py tests/unit/review_packet/test_browser_launcher.py tests/integration/review_packet/test_protected_review_readiness.py
git commit -m "test(viewer): gate protected readiness on HTTP and image decode"
```

## PR-5 Merge Gate

Required live acceptance on a real multi-page run:

- protected review GET = 200,
- zero `data:image/png;base64,` in body and model,
- all requested image routes authorized only for owning run,
- every sampled PNG decodes and hash matches,
- 17-page cold-cache navigation/zoom/pan remains functional,
- idle termination exits 0 and state file is cleaned,
- browser dispatch result is not used as substitute for HTTP/visual readiness.

Then run:

```bash
py -3.13 -m pytest -q tests/unit/review_packet tests/integration/review_packet
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests
py -3.13 -m mypy src/evidence_review
git diff --check
```

---

# PR-6 — Runtime and Release Completeness Gate

**Goal:** Close temporal human-decision authority, require complete runtime manifest coverage, move PDF parsing onto a supported patched dependency line, and perform clean release acceptance.

**Files:**

- Modify: `src/evidence_review/review_packet/decision_record.py`
- Modify: `tests/unit/review_packet/test_decision_record.py`
- Modify: `tests/unit/review_packet/test_decision_state.py`
- Modify: `web_runtime/bootstrap.py`
- Modify: `src/evidence_review/packaging/web_bundle.py`
- Modify: `tests/integration/packaging/test_web_bundle.py`
- Modify: `pyproject.toml`
- Modify: `tests/unit/parsing/test_pdf_page_geometry.py`
- Modify: `tests/integration/packaging/test_python_support_policy.py`
- Modify: `src/evidence_review/release/validator.py` only if release validation does not already call the runtime/package integrity gates.
- Modify: `docs/OFFLINE_EXECUTION.md`, `SECURITY.md`, `CHANGELOG.md` for externally visible policy changes.

## Task 6.1: Prevent future-dated imported decisions from pinning latest state

**Policy:** server-created decisions use trusted server time. Imported archival decisions may preserve historical `reviewed_at`, but a timestamp beyond explicit future skew is ineligible for active “latest decision” ordering.

Use:

```python
MAX_FUTURE_DECISION_SKEW = timedelta(minutes=5)
```

unless repository policy already defines a stricter shared clock-skew constant.

- [ ] **Step 1: Add RED**

Test sequence:

1. import a packet-bound decision dated years in the future,
2. write a current server decision afterward,
3. call `load_latest_valid_human_decision()`,
4. assert the future import does not dominate active state,
5. assert a normal historical import remains readable.

- [ ] **Step 2: Separate archival validity from active ordering validity**

Keep archival record parsing intact. Add:

```python
def _eligible_for_latest(
    record: HumanDecisionRecord,
    *,
    now: datetime,
) -> bool:
    reviewed_at = datetime.fromisoformat(record.reviewed_at)
    return reviewed_at <= now + MAX_FUTURE_DECISION_SKEW
```

`load_latest_valid_human_decision()` filters bound records through this helper before `max()`. If every candidate is future-ineligible, return `None` rather than selecting one.

- [ ] **Step 3: Run GREEN and commit**

```bash
py -3.13 -m pytest -q tests/unit/review_packet/test_decision_record.py tests/unit/review_packet/test_decision_state.py tests/integration/review_packet/test_persisted_decision_ui.py
git add src/evidence_review/review_packet/decision_record.py tests/unit/review_packet/test_decision_record.py tests/unit/review_packet/test_decision_state.py tests/integration/review_packet/test_persisted_decision_ui.py
git commit -m "fix(decision): bound future timestamps in active decision ordering"
```

## Task 6.2: Require runtime manifest completeness

**Contract:** every required runtime file other than the manifest itself must be present in `runtime-manifest.json`, and every manifest entry must correspond to an allowed bundled file. Empty `files` cannot pass.

- [ ] **Step 1: Add bootstrap RED cases**

Add tests through `tests/integration/packaging/test_web_bundle.py` or a focused bootstrap harness:

- `files: []` -> `RUNTIME_MANIFEST_INCOMPLETE`,
- required SQLite omitted but present on disk -> fail,
- required rules manifest omitted -> fail,
- duplicate case-folded path -> existing failure remains,
- wrong hash -> existing failure remains,
- corrupt SQLite -> existing failure remains,
- complete generated manifest -> PASS.

- [ ] **Step 2: Enforce required membership**

After `entries = load_manifest(required["runtime-manifest.json"])`:

```python
entry_paths = {entry.path for entry in entries}
required_manifest_paths = set(required_paths) - {"runtime-manifest.json"}
if not required_manifest_paths.issubset(entry_paths):
    _fail("RUNTIME_MANIFEST_INCOMPLETE")
```

Use the public-runtime required set when `public-runtime.txt` is present. Keep `runtime-manifest.json` outside self-hash membership unless the producer already implements a stable recursive-manifest scheme.

- [ ] **Step 3: Enforce producer/consumer symmetry**

In `packaging/web_bundle.py`, compare generated manifest inventory to selected bundle inventory after excluding documented control files that are intentionally not hash-bound. Add a test asserting exact set equality for the intended integrity-bound files.

- [ ] **Step 4: Run GREEN and commit**

```bash
py -3.13 -m pytest -q tests/integration/packaging/test_web_bundle.py tests/integration/packaging/test_cross_runtime_equivalence.py
git add web_runtime/bootstrap.py src/evidence_review/packaging/web_bundle.py tests/integration/packaging
git commit -m "fix(runtime): require complete manifest integrity coverage"
```

## Task 6.3: Move pypdf to a supported patched line

**Contract:** choose a pypdf range whose minimum is not affected by upstream advisories verified on implementation date. Do not blindly hard-code a version from the audit report.

- [ ] **Step 1: Re-verify upstream advisory and record chosen floor**

Use official upstream GitHub Security Advisory/release information. Record advisory id, affected range, patched version, and verification date in the PR description and `SECURITY.md` if relevant.

- [ ] **Step 2: Change only the pypdf range necessary for security support**

If the verified patched floor remains `6.15.0`, the intended range is:

```toml
"pypdf>=6.15,<7",
```

Do not change pypdfium2/Pillow ranges without separate evidence.

- [ ] **Step 3: Add dependency-policy test**

Extend `tests/integration/packaging/test_python_support_policy.py` to parse `pyproject.toml` and assert the supported pypdf range includes the chosen patched floor and no longer caps below major 6.

- [ ] **Step 4: Run PDF geometry/parser regressions**

```bash
py -3.13 -m pytest -q tests/unit/parsing/test_pdf_page_geometry.py tests/unit/parsing/test_coordinate_normalization.py tests/unit/parsing/test_odl_adapter.py tests/integration/parsing/test_generic_source_matrix.py tests/integration/packaging/test_python_support_policy.py
```

Build/install a fresh wheel in a clean environment and run one PDF parse/geometry smoke through the installed package, not source checkout.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/integration/packaging/test_python_support_policy.py SECURITY.md CHANGELOG.md
git commit -m "fix(deps): move PDF parser to patched pypdf line"
```

## Task 6.4: Clean release acceptance

- [ ] **Step 1: Build from clean exact HEAD**

```bash
git rev-parse HEAD
git status --short
```

Working tree must be clean except explicitly documented generated acceptance output outside tracked source.

- [ ] **Step 2: Run static and full automated gates**

```bash
py -3.13 -m pytest -q
py -3.13 -m ruff check src tests
py -3.13 -m mypy src/evidence_review
py -3.13 -m compileall -q src web_runtime scripts
py -3.13 scripts/validate_workspace.py .
py -3.13 scripts/build_release.py
py -3.13 scripts/validate_release.py
git diff --check
```

If release scripts require explicit arguments, use the repository-documented arguments and capture exact commands/output in the acceptance note.

- [ ] **Step 3: Test built wheel/runtime rather than source checkout only**

Create clean venv, install wheel, run CLI help, minimal deterministic review smoke, web-runtime self-test, and protected server smoke.

- [ ] **Step 4: Run Windows protected-view acceptance**

Use at least:

- one single-page reference run,
- one 17-page large/multi-page run,
- one untiled CASE visual,
- one tiled CASE visual.

For each, capture HTTP status, packet hash, image hash/decode, server exit, and browser/manual visual status separately.

- [ ] **Step 5: Add dated stabilization acceptance record when repository policy tracks acceptance evidence**

Do not rewrite prior historical acceptance records in place.

## PR-6 Merge Gate

All automated, installed-runtime, dependency, Windows protected-route, and release artifact checks must PASS. Any `NOT_RUN` item touching correctness, integrity, protected delivery, or package execution keeps release gate HOLD/BLOCK.

---

## 4. Stabilization Acceptance S1-S14

The project may leave stabilization HOLD only when all fourteen gates are evidenced on the same exact HEAD.

| Gate | Acceptance | Required result |
|---:|---|---|
| S1 | Track B unsupported claim downgrades linked issue | PASS |
| S2 | Legitimate independent partial issue remains PARTIALLY_RESOLVED | PASS |
| S3 | PARTIALLY_RESOLVED Track B retry is idempotent | PASS |
| S4 | Review Packet v2 `issue_ids` round-trip | PASS |
| S5 | Manifest-bound artifacts consumed from same verified bytes | PASS |
| S6 | v2 displayed quote remains packet quote if DB text differs | PASS |
| S7 | Track A/Track B canonical inputs survive downstream recovery | PASS |
| S8 | Concurrent source-batch publication cannot overwrite competitor | PASS |
| S9 | Symlink/junction/reparse escape matrix | PASS; execution count recorded |
| S10 | Untiled/tiled CASE protected HTML/model contains no base64 | PASS |
| S11 | Cross-run protected asset access denied | PASS |
| S12 | Protected route HTTP 200 + PNG decode/hash + idle clean exit | PASS |
| S13 | Runtime manifest completeness + corrupted/omitted file failures | PASS |
| S14 | Clean wheel/release artifact + patched pypdf + full suite/static gates | PASS |

### Release verdict rule

```text
if any S1-S14 == FAIL:      BLOCK
if any S1-S14 == NOT_RUN:   HOLD
if all S1-S14 == PASS:      stabilization gate may close
```

No manual “looks good” result can override a failing deterministic integrity gate.

---

## 5. Cross-PR Regression Matrix

| Domain | Test paths |
|---|---|
| Finalizer / partial policy | `tests/unit/abstention`, `tests/integration/abstention` |
| Track A/B workflow | `tests/unit/review_question`, `tests/integration/review_question`, `tests/integration/review_run` |
| Contract v2 | `tests/unit/contracts`, `tests/integration/contracts` |
| Evidence snapshot / parser | `tests/unit/evidence`, `tests/unit/parsing`, `tests/integration/parsing` |
| Viewer / protected server | `tests/unit/review_packet`, `tests/integration/review_packet` |
| Workflow state | `tests/unit/workflow`, `tests/integration/workflow` |
| Packaging / runtime | `tests/integration/packaging`, `tests/unit/release`, `tests/integration/release` |
| Repository-wide | `pytest -q`, Ruff, mypy, compileall, diff-check |

---

## 6. Required PR Description Evidence

Every stabilization PR description must contain these concrete fields populated from that PR's actual execution:

- Scope: finding/issue identifiers covered by the PR.
- Baseline reproduced: the exact SHA used for RED reproduction.
- Branch HEAD: the exact candidate SHA under review.
- Root cause: one precise paragraph naming the failing authority or ownership boundary.
- RED evidence: exact command plus the actual failure message/assertion.
- Fix: exact invariant enforced and explicit non-goals.
- GREEN evidence: focused test counts, adjacent test counts, full pytest result, Ruff, mypy, diff-check, and required platform/live acceptance.
- Compatibility: packet/schema impact, filesystem/platform impact, and migration impact.
- Merge gate: `PASS` only when every required item ran and passed; otherwise `HOLD` with the exact unrun/failing item.

For PR-1, for example, the scope line must name the Track B partial false-green, terminal `PARTIALLY_RESOLVED` retry, and Review Packet v2 `issue_ids` lineage defects, rather than a generic “stability fixes” label.

---

## 7. Implementation Stop Conditions

Stop the current PR and classify the result instead of widening scope when any of the following occurs:

1. RED does not reproduce because checkout is not the audited baseline. Record provenance and re-establish correct baseline.
2. A later branch already contains a materially equivalent fix. Verify it against this contract instead of reimplementing.
3. A fix requires changing immutable packet / separate human-decision architecture. Escalate as architecture change.
4. A filesystem fix works only by allowing symlink/junction traversal. Reject it.
5. A protected-presentation fix merely removes the final base64 assertion rather than removing raster payload from protected projection. Reject it.
6. A publication fix still uses an existence check followed by an overwrite-capable operation. Reject it.
7. A test passes only after weakening expected integrity/status behavior. Treat as false-green and reject.
8. pypdf update changes geometry semantics. Repair compatibility or select another verified patched version before PR-6 merge.

---

## 8. Final Self-Review Checklist for This Plan

- [x] Every confirmed high-severity finding is assigned to one PR.
- [x] Every PR has exact source/test paths.
- [x] RED behavior and corrected behavior are explicit.
- [x] New cross-PR interfaces are named before consumers use them.
- [x] Recovery and publication concurrency have deterministic failure-injection tests.
- [x] Protected delivery acceptance distinguishes browser dispatch, HTTP readiness, asset decode, and human visual QA.
- [x] Windows junction/reparse coverage is explicitly required.
- [x] Full suite/static/release gates are not substituted by focused tests.
- [x] No feature expansion is mixed into stabilization.
- [x] Release remains blocked until S1-S14 pass on one exact HEAD.

---

## Execution Handoff

Recommended mode: `superpowers:subagent-driven-development` for PR-1 through PR-3, then parallel development of PR-4/PR-5 from the same PR-3 merge SHA with two-stage review, followed by PR-6 and single-head S1-S14 acceptance.

At execution start, create an isolated worktree via `superpowers:using-git-worktrees`, record exact repository state, and begin with PR-1 Task 1.1 RED reproduction. Do not start new product features until stabilization acceptance closes.
