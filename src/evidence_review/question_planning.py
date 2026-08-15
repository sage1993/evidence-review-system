"""Deterministic utilities for validated question plans."""

from __future__ import annotations

from evidence_review.canonical_json import sha256_json
from evidence_review.contracts.question_plan import QuestionPlan, question_plan_document


def question_plan_sha256(plan: QuestionPlan) -> str:
    """Hash the canonical validated plan used as the deterministic replay boundary."""
    return sha256_json(question_plan_document(plan))
