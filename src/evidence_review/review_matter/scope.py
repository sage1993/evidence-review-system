"""Canonical, evidence-free control contract for formal review scope."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from evidence_review.contracts.formats import REVIEW_SCOPE_FORMAT
from evidence_review.contracts.question_plan import (
    LegalAnchor,
    QuestionFact,
    QuestionIssue,
    SearchRequest,
    decode_question_plan,
)
from evidence_review.question_planning import question_plan_sha256

REVIEW_SCOPE_VERSION = 1
ReviewScopeOrigin = Literal["PLANNER", "EXPLICIT_USER"]

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = {
    "format",
    "version",
    "question",
    "facts",
    "assumptions",
    "issues",
    "legal_anchors",
    "search_requests",
    "origin",
    "question_plan_sha256",
}


@dataclass(frozen=True, slots=True)
class ReviewScope:
    """Immutable control input; it deliberately carries no evidence or final status."""

    question: str
    facts: tuple[QuestionFact, ...]
    assumptions: tuple[QuestionFact, ...]
    issues: tuple[QuestionIssue, ...]
    legal_anchors: tuple[LegalAnchor, ...]
    search_requests: tuple[SearchRequest, ...]
    origin: ReviewScopeOrigin
    question_plan_sha256: str | None


def _expect_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError("review_scope must be an object")
    return cast(Mapping[str, object], value)


def _expect_version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("version must be an integer")
    if value != REVIEW_SCOPE_VERSION:
        raise ValueError("unsupported review scope version")
    return value


def _expect_origin(value: object) -> ReviewScopeOrigin:
    if value not in ("PLANNER", "EXPLICIT_USER"):
        raise ValueError("unsupported review scope origin")
    return value


def _expect_provenance(value: object, origin: ReviewScopeOrigin) -> str | None:
    if origin == "EXPLICIT_USER":
        if value is not None:
            raise ValueError("EXPLICIT_USER review scope must not have question plan provenance")
        return None
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(
            "PLANNER review scope requires a lowercase SHA-256 question plan provenance"
        )
    return value


def decode_review_scope(value: object) -> ReviewScope:
    """Decode a canonical scope while retaining QuestionPlan validation semantics."""
    payload = _expect_mapping(value)
    unknown = sorted(set(payload) - _FIELDS)
    missing = sorted(_FIELDS - set(payload))
    if unknown:
        raise ValueError("review_scope has unknown fields: " + ", ".join(unknown))
    if missing:
        raise ValueError("review_scope is missing fields: " + ", ".join(missing))
    if payload["format"] != REVIEW_SCOPE_FORMAT:
        raise ValueError("unsupported review scope format")
    _expect_version(payload["version"])
    origin = _expect_origin(payload["origin"])
    provenance_sha256 = _expect_provenance(payload["question_plan_sha256"], origin)
    question = payload["question"]
    if not isinstance(question, str):
        raise ValueError("question must be a string")
    if not question.strip():
        raise ValueError("question must not be empty")

    plan = decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": payload["question"],
            "facts": payload["facts"],
            "assumptions": payload["assumptions"],
            "issues": payload["issues"],
            "legal_anchors": payload["legal_anchors"],
            "search_requests": payload["search_requests"],
        },
        question,
    )
    if origin == "PLANNER" and provenance_sha256 != question_plan_sha256(plan):
        raise ValueError("question_plan_sha256 does not match canonical QuestionPlan")
    return ReviewScope(
        question=plan.original_question,
        facts=plan.facts,
        assumptions=plan.assumptions,
        issues=plan.issues,
        legal_anchors=plan.legal_anchors,
        search_requests=plan.search_requests,
        origin=origin,
        question_plan_sha256=provenance_sha256,
    )


def review_scope_document(scope: ReviewScope) -> dict[str, object]:
    """Encode a scope into its deterministic JSON-compatible document."""
    return {
        "format": REVIEW_SCOPE_FORMAT,
        "version": REVIEW_SCOPE_VERSION,
        "question": scope.question,
        "facts": [
            {"id": item.id, "text": item.text, "polarity": item.polarity} for item in scope.facts
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
        "question_plan_sha256": scope.question_plan_sha256,
    }
