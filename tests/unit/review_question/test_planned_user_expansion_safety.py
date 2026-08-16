from evidence_review.contracts.question_plan import QuestionIssue, QuestionPlan, SearchRequest
from evidence_review.user_expansions import plan_with_user_expansions


def _plan() -> QuestionPlan:
    return QuestionPlan(
        original_question="역세권 기준을 검토해줘",
        facts=(),
        assumptions=(),
        issues=(
            QuestionIssue(
                id="SITE_DISTANCE",
                question="역세권 거리 기준은 무엇인가?",
                depends_on=(),
                required_evidence_roles=("rule",),
            ),
        ),
        legal_anchors=(),
        search_requests=(
            SearchRequest(
                id="SEARCH-DISTANCE",
                issue_ids=("SITE_DISTANCE",),
                text="역세권 승강장 경계 거리 기준",
                kind="concept_relation",
                source="planner",
                role="rule",
            ),
        ),
    )


def test_user_expansion_is_bound_to_primary_issue_and_role() -> None:
    effective = plan_with_user_expansions(_plan(), ("  별표   2  ",))

    expansion = effective.search_requests[0]
    assert expansion.text == "별표 2"
    assert expansion.source == "user"
    assert expansion.issue_ids == ("SITE_DISTANCE",)
    assert expansion.role == "rule"
    assert effective.search_requests[1].id == "SEARCH-DISTANCE"
