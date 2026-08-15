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
    """Bind a validated plan identity and canonical projection into a review request."""
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
    inputs["question_plan"] = {
        "issues": [
            {
                "id": issue.id,
                "question": issue.question,
                "depends_on": list(issue.depends_on),
            }
            for issue in plan.issues
        ],
        "facts": [
            {"id": item.id, "text": item.text, "polarity": item.polarity}
            for item in plan.facts
        ],
        "assumptions": [
            {"id": item.id, "text": item.text, "polarity": item.polarity}
            for item in plan.assumptions
        ],
        "legal_anchors": [
            {"text": item.text, "source": item.source} for item in plan.legal_anchors
        ],
    }
    bound["inputs"] = inputs
    return bound


def bind_retrieval_lineage_to_review_request(
    request: dict[str, object], bundle: dict[str, object]
) -> dict[str, object]:
    """Expose deterministic retrieval lineage to Track A through request inputs."""
    inputs_value = request.get("inputs")
    if not isinstance(inputs_value, dict) or not all(
        isinstance(key, str) for key in inputs_value
    ):
        raise ValueError("review request inputs must be an object")
    hits = bundle.get("hits")
    if not isinstance(hits, list):
        raise ValueError("evidence bundle hits must be an array")

    lineage: list[dict[str, object]] = []
    for index, hit_value in enumerate(hits):
        if not isinstance(hit_value, dict):
            raise ValueError(f"hits[{index}] must be an object")
        matches_value = hit_value.get("matches", [])
        if not isinstance(matches_value, list):
            raise ValueError(f"hits[{index}].matches must be an array")
        if not matches_value:
            continue
        evidence_id = hit_value.get("evidence_id")
        citation = hit_value.get("citation")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise ValueError(f"hits[{index}].evidence_id must be a non-empty string")
        if not isinstance(citation, dict):
            raise ValueError(f"hits[{index}].citation must be an object")
        citation_id = citation.get("citation_id")
        if not isinstance(citation_id, str) or not citation_id:
            raise ValueError(
                f"hits[{index}].citation.citation_id must be a non-empty string"
            )

        matches: list[dict[str, object]] = []
        for match_index, match_value in enumerate(matches_value):
            if not isinstance(match_value, dict):
                raise ValueError(
                    f"hits[{index}].matches[{match_index}] must be an object"
                )
            allowed = {"search_request_id", "issue_ids", "query_text", "origin"}
            if set(match_value) != allowed:
                raise ValueError(
                    f"hits[{index}].matches[{match_index}] has invalid fields"
                )
            search_request_id = match_value.get("search_request_id")
            issue_ids = match_value.get("issue_ids")
            query_text = match_value.get("query_text")
            origin = match_value.get("origin")
            if not isinstance(search_request_id, str) or not search_request_id:
                raise ValueError("retrieval match search_request_id must be non-empty")
            if (
                not isinstance(issue_ids, list)
                or not issue_ids
                or not all(isinstance(item, str) and item for item in issue_ids)
            ):
                raise ValueError("retrieval match issue_ids must be non-empty strings")
            if not isinstance(query_text, str) or not query_text:
                raise ValueError("retrieval match query_text must be non-empty")
            if origin not in {"primary", "approved_synonym", "user", "llm"}:
                raise ValueError("retrieval match origin is unsupported")
            matches.append(
                {
                    "search_request_id": search_request_id,
                    "issue_ids": sorted(set(issue_ids)),
                    "query_text": query_text,
                    "origin": origin,
                }
            )
        matches.sort(
            key=lambda item: (
                item["search_request_id"],
                item["issue_ids"],
                item["query_text"],
                item["origin"],
            )
        )
        lineage.append(
            {
                "evidence_id": evidence_id,
                "citation_id": citation_id,
                "matches": matches,
            }
        )

    bound = dict(request)
    inputs = dict(inputs_value)
    inputs["retrieval_lineage"] = sorted(
        lineage, key=lambda item: (item["evidence_id"], item["citation_id"])
    )
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
