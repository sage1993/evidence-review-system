from evidence_review.abstention.issue_policy import reconcile_issue_results
from evidence_review.contracts.review import Claim, IssueResult


def _issue(status: str = "RESOLVED", issue_id: str = "I1") -> IssueResult:
    return IssueResult(
        issue_id=issue_id,
        status=status,  # type: ignore[arg-type]
        evidence_ids=("EV-1",),
        covered_roles=("rule",),
    )


def _claim(issue_id: str = "I1") -> Claim:
    return Claim(
        claim_id="CL-1",
        text="supported",
        citation_ids=("CIT-1",),
        issue_ids=(issue_id,),
    )


def test_resolved_issue_without_track_a_claim_becomes_unresolved() -> None:
    result = reconcile_issue_results((_issue(),), claims=(), track_a_missing_inputs=())

    assert result[0].status == "UNRESOLVED"


def test_issue_scoped_missing_input_prevents_resolved_status() -> None:
    result = reconcile_issue_results(
        (_issue(),),
        claims=(_claim(),),
        track_a_missing_inputs=("I1: 구체적인 결정 절차와 결정권자 근거가 필요함",),
    )

    assert result[0].status == "CONDITIONAL"


def test_missing_input_and_zero_claims_becomes_source_missing() -> None:
    result = reconcile_issue_results(
        (_issue(issue_id="I3"),),
        claims=(),
        track_a_missing_inputs=("I3: 최소 사업면적 기준이 없음",),
    )

    assert result[0].status == "SOURCE_MISSING"


def test_supported_issue_remains_resolved() -> None:
    result = reconcile_issue_results(
        (_issue(),), claims=(_claim(),), track_a_missing_inputs=()
    )

    assert result[0].status == "RESOLVED"


def test_existing_unresolved_status_is_preserved() -> None:
    result = reconcile_issue_results(
        (_issue(status="SOURCE_MISSING"),),
        claims=(_claim(),),
        track_a_missing_inputs=(),
    )

    assert result[0].status == "SOURCE_MISSING"
