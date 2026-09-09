from __future__ import annotations

from dataclasses import replace

import pytest

from evidence_review.contracts.question_plan import (
    LegalAnchor,
    QuestionFact,
    QuestionIssue,
    QuestionPlan,
    SearchRequest,
)
from evidence_review.review_matter.scope import (
    build_explicit_review_scope,
    decode_review_scope,
    review_scope_document,
    review_scope_from_question_plan,
)


def _plan() -> QuestionPlan:
    return QuestionPlan(
        original_question="Is the entrance width sufficient?",
        facts=(QuestionFact("FACT-001", "The entrance is 900 mm wide.", "positive"),),
        assumptions=(),
        issues=(
            QuestionIssue(
                "ISSUE-001",
                "Is the entrance width sufficient?",
                (),
                ("rule",),
            ),
        ),
        legal_anchors=(LegalAnchor("Building Act Article 1", "planner"),),
        search_requests=(
            SearchRequest(
                "SEARCH-001",
                ("ISSUE-001",),
                "entrance width",
                "phrase",
                "planner",
                "rule",
            ),
        ),
    )


def test_equivalent_explicit_and_planner_scope_share_downstream_structure() -> None:
    plan = _plan()
    planner_scope = review_scope_from_question_plan(plan)
    explicit_scope = build_explicit_review_scope(
        question=plan.original_question,
        issues=plan.issues,
        facts=plan.facts,
        assumptions=plan.assumptions,
        legal_anchors=plan.legal_anchors,
        search_requests=plan.search_requests,
    )
    left = review_scope_document(planner_scope)
    right = review_scope_document(explicit_scope)
    for key in ("question", "issues", "facts", "assumptions", "legal_anchors", "search_requests"):
        assert left[key] == right[key]
    assert left["origin"] == "PLANNER"
    assert right["origin"] == "EXPLICIT_USER"


def test_review_scope_rejects_issue_cycles_and_empty_required_roles() -> None:
    plan = _plan()
    cyclic_issue = QuestionIssue("ISSUE-001", plan.issues[0].question, ("ISSUE-002",), ("rule",))
    second_issue = QuestionIssue("ISSUE-002", "Second", ("ISSUE-001",), ("rule",))
    with pytest.raises(ValueError, match="dependency cycle"):
        build_explicit_review_scope(
            question=plan.original_question,
            issues=(cyclic_issue, second_issue),
            facts=plan.facts,
            assumptions=plan.assumptions,
            legal_anchors=plan.legal_anchors,
            search_requests=plan.search_requests,
        )

    empty_role_issue = QuestionIssue("ISSUE-001", plan.issues[0].question, (), ())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="required_evidence_roles"):
        build_explicit_review_scope(
            question=plan.original_question,
            issues=(empty_role_issue,),
            facts=plan.facts,
            assumptions=plan.assumptions,
            legal_anchors=plan.legal_anchors,
            search_requests=plan.search_requests,
        )


def test_scope_round_trips_through_strict_document() -> None:
    scope = review_scope_from_question_plan(_plan())
    assert decode_review_scope(review_scope_document(scope)) == scope


def test_scope_public_document_rejects_forged_planner_lineage() -> None:
    scope = review_scope_from_question_plan(_plan())
    forged = replace(scope, question_plan_sha256="f" * 64)
    with pytest.raises(ValueError, match="question_plan_sha256 mismatch"):
        review_scope_document(forged)
