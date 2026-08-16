from evidence_review.abstention.issue_policy import issue_results_require_global_abstain
from evidence_review.contracts.review import IssueResult


def test_deterministic_missing_input_remains_global_hard_gate_with_partial_coverage() -> None:
    issue_results = (
        IssueResult(issue_id="I1", status="RESOLVED"),
        IssueResult(issue_id="I2", status="SOURCE_MISSING"),
    )

    assert issue_results_require_global_abstain(
        issue_results,
        deterministic_missing_inputs=True,
    )


def test_issue_local_gap_does_not_force_global_abstain_without_deterministic_missing_input(
) -> None:
    issue_results = (
        IssueResult(issue_id="I1", status="RESOLVED"),
        IssueResult(issue_id="I2", status="SOURCE_MISSING"),
    )

    assert not issue_results_require_global_abstain(
        issue_results,
        deterministic_missing_inputs=False,
    )
