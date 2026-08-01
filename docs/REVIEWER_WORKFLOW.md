# Reviewer Workflow

The machine packet is evidence for review, not a decision. Confirm the source quote, page, bbox or geometry, calculation trace, rule version, confidence factors, exceptions, conflicts, and abstention reasons. Record the human decision only in a separate append-only file.

Shared machine/human authority boundaries and version compatibility are governed by `docs/CONTRACT_GOVERNANCE.md`.

## Distinguish the four status domains

Do not interpret similarly named values as interchangeable.

- **Workflow state** reports processing progress, such as `WAITING_TRACK_A`, `INPUT_CONFIRMATION_REQUIRED`, `BLOCKED`, or `READY_FOR_REVIEW`.
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

- the packet declares `format: ansim/review-packet` and `version: 2`;
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

Only after completing the review should the named reviewer create the separate append-only decision or acceptance record. Never edit the machine packet to insert a human decision. A release acceptance record must bind the exact release candidate hash and packet hash.

`REVIEW_COMPLETED` is a display projection derived from a valid separate decision record. It is not a stored machine workflow state.

## Ready case smoke check

```bash smoke
python -c "from ansim_review.review_packet.decision_record import _ALLOWED; assert 'ADDITIONAL_REVIEW_REQUIRED' in _ALLOWED"
```

A ready packet keeps `human_decision` null until the named reviewer signs a separate record.
