import pytest

from evidence_review.contracts.question_plan import QuestionIssue, QuestionPlan, SearchRequest
from evidence_review.planned_review_question import prepare_planned_review_question


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


def test_planned_review_rejects_unbound_user_expansions_before_retrieval(tmp_path) -> None:
    with pytest.raises(ValueError, match="issue-bound"):
        prepare_planned_review_question(
            tmp_path,
            _plan(),
            user_expansions=("300m",),
        )
