"""Deterministic utilities for validated question plans."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from evidence_review.canonical_json import dump_bytes, sha256_json
from evidence_review.contracts.question_plan import QuestionPlan, question_plan_document
from evidence_review.llm_layer.question_planner import build_question_planner_bundle


@dataclass(frozen=True, slots=True)
class QuestionPlannerHandoff:
    """Immutable file paths for one external question-planner handoff."""

    planning_directory: Path
    bundle_path: Path
    instructions_path: Path
    expected_output_path: Path


def _write_or_identical(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise FileExistsError(f"existing planner artifact differs: {path.name}") from None


def prepare_question_planner_handoff(workspace: Path, question: str) -> QuestionPlannerHandoff:
    """Write a deterministic evidence-free handoff for an external AI planner."""
    bundle = build_question_planner_bundle(question)
    plan_id = f"PLAN-{sha256_json(bundle)[:20].upper()}"
    directory = workspace / "question-planning" / plan_id
    bundle_path = directory / "question-planner-bundle.json"
    instructions_path = directory / "QUESTION_PLANNER_INSTRUCTIONS.md"
    expected_output_path = directory / "question-plan-output.json"
    template = (
        Path(__file__).with_name("llm_layer") / "templates" / "question-planner.md"
    ).read_bytes()
    _write_or_identical(bundle_path, dump_bytes(bundle))
    _write_or_identical(instructions_path, template)
    return QuestionPlannerHandoff(
        planning_directory=directory,
        bundle_path=bundle_path,
        instructions_path=instructions_path,
        expected_output_path=expected_output_path,
    )


def question_plan_sha256(plan: QuestionPlan) -> str:
    """Hash the canonical validated plan used as the deterministic replay boundary."""
    return sha256_json(question_plan_document(plan))


def bind_question_plan_to_review_request(
    request: dict[str, object], plan: QuestionPlan
) -> dict[str, object]:
    """Bind a validated plan identity and issue structure into an immutable review request."""
    question = request.get("question")
    if question != plan.original_question:
        raise ValueError("review request question does not match question plan")
    inputs_value = request.get("inputs")
    if not isinstance(inputs_value, dict) or not all(
        isinstance(key, str) for key in inputs_value
    ):
        raise ValueError("review request inputs must be an object")
    bound = dict(request)
    inputs = dict(inputs_value)
    inputs["question_plan_sha256"] = question_plan_sha256(plan)
    inputs["question_issues"] = [
        {
            "id": issue.id,
            "question": issue.question,
            "depends_on": list(issue.depends_on),
        }
        for issue in plan.issues
    ]
    inputs["question_facts"] = [
        {"id": item.id, "text": item.text, "polarity": item.polarity}
        for item in plan.facts
    ]
    inputs["question_assumptions"] = [
        {"id": item.id, "text": item.text, "polarity": item.polarity}
        for item in plan.assumptions
    ]
    bound["inputs"] = inputs
    return bound


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
