# Reviewer Workflow

The machine packet is evidence for review, not a decision. Confirm the source quote, page, bbox, calculation trace, rule version, confidence factors, exceptions, conflicts, and abstention reasons. Record the human decision only in a separate append-only file.

## Ready case smoke check

```bash smoke
python -c "from ansim_review.review_packet.decision_record import _ALLOWED; assert 'ADDITIONAL_REVIEW_REQUIRED' in _ALLOWED"
```

A ready packet keeps `human_decision` null until the named reviewer signs a separate record.
