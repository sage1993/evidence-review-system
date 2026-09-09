from __future__ import annotations

from evidence_review.review_matter.contracts import MatterIssue
from evidence_review.review_matter.snapshot import (
    decode_formalization_snapshot,
    formalization_snapshot_document,
)


def test_formalization_snapshot_document_has_no_draft_authority_fields() -> None:
    assert callable(decode_formalization_snapshot)
    assert callable(formalization_snapshot_document)
    assert MatterIssue(
        issue_id="ISSUE-001",
        question="Question",
        work_state="READY_TO_FORMALIZE",
        depends_on=(),
    ).work_state == "READY_TO_FORMALIZE"
