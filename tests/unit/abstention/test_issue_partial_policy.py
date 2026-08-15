from evidence_review.abstention.issue_policy import issue_results_require_global_abstain
from evidence_review.contracts.review import IssueResult


def _issue(issue_id: str, status: str) -> IssueResult:
    return IssueResult(issue_id=issue_id, status=status)


def test_partial_issue_coverage_does_not_force_global_abstain() -> None:
    assert not issue_results_require_global_abstain(
        (
            _issue("I1", "RESOLVED"),
            _issue("I2", "UNRESOLVED"),
        )
    )


def test_conditional_issue_counts_as_supported_for_global_finalization() -> None:
    assert not issue_results_require_global_abstain(
        (
            _issue("I1", "CONDITIONAL"),
            _issue("I2", "SOURCE_MISSING"),
        )
    )


def test_all_unresolved_issue_coverage_requires_global_abstain() -> None:
    assert issue_results_require_global_abstain(
        (
            _issue("I1", "UNRESOLVED"),
            _issue("I2", "SOURCE_MISSING"),
        )
    )


def test_empty_issue_results_do_not_override_legacy_missing_input_policy() -> None:
    assert not issue_results_require_global_abstain(())
