# Reviewer Workflow

The machine packet is evidence for review, not a decision. Confirm the source quote, page, bbox, calculation trace, rule version, confidence factors, exceptions, conflicts, and abstention reasons. Record the human decision only in a separate append-only file.

## Review the finalized run

Open the run-specific `review.html` created by `review-run finalize`. Confirm that each factual claim is connected to the displayed source identity, revision, page, evidence ID, source hash, and bounding box. Check all calculation substitutions and registered result hashes rather than reproducing arithmetic in prose.

Review the matching run-specific `final-review-packet.json` and confirm:

- `human_decision` is `null`;
- the status is either `READY_FOR_HUMAN_REVIEW` or `ABSTAIN`;
- every RuleResult has its version, status, citations, and result hash;
- confidence factors identify their values, weights, contributions, and sources;
- every applicable abstention reason is preserved.

The root `runs/final-review-packet.json` is only the packet explicitly selected with `review-run finalize --publish`. Publication does not constitute reviewer approval and does not create a signature.

## Record the human decision separately

Only after completing the review should the named reviewer create the separate append-only decision or acceptance record. Never edit the machine packet to insert a human decision. A release acceptance record must bind the exact release candidate hash and packet hash.

## Ready case smoke check

```bash smoke
python -c "from ansim_review.review_packet.decision_record import _ALLOWED; assert 'ADDITIONAL_REVIEW_REQUIRED' in _ALLOWED"
```

A ready packet keeps `human_decision` null until the named reviewer signs a separate record.
