from evidence_review.review_run import _required_facet_completeness


def test_required_facet_completeness_is_a_non_authoritative_summary() -> None:
    assert _required_facet_completeness(
        (
            {"issue_id": "I1", "missing_facet_ids": []},
            {"issue_id": "I2", "missing_facet_ids": ["distance"]},
        )
    ) == {
        "status": "INCOMPLETE",
        "covered_issue_count": 1,
        "total_issue_count": 2,
    }


def test_required_facet_completeness_explicitly_marks_absence() -> None:
    assert _required_facet_completeness(()) == {
        "status": "NOT_PROVIDED",
        "covered_issue_count": 0,
        "total_issue_count": 0,
    }
