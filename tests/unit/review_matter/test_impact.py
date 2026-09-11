from evidence_review.review_matter.impact import evaluate_source_change_impact


def test_changed_source_hash_invalidates_every_dependent_issue() -> None:
    report = evaluate_source_change_impact(
        before={"source_id": "SRC-1", "sha256": "a" * 64},
        after={"source_id": "SRC-1", "sha256": "b" * 64},
        dependencies={"ISSUE-1": {"SRC-1"}, "ISSUE-2": {"SRC-2"}},
    )

    assert report.stale_issue_ids == ("ISSUE-1",)
    assert "ISSUE-1" not in report.retained_issue_ids


def test_same_exact_source_identity_retains_explicitly_modelled_dependents() -> None:
    report = evaluate_source_change_impact(
        before={"source_id": "SRC-1", "revision_id": "REV-1", "sha256": "a" * 64},
        after={"source_id": "SRC-1", "revision_id": "REV-1", "sha256": "a" * 64},
        dependencies={"ISSUE-2": {"SRC-2"}, "ISSUE-1": {"SRC-1"}},
    )

    assert report.status == "UNCHANGED"
    assert report.stale_issue_ids == ()
    assert report.retained_issue_ids == ("ISSUE-1", "ISSUE-2")


def test_changed_revision_identity_marks_each_direct_dependent_issue_stale() -> None:
    report = evaluate_source_change_impact(
        before={"source_id": "SRC-1", "revision_id": "REV-1", "sha256": "a" * 64},
        after={"source_id": "SRC-1", "revision_id": "REV-2", "sha256": "a" * 64},
        dependencies={"ISSUE-2": {"SRC-1"}, "ISSUE-1": {"SRC-1"}},
    )

    assert report.status == "STALE"
    assert report.stale_issue_ids == ("ISSUE-1", "ISSUE-2")
    assert report.retained_issue_ids == ()


def test_malformed_dependency_record_requires_recheck_instead_of_retention() -> None:
    report = evaluate_source_change_impact(
        before={"source_id": "SRC-1", "sha256": "a" * 64},
        after={"source_id": "SRC-1", "sha256": "b" * 64},
        dependencies={"ISSUE-1": {"SRC-1", None}},  # type: ignore[dict-item]
    )

    assert report.status == "RECHECK_REQUIRED"
    assert report.stale_issue_ids == ("ISSUE-1",)
    assert report.retained_issue_ids == ()
