"""External AI question-planner handoff contract."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping

from evidence_review.contracts.question_plan import (
    QUESTION_PLAN_FORMAT,
    QUESTION_PLAN_VERSION,
    QuestionPlan,
    decode_question_plan,
)

QUESTION_PLANNER_BUNDLE_FORMAT = "evidence-review/question-planner-bundle"
QUESTION_PLANNER_BUNDLE_VERSION = 1


def _normalize_question(value: str) -> str:
    normalized = unicodedata.normalize("NFC", " ".join(value.split()))
    if not normalized:
        raise ValueError("question must not be empty")
    return normalized


def build_question_planner_bundle(question: str) -> dict[str, object]:
    """Build the evidence-free artifact handed to an external question planner."""
    return {
        "format": QUESTION_PLANNER_BUNDLE_FORMAT,
        "version": QUESTION_PLANNER_BUNDLE_VERSION,
        "original_question": _normalize_question(question),
        "question_plan_format": QUESTION_PLAN_FORMAT,
        "question_plan_version": QUESTION_PLAN_VERSION,
    }


def validate_question_planner_output(value: object, question: str) -> QuestionPlan:
    """Fail closed on current external planner output before retrieval starts."""
    if not isinstance(value, Mapping):
        raise ValueError("question planner output must be an object")
    if value.get("version") != QUESTION_PLAN_VERSION:
        raise ValueError(
            f"question planner output must use question plan version {QUESTION_PLAN_VERSION}"
        )
    return decode_question_plan(value, question)
