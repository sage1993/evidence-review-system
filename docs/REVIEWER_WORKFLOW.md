# Reviewer Workflow

The machine packet is evidence for review, not a decision. Confirm the source quote, page, bbox or geometry, calculation trace, rule version, confidence factors, exceptions, conflicts, and abstention reasons. Record the human decision only in a separate append-only file.

Shared machine/human authority boundaries and version compatibility are governed by `docs/CONTRACT_GOVERNANCE.md`.

## Confirm source identity first

Every reviewed PDF must be traceable to a source-batch entry and immutable source SHA-256. A filename or display title is not sufficient proof of identity and must never be interpreted as a document type or legal authority.

Confirm:

- the source PDF SHA-256 matches the registered source;
- the document ID was explicitly supplied or deterministically derived from source bytes;
- the revision ID matches the source hash;
- the parser artifact belongs to the same registered source;
- the cited page and geometry exist within the verified page bounds.

## Distinguish the four status domains

Do not interpret similarly named values as interchangeable.

- **Workflow state** reports processing progress, such as `PENDING_PARSER_OUTPUT`, `WAITING_TRACK_A`, `INPUT_CONFIRMATION_REQUIRED`, `BLOCKED`, or `READY_FOR_REVIEW`.
- **Finalizer status** is only `READY_FOR_HUMAN_REVIEW` or `ABSTAIN`.
- **Rule status** is the result of one approved Rule-as-Code evaluation.
- **Human decision** is a separate reviewer record and is never stored in the machine packet.

Reason codes explain why a workflow is blocked or failed. They are not workflow states and do not constitute a human decision.

## Review the finalized run

Open the run-specific `review.html` created by `review-run finalize`. Confirm that each factual claim is connected to the displayed source identity, revision, page, evidence ID, source hash, and bounding box or drawing geometry. Check all calculation substitutions and registered result hashes rather than reproducing arithmetic in prose.

Review the matching run-specific `final-review-packet.json` and confirm:

- `human_decision` is `null`;
- the finalizer status is either `READY_FOR_HUMAN_REVIEW` or `ABSTAIN`;
- every RuleResult has its version, status, citations, and result hash;
- confidence factors identify their values, weights, contributions, and sources;
- every applicable abstention reason is preserved.

For a native Review Packet v2, also confirm:

- the packet format and version match the published Review Packet schema;
- snapshot, rule-manifest, and formula-manifest hashes are present;
- every claim resolves to an evidence record;
- every displayed numeric token resolves to source evidence or a Math Engine result;
- every confirmed drawing input identifies immutable source bytes, page, geometry, and confirmation record;
- unconfirmed or conflicting drawing candidates are not present as engine inputs.

A packet with `compatibility_source_version: 1` is a deterministic v1 wrapper. Empty v2-only evidence and drawing collections mean the information did not exist in v1; they must not be treated as proof that the source was reviewed under the native v2 contract.

The root `runs/final-review-packet.json` is only the packet explicitly selected with `review-run finalize --publish`. Publication does not constitute reviewer approval and does not create a signature.

## Review drawing geometry and confirmation

Drawing evidence may use `POINT`, `BBOX`, `LINESTRING`, or `POLYGON` geometry. Confirm that the geometry type is appropriate for the source object:

- a dimension endpoint or entrance location may use `POINT`;
- a text region may use `BBOX`;
- a dimension or road edge may use `LINESTRING`;
- a site or building boundary may use `POLYGON`.

Confirm that extractor candidates and reviewer-created annotations are visibly distinguishable. Reviewer-created annotations must retain their own stable annotation ID. Drawing quality values (`PASS`, `REVIEW_REQUIRED`, `REJECTED`) are not finalizer statuses or human decisions.

## Record the human decision separately

Only after completing the review should the named reviewer create the separate append-only decision record. Never edit the machine packet to insert a human decision.

`REVIEW_COMPLETED` is a display projection derived from a valid separate decision record. It is not a stored machine workflow state.

## Create the release process attestation

Release authorization uses the strict `evidence-review/human-attestation` version 1 contract. The canonical file is:

```text
releases/evidence-review-v1.0/human-attestation.json
```

The named reviewer must create this file only after examining the exact release candidate. It is append-only and must not overwrite a prior record. The record must contain:

- `assurance_level: PROCESS_ATTESTATION`;
- `attestation: REVIEWED_AND_ACCEPTED_FOR_RELEASE`;
- a non-empty reviewer ID;
- an ISO-8601 timestamp with timezone;
- the exact release candidate hash;
- the exact packet hash;
- every required manual check with `status: PASS` and a non-empty evidence locator.

Validate the record before release:

```powershell
evidence-review release validate-attestation `
  --attestation releases/evidence-review-v1.0/human-attestation.json `
  --candidate-hash <release-candidate-sha256> `
  --packet-hash <final-review-packet-sha256>
```

A successful validation reports:

```json
{
  "format": "evidence-review/human-attestation-status",
  "status": "VALID",
  "assurance_level": "PROCESS_ATTESTATION",
  "cryptographic_identity_verified": false
}
```

This record is a controlled internal process attestation. Possession of the JSON file is **not cryptographic proof of reviewer identity**. The system does not verify a private key, certificate, account session, or handwritten identity. The release manifest therefore always records `cryptographic_identity_verified: false`.

A legacy `ansim/human-acceptance` record may be inspected for migration history, but it **cannot authorize a new release**. Copying a legacy `signature` string into the new record is prohibited. Missing, malformed, hash-mismatched, stale, or legacy-only records keep the release `BLOCKED`.

### Threat model and operational assumptions

The process attestation is designed to reject stale or mismatched release artifacts, incomplete checklist records, accidental reuse of an older packet, configured reviewer ID mismatch, and legacy acceptance files presented as current authorization.

It does not protect against a malicious reviewer, a stolen or copied JSON file, a compromised filesystem, an operator who supplies a false reviewer ID when no expected reviewer policy is configured, or artifact changes made after validation outside the controlled release process.

Operational use therefore assumes:

- reviewer identity is checked through an external access control or organizational process;
- only authorized reviewers can create files in the attestation directory;
- checklist evidence is retained and independently reviewable;
- the release build and attestation validation run on a trusted host;
- outputs are not modified after validation and before distribution.

These assumptions explain why the assurance level is `PROCESS_ATTESTATION` and why `cryptographic_identity_verified` remains `false`.

## Ready case smoke check

```bash smoke
python -c "from ansim_review.review_packet.decision_record import _ALLOWED; assert 'ADDITIONAL_REVIEW_REQUIRED' in _ALLOWED"
```

A ready packet keeps `human_decision` null until the named reviewer records a separate decision.
