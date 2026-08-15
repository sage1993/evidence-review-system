"""Deterministic utilities for validated question plans."""

from __future__ import annotations

from collections.abc import Sequence

from evidence_review.canonical_json import sha256_json
from evidence_review.contracts.question_plan import QuestionPlan, question_plan_document


def question_plan_sha256(plan: QuestionPlan) -> str:
    """Hash the canonical validated plan used as the deterministic replay boundary."""
    return sha256_json(question_plan_document(plan))


def query_request_from_plan(
    plan: QuestionPlan, *, user_expansions: Sequence[str] = ()
) -> dict[str, object]:
    """Convert a validated plan to the existing bounded retrieval request contract."""
    expansions: list[dict[str, object]] = [
        {
            "text": request.text,
            "origin": "llm",
            "search_request_ids": [request.id],
            "issue_ids": list(request.issue_ids),
        }
        for request in plan.search_requests
    ]
    for index, term in enumerate(user_expansions):
        if not isinstance(term, str) or not term.strip():
            raise ValueError(f"user_expansions[{index}] must be a non-empty string")
        expansions.append({"text": term, "origin": "user"})
    return {
        "question": plan.original_question,
        "expansions": expansions,
        "synonym_manifest": {},
        "filters": {},
        "clause_ids": [],
        "seed_ids": [],
        "graph_depth": 1,
        "limit": 20,
    }
