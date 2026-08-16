from dataclasses import dataclass
from decimal import Decimal

from evidence_review.contracts.question_plan import QuestionIssue, QuestionPlan
from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit
from evidence_review.retrieval.coverage import evaluate_issue_coverage
from evidence_review.retrieval.graph import MissingReference
from evidence_review.retrieval.issue_bundle import (
    IssueCandidateMatch,
    IssueClauseCandidate,
    IssueRetrievalBundle,
)
from evidence_review.retrieval.models import ChannelScore


@dataclass(frozen=True)
class _Evidence:
    evidence_id: str


def _plan() -> QuestionPlan:
    return QuestionPlan(
        original_question="복합 검토",
        facts=(),
        assumptions=(),
        issues=(
            QuestionIssue(
                id="I1",
                question="기준과 사실을 검토",
                depends_on=(),
                required_evidence_roles=("supporting_fact", "rule"),
            ),
            QuestionIssue(
                id="I2",
                question="규칙을 검토",
                depends_on=(),
                required_evidence_roles=("rule",),
            ),
        ),
        legal_anchors=(),
        search_requests=(),
    )


def _candidate(issue_id: str, role: str, *, with_evidence: bool) -> IssueClauseCandidate:
    clause = ClauseRetrievalHit(
        clause_id=f"CL-{issue_id}-{role}",
        document_id="DOC",
        revision_id="REV",
        title="기준",
        text="기준 본문",
        channel_scores=(ChannelScore("test", Decimal("1")),),
    )
    return IssueClauseCandidate(
        clause=clause,
        matches=(
            IssueCandidateMatch(
                search_request_id=f"SR-{issue_id}-{role}",
                issue_id=issue_id,
                role=role,
                query_text="기준",
                retrieval_query="기준",
                fallback_stage="PHRASE",
            ),
        ),
        evidence=(_Evidence(f"E-{issue_id}-{role}"),) if with_evidence else (),
    )


def _bundle(*candidates: IssueClauseCandidate) -> IssueRetrievalBundle:
    return IssueRetrievalBundle(
        candidates=tuple(candidates),
        selected_evidence=(),
        budget_drops=(),
    )


def test_resolved_requires_every_required_role_to_have_citation_grade_evidence() -> None:
    support = evaluate_issue_coverage(
        _plan(),
        _bundle(
            _candidate("I1", "supporting_fact", with_evidence=True),
            _candidate("I1", "rule", with_evidence=True),
        ),
    )

    i1 = support.by_issue_id("I1")
    assert i1.status == "RESOLVED"
    assert i1.covered_roles == ("rule", "supporting_fact")
    assert i1.missing_roles == ()
    assert i1.gap_codes == ()


def test_semantic_clause_without_citation_materialization_is_parse_gap() -> None:
    support = evaluate_issue_coverage(
        _plan(),
        _bundle(_candidate("I2", "rule", with_evidence=False)),
    )

    i2 = support.by_issue_id("I2")
    assert i2.status == "UNRESOLVED"
    assert i2.missing_roles == ("rule",)
    assert i2.gap_codes == ("PARSE_GAP",)


def test_no_candidate_is_retrieval_miss() -> None:
    i2 = evaluate_issue_coverage(_plan(), _bundle()).by_issue_id("I2")
    assert i2.status == "UNRESOLVED"
    assert i2.gap_codes == ("RETRIEVAL_MISS",)


def test_reference_target_missing_is_source_missing_not_generic_retrieval_miss() -> None:
    missing = MissingReference(
        source_id="E-SOURCE",
        target_id="E-MISSING",
        relation_type="cited_clause",
        depth=1,
        reason_code="REFERENCE_TARGET_MISSING",
    )
    i2 = evaluate_issue_coverage(
        _plan(),
        _bundle(_candidate("I2", "rule", with_evidence=True)),
        reference_missing_by_issue={"I2": (missing,)},
    ).by_issue_id("I2")

    assert i2.status == "SOURCE_MISSING"
    assert i2.gap_codes == ("REFERENCE_TARGET_MISSING",)


def test_source_not_ingested_is_distinct_from_retrieval_miss() -> None:
    i2 = evaluate_issue_coverage(
        _plan(),
        _bundle(),
        source_missing_issue_ids=("I2",),
    ).by_issue_id("I2")

    assert i2.status == "SOURCE_MISSING"
    assert i2.gap_codes == ("SOURCE_NOT_INGESTED",)


def test_conflict_and_ambiguity_take_precedence_over_retrieval_status() -> None:
    conflict = evaluate_issue_coverage(
        _plan(),
        _bundle(_candidate("I2", "rule", with_evidence=True)),
        conflicting_issue_ids=("I2",),
    ).by_issue_id("I2")
    ambiguous = evaluate_issue_coverage(
        _plan(),
        _bundle(_candidate("I2", "rule", with_evidence=True)),
        ambiguous_issue_ids=("I2",),
    ).by_issue_id("I2")

    assert conflict.status == "CONFLICT"
    assert conflict.gap_codes == ("CONFLICTING_RULES",)
    assert ambiguous.status == "UNRESOLVED"
    assert ambiguous.gap_codes == ("AMBIGUOUS_RULE",)


def test_conditional_is_only_used_when_required_evidence_is_complete() -> None:
    resolved = evaluate_issue_coverage(
        _plan(),
        _bundle(_candidate("I2", "rule", with_evidence=True)),
        conditional_issue_ids=("I2",),
    ).by_issue_id("I2")
    unresolved = evaluate_issue_coverage(
        _plan(),
        _bundle(),
        conditional_issue_ids=("I2",),
    ).by_issue_id("I2")

    assert resolved.status == "CONDITIONAL"
    assert unresolved.status == "UNRESOLVED"
