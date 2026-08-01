# Browser Review and Drawing Evidence Shared Contracts Design

## Purpose

Define the shared versioned contracts required by issues #5, #6, and #7 before browser review, drawing ingestion, or Codex orchestration implementation begins.

The existing runtime already produces Review Packet v1 artifacts. This design preserves those artifacts while adding an explicit Review Packet v2 contract, drawing-evidence contracts, workflow-state separation, immutable attachment metadata, and agent-mediated next-action documents.

## Design Principles

1. Preserve existing Review Packet v1 canonical output.
2. Add v2 through new contracts and an explicit deterministic adapter.
3. Keep workflow progress, finalizer result, rule result, reason codes, and human decision in separate namespaces.
4. Keep machine packets immutable and force `human_decision` to remain `null`.
5. Bind every factual claim and confirmed drawing input to immutable evidence.
6. Treat drawing extraction as candidate generation only; reviewer confirmation is required before engine binding.
7. Keep project code API-free. Track A and Track B are agent-mediated file actions.
8. Separate deterministic payloads from operational envelopes containing timestamps, ports, tokens, or reviewer filenames.

## Contract Boundaries

### Review Packet v1

The existing `ReviewPacket` type, decoder, finalizer output, and canonical JSON remain unchanged. New v1 golden fixtures freeze ready and abstain examples.

### Review Packet v2

The v2 envelope adds:

- `format: ansim/review-packet`
- `version: 2`
- `case_id`
- snapshot, rule-manifest, and formula-manifest hashes
- resolved evidence records
- drawing evidence
- confirmed inputs
- rule evaluations
- explicit exception, conflict, confidence, and abstention sections
- `human_decision: null`

A v1-to-v2 adapter converts only information present in v1. Missing v2-only collections are empty and compatibility metadata records the source version. The adapter must not invent case, drawing, or evidence data.

### Status namespaces

Workflow state records progress only. Finalizer status remains `READY_FOR_HUMAN_REVIEW | ABSTAIN`. Rule status and human decision reuse existing contracts. Failures and holds are reason codes attached to `BLOCKED` or `FAILED` workflow states.

`REVIEW_COMPLETED` is not stored in a machine packet. It is a UI projection derived from a verified human-decision record.

### Drawing evidence

Drawing geometry supports `POINT`, `BBOX`, `LINESTRING`, and `POLYGON`. Each geometry declares `PDF_BOTTOM_LEFT_POINTS` or `IMAGE_TOP_LEFT_PIXELS`.

Candidates declare their origin as `EXTRACTOR` or `REVIEWER_MANUAL`. Candidate status supports `UNCONFIRMED`, `ACCEPTED`, `REJECTED`, `EDITED`, `CREATED`, and `CONFLICT`.

Drawing quality uses `PASS`, `REVIEW_REQUIRED`, or `REJECTED`. Physical-size trust uses `PDF_MEDIABOX_VERIFIED`, `USER_CONFIRMED`, `METADATA_ONLY`, or `UNKNOWN`. `METADATA_ONLY` cannot automatically yield `PASS`.

Confirmed inputs contain decimal values as strings, units, source hashes, page and geometry references, and a separate append-only confirmation-record reference. Unconfirmed or conflicting candidates cannot become engine inputs.

### Immutable attachments

Runtime processing uses a copied immutable attachment under the run or case directory. The attachment contract records the original name, stored relative path, SHA-256, byte size, MIME, and role. External mutable paths are not runtime authority.

### Agent-mediated actions

When the workflow reaches `WAITING_TRACK_A` or `WAITING_TRACK_B`, it writes `next-action.json`. The document identifies the input bundle, instructions, expected output, and resume command. Track B actions are emitted only after deterministic validation of Track A output.

## Determinism

Deterministic payloads include retrieval, calculation, rule, drawing-candidate, confirmed-input core, v2 packet, and v1-to-v2 adapter output. Operational envelopes containing run IDs, timestamps, browser ports, access tokens, or reviewer filenames are excluded from byte-equivalence assertions.

## Compatibility

- Existing v1 codecs and finalizer behavior remain supported.
- New code consumes v2 contracts without modifying v1 output.
- The adapter is the only supported automatic v1-to-v2 conversion path.
- Downstream issues must import shared enums and codecs rather than defining copies.

## Error Handling

- Unknown fields are rejected.
- Invalid SHA-256 values are rejected.
- Mixed status namespaces are rejected.
- Non-null machine `human_decision` is rejected.
- Claims without citations are rejected.
- Invalid geometry and out-of-contract coordinate systems are rejected.
- Unconfirmed or conflicting inputs are rejected at confirmed-input decoding.
- Track B next actions are rejected unless Track A validation is complete.

## Testing Strategy

1. Freeze v1 ready and abstain packets as canonical golden fixtures.
2. Add unit tests for status separation, reason codes, v2 decoding, geometry, confirmed inputs, immutable attachments, and next actions.
3. Add deterministic v1-to-v2 adapter integration tests.
4. Run full `pytest`, `ruff check`, and strict `mypy`.

## Downstream Gates

- #5 consumes Review Packet v2 and status contracts.
- #6 consumes geometry, drawing candidate, confirmation, quality, trust, and confirmed-input contracts.
- #7 consumes workflow, reason-code, immutable-attachment, and next-action contracts.
- #8 treats this design and implementation as milestone M0.
