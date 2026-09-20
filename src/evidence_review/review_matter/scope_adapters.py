"""Validated adapters into the canonical ReviewScope control contract."""

from __future__ import annotations

from evidence_review.contracts.question_plan import (
    LegalAnchor,
    QuestionFact,
    QuestionIssue,
    QuestionPlan,
    SearchRequest,
    decode_question_plan,
    question_plan_document,
)
from evidence_review.question_planning import question_plan_sha256
from evidence_review.review_matter.scope import (
    ReviewScope,
    decode_review_scope,
    review_scope_document,
)


def _validated_question_plan(plan: object) -> QuestionPlan:
    if not isinstance(plan, QuestionPlan):
        raise ValueError("question plan must be a validated QuestionPlan")
    try:
        return decode_question_plan(question_plan_document(plan), plan.original_question)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("question plan is not valid") from error


def _scope_from_plan(
    plan: QuestionPlan,
    *,
    origin: str,
    question_plan_sha256_value: str | None,
) -> ReviewScope:
    document = question_plan_document(plan)
    document.update(
        {
            "format": "evidence-review/review-scope",
            "version": 2,
            "question": document.pop("original_question"),
            "origin": origin,
            "question_plan_sha256": question_plan_sha256_value,
            "question_plan_version": plan.version,
        }
    )
    return decode_review_scope(document)


def review_scope_from_question_plan(plan: QuestionPlan) -> ReviewScope:
    """Revalidate planner control input and retain its exact lineage hash."""
    canonical_plan = _validated_question_plan(plan)
    return _scope_from_plan(
        canonical_plan,
        origin="PLANNER",
        question_plan_sha256_value=question_plan_sha256(plan),
    )


def review_scope_from_explicit_input(
    *,
    question: str,
    issues: tuple[QuestionIssue, ...] | list[QuestionIssue],
    facts: tuple[QuestionFact, ...] | list[QuestionFact] = (),
    assumptions: tuple[QuestionFact, ...] | list[QuestionFact] = (),
    legal_anchors: tuple[LegalAnchor, ...] | list[LegalAnchor] = (),
    search_requests: tuple[SearchRequest, ...] | list[SearchRequest],
) -> ReviewScope:
    """Validate explicit reviewer control input without planner provenance."""
    values = (facts, assumptions, issues, legal_anchors, search_requests)
    if not all(isinstance(value, (tuple, list)) for value in values):
        raise ValueError("explicit review scope collections must be tuples or lists")
    plan = _validated_question_plan(
        QuestionPlan(
            original_question=question,
            facts=tuple(facts),
            assumptions=tuple(assumptions),
            issues=tuple(issues),
            legal_anchors=tuple(legal_anchors),
            search_requests=tuple(search_requests),
            version=(3 if all(issue.required_facet_ids for issue in issues) else 2),
        )
    )
    return _scope_from_plan(
        plan,
        origin="EXPLICIT_USER",
        question_plan_sha256_value=None,
    )


def normalize_review_scope(value: QuestionPlan | ReviewScope) -> ReviewScope:
    """Normalize a legacy QuestionPlan or canonical scope at an input boundary."""
    if isinstance(value, QuestionPlan):
        return review_scope_from_question_plan(value)
    if not isinstance(value, ReviewScope):
        raise ValueError("review scope must be a QuestionPlan or ReviewScope")
    try:
        return decode_review_scope(review_scope_document(value))
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("review scope is not valid") from error


def question_plan_from_review_scope(scope: ReviewScope) -> QuestionPlan:
    """Project a validated scope into the legacy planner control contract."""
    canonical_scope = normalize_review_scope(scope)
    document = review_scope_document(canonical_scope)
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": canonical_scope.question_plan_version,
            "original_question": document["question"],
            "facts": document["facts"],
            "assumptions": document["assumptions"],
            "issues": document["issues"],
            "legal_anchors": document["legal_anchors"],
            "search_requests": document["search_requests"],
        },
        canonical_scope.question,
    )


__all__ = [
    "question_plan_from_review_scope",
    "normalize_review_scope",
    "review_scope_from_explicit_input",
    "review_scope_from_question_plan",
]
