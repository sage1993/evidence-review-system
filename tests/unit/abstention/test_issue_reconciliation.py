import pytest

from evidence_review.abstention.issue_policy import (
    has_partial_issue_resolution,
    reconcile_issue_results,
)
from evidence_review.contracts.review import Claim, ClaimAudit, IssueResult


def _issue(status: str = "RESOLVED", issue_id: str = "I1") -> IssueResult:
    return IssueResult(
        issue_id=issue_id,
        status=status,  # type: ignore[arg-type]
        evidence_ids=("EV-1",),
        covered_roles=("rule",),
    )


def _claim(issue_id: str = "I1", claim_id: str = "CL-1") -> Claim:
    return Claim(
        claim_id=claim_id,
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


def test_mixed_track_b_audits_downgrade_only_nonaccepted_claim_issue() -> None:
    reconciled = reconcile_issue_results(
        (_issue(issue_id="I1"), _issue(issue_id="I2")),
        claims=(_claim("I1", "CL-I1"), _claim("I2", "CL-I2")),
        track_a_missing_inputs=(),
        claim_audits=(
            ClaimAudit(claim_id="CL-I1", disposition="INCOMPLETE"),
            ClaimAudit(claim_id="CL-I2", disposition="ACCEPT"),
        ),
    )

    assert [item.status for item in reconciled] == ["UNRESOLVED", "RESOLVED"]
    assert has_partial_issue_resolution(reconciled) is True


def test_duplicate_claim_audits_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate claim audit"):
        reconcile_issue_results(
            (_issue(),),
            claims=(_claim(),),
            track_a_missing_inputs=(),
            claim_audits=(
                ClaimAudit(claim_id="CL-1", disposition="ACCEPT"),
                ClaimAudit(claim_id="CL-1", disposition="INCOMPLETE"),
            ),
        )


def test_unknown_claim_audit_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown claim audit"):
        reconcile_issue_results(
            (_issue(),),
            claims=(_claim(),),
            track_a_missing_inputs=(),
            claim_audits=(ClaimAudit(claim_id="CL-404", disposition="INCOMPLETE"),),
        )
