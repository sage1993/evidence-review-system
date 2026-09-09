"""Canonical downstream ReviewScope control input."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from evidence_review.contracts.formats import REVIEW_SCOPE_FORMAT
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

ReviewScopeOrigin = Literal["PLANNER", "EXPLICIT_USER"]
REVIEW_SCOPE_VERSION = 1


@dataclass(frozen=True, slots=True)
class ReviewScope:
    """Validated control input independent of how the scope was produced."""

    question: str
    facts: tuple[QuestionFact, ...]
    assumptions: tuple[QuestionFact, ...]
    issues: tuple[QuestionIssue, ...]
    legal_anchors: tuple[LegalAnchor, ...]
    search_requests: tuple[SearchRequest, ...]
    origin: ReviewScopeOrigin
    question_plan_sha256: str | None = None


def _from_plan(
    plan: QuestionPlan,
    *,
    origin: ReviewScopeOrigin,
    plan_hash: str | None,
) -> ReviewScope:
    # Re-decode the canonical QuestionPlan document to keep constructors from
    # becoming an unvalidated alternate path into retrieval.
    validated = decode_question_plan(question_plan_document(plan), plan.original_question)
    return ReviewScope(
        question=validated.original_question,
        facts=validated.facts,
        assumptions=validated.assumptions,
        issues=validated.issues,
        legal_anchors=validated.legal_anchors,
        search_requests=validated.search_requests,
        origin=origin,
        question_plan_sha256=plan_hash,
    )


def review_scope_from_question_plan(plan: QuestionPlan) -> ReviewScope:
    """Adapt one validated planner result into the canonical scope contract."""
    if not isinstance(plan, QuestionPlan):
        raise ValueError("plan must be a validated QuestionPlan")
    return _from_plan(plan, origin="PLANNER", plan_hash=question_plan_sha256(plan))


def question_plan_from_review_scope(scope: ReviewScope) -> QuestionPlan:
    """Return the validated legacy-shaped plan consumed by existing retrieval code."""
    scope = _validated_scope(scope)
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": scope.question,
            "facts": [
                {"id": item.id, "text": item.text, "polarity": item.polarity}
                for item in scope.facts
            ],
            "assumptions": [
                {"id": item.id, "text": item.text, "polarity": item.polarity}
                for item in scope.assumptions
            ],
            "issues": [
                {
                    "id": item.id,
                    "question": item.question,
                    "depends_on": list(item.depends_on),
                    "required_evidence_roles": list(item.required_evidence_roles),
                }
                for item in scope.issues
            ],
            "legal_anchors": [
                {"text": item.text, "source": item.source}
                for item in scope.legal_anchors
            ],
            "search_requests": [
                {
                    "id": item.id,
                    "issue_ids": list(item.issue_ids),
                    "text": item.text,
                    "kind": item.kind,
                    "source": item.source,
                    "role": item.role,
                }
                for item in scope.search_requests
            ],
        },
        scope.question,
    )


def build_explicit_review_scope(
    *,
    question: str,
    issues: tuple[QuestionIssue, ...] | list[QuestionIssue],
    facts: tuple[QuestionFact, ...] | list[QuestionFact] = (),
    assumptions: tuple[QuestionFact, ...] | list[QuestionFact] = (),
    legal_anchors: tuple[LegalAnchor, ...] | list[LegalAnchor] = (),
    search_requests: tuple[SearchRequest, ...] | list[SearchRequest],
) -> ReviewScope:
    """Build the same validated scope shape from explicit user inputs."""
    plan = QuestionPlan(
        original_question=question,
        facts=tuple(facts),
        assumptions=tuple(assumptions),
        issues=tuple(issues),
        legal_anchors=tuple(legal_anchors),
        search_requests=tuple(search_requests),
    )
    return _from_plan(plan, origin="EXPLICIT_USER", plan_hash=None)


def _scope_document(scope: ReviewScope) -> dict[str, object]:
    """Serialize one already validated scope without recursively decoding it."""
    if not isinstance(scope, ReviewScope):
        raise ValueError("scope must be a ReviewScope")
    document: dict[str, object] = {
        "format": REVIEW_SCOPE_FORMAT,
        "version": REVIEW_SCOPE_VERSION,
        "question": scope.question,
        "facts": [
            {"id": item.id, "text": item.text, "polarity": item.polarity}
            for item in scope.facts
        ],
        "assumptions": [
            {"id": item.id, "text": item.text, "polarity": item.polarity}
            for item in scope.assumptions
        ],
        "issues": [
            {
                "id": item.id,
                "question": item.question,
                "depends_on": list(item.depends_on),
                "required_evidence_roles": list(item.required_evidence_roles),
            }
            for item in scope.issues
        ],
        "legal_anchors": [
            {"text": item.text, "source": item.source} for item in scope.legal_anchors
        ],
        "search_requests": [
            {
                "id": item.id,
                "issue_ids": list(item.issue_ids),
                "text": item.text,
                "kind": item.kind,
                "source": item.source,
                "role": item.role,
            }
            for item in scope.search_requests
        ],
        "origin": scope.origin,
    }
    if scope.question_plan_sha256 is not None:
        document["question_plan_sha256"] = scope.question_plan_sha256
    return document


def _validated_scope(scope: ReviewScope) -> ReviewScope:
    if not isinstance(scope, ReviewScope):
        raise ValueError("scope must be a ReviewScope")
    return decode_review_scope(_scope_document(scope))


def review_scope_document(scope: ReviewScope) -> dict[str, object]:
    """Return the strict canonical JSON-compatible scope document."""
    return _scope_document(_validated_scope(scope))


def decode_review_scope(value: object) -> ReviewScope:
    """Decode a strict ReviewScope and reject evidence/final-status fields."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("review_scope must be an object")
    required = {
        "format",
        "version",
        "question",
        "facts",
        "assumptions",
        "issues",
        "legal_anchors",
        "search_requests",
        "origin",
    }
    allowed = required | {"question_plan_sha256"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"review_scope has unknown fields: {', '.join(unknown)}")
    if not required <= set(value):
        missing = sorted(required - set(value))
        raise ValueError(f"review_scope is missing required fields: {', '.join(missing)}")
    if value["format"] != REVIEW_SCOPE_FORMAT or value["version"] != REVIEW_SCOPE_VERSION:
        raise ValueError("unsupported review_scope format or version")
    origin = value["origin"]
    if origin not in {"PLANNER", "EXPLICIT_USER"}:
        raise ValueError("unsupported review_scope origin")
    plan_document = {
        "format": "evidence-review/question-plan",
        "version": 2,
        "original_question": value["question"],
        "facts": value["facts"],
        "assumptions": value["assumptions"],
        "issues": value["issues"],
        "legal_anchors": value["legal_anchors"],
        "search_requests": value["search_requests"],
    }
    plan = decode_question_plan(plan_document, value["question"])
    plan_hash = value.get("question_plan_sha256")
    if origin == "PLANNER":
        if not isinstance(plan_hash, str) or len(plan_hash) != 64:
            raise ValueError("planner ReviewScope requires question_plan_sha256")
        if plan_hash != question_plan_sha256(plan):
            raise ValueError("planner ReviewScope question_plan_sha256 mismatch")
    elif "question_plan_sha256" in value:
        raise ValueError("explicit ReviewScope must not contain planner lineage")
    return _from_plan(plan, origin=origin, plan_hash=plan_hash)
