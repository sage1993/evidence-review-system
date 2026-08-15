# Contract Governance

## Purpose

This document governs shared machine-readable contracts used by browser review, drawing evidence, and resumable Codex workflows.

## Frozen v1 policy

Review Packet v1 is frozen. Existing v1 dataclasses, codecs, finalizer serialization, golden fixtures, and runtime packages must remain byte-compatible.

A v2 consumer must use `adapt_review_packet_v1_to_v2`. It must not reinterpret a v1 packet as native v2 data or invent resolved evidence, drawing evidence, confirmed inputs, exceptions, or conflicts that are absent from v1.

## Shared namespace policy

Do not create duplicate definitions for:

- workflow states;
- finalizer statuses;
- rule statuses;
- reason codes;
- human decisions;
- drawing geometry, origin, candidate status, quality, or physical-size trust;
- immutable attachment roles;
- Track A/Track B next actions.

Downstream work must import the shared contracts under `evidence_review.contracts` and update the shared contract through a versioned migration when a new value is required.

## Authority boundaries

- Workflow state reports progress only.
- Finalizer status is only `READY_FOR_HUMAN_REVIEW` or `ABSTAIN`.
- Rule status remains owned by the Rule Engine.
- Reason codes explain a hold or failure; they are not workflow states.
- Human decisions exist only in separate append-only records.
- Machine packets always contain `human_decision: null`.
- Drawing extraction creates candidates. Only reviewer-confirmed values may bind to Math or Rule Engine inputs.
- Project code never invokes Track A or Track B through an API. It emits a deterministic `next-action.json` handoff.

## Determinism boundary

Byte-equivalence applies to canonical machine payloads, including retrieval, calculation, rule, drawing-candidate, confirmed-input core, Review Packet v2, and v1-to-v2 adapter output.

Operational data such as timestamps, ports, access tokens, reviewer timestamps, and append-only record filenames must be kept in separate envelopes and excluded from deterministic payload comparisons.

## Completion gate

Changes to shared contracts are not complete until:

1. focused tests pass;
2. the full pytest suite passes;
3. Ruff passes;
4. strict mypy passes;
5. canonical golden fixtures remain byte-equivalent;
6. applicable human contract reviews are recorded.

Issues #5, #6, and #7 must consume these shared contracts and must not define parallel schemas or enums.
