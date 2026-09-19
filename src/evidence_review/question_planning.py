"""Deterministic utilities for validated question plans."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from evidence_review.canonical_json import dump_bytes, sha256_json
from evidence_review.contracts.question_plan import QuestionPlan, question_plan_document
from evidence_review.llm_layer.question_planner import build_question_planner_bundle
from evidence_review.retrieval.issue_bundle import IssueClauseCandidate, IssueRetrievalBundle
from evidence_review.retrieval.korean_variants import (
    derive_korean_compound_variants,
    derive_korean_query_variants,
)
from evidence_review.retrieval.models import RetrievalHit


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


def _write_bundle_or_semantically_identical(
    path: Path, bundle: dict[str, object]
) -> None:
    """Keep raw wording while treating whitespace-only rewrites as one handoff."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = dump_bytes(bundle)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise FileExistsError(
                f"existing planner artifact differs: {path.name}"
            ) from None
        if not isinstance(existing, dict):
            raise FileExistsError(
                f"existing planner artifact differs: {path.name}"
            ) from None
        existing_identity = dict(existing)
        bundle_identity = dict(bundle)
        existing_identity["raw_user_question"] = existing_identity.get(
            "normalized_question"
        )
        bundle_identity["raw_user_question"] = bundle_identity.get(
            "normalized_question"
        )
        if existing_identity != bundle_identity:
            raise FileExistsError(
                f"existing planner artifact differs: {path.name}"
            ) from None


def prepare_question_planner_handoff(workspace: Path, question: str) -> QuestionPlannerHandoff:
    """Write a deterministic evidence-free handoff for an external AI planner."""
    bundle = build_question_planner_bundle(question)
    plan_identity = dict(bundle)
    plan_identity["raw_user_question"] = plan_identity["normalized_question"]
    plan_id = f"PLAN-{sha256_json(plan_identity)[:20].upper()}"
    directory = workspace / "question-planning" / plan_id
    bundle_path = directory / "question-planner-bundle.json"
    instructions_path = directory / "QUESTION_PLANNER_INSTRUCTIONS.md"
    expected_output_path = directory / "question-plan-output.json"
    template = (
        Path(__file__).with_name("llm_layer") / "templates" / "question-planner.md"
    ).read_bytes()
    _write_bundle_or_semantically_identical(bundle_path, bundle)
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
                "required_evidence_roles": list(issue.required_evidence_roles),
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
        "search_requests": [
            {
                "id": item.id,
                "issue_ids": list(item.issue_ids),
                "text": item.text,
                "kind": item.kind,
                "source": item.source,
                "role": item.role,
            }
            for item in plan.search_requests
        ],
    }
    if (
        plan.raw_user_question is not None
        or plan.normalized_question is not None
        or plan.document_context
        or plan.planner_inference
    ):
        inputs["question_provenance"] = {
            "raw_user_question": plan.raw_user_question or plan.original_question,
            "normalized_question": plan.normalized_question or plan.original_question,
            "document_context": [
                {"text": item.text, "source": item.source}
                for item in plan.document_context
            ],
            "planner_inference": [
                {"text": item.text, "source": item.source}
                for item in plan.planner_inference
            ],
        }
    bound["inputs"] = inputs
    return bound


def _citation_document(hit: RetrievalHit) -> dict[str, object]:
    citation = hit.citation()
    return {
        "citation_id": citation.citation_id,
        "document_id": citation.document_id,
        "revision_id": citation.revision_id,
        "page_number": citation.page_number,
        "evidence_id": citation.evidence_id,
        "bbox": [
            citation.bbox.left,
            citation.bbox.bottom,
            citation.bbox.right,
            citation.bbox.top,
        ],
        "source_hash": citation.source_hash,
    }


def issue_retrieval_bundle_document(
    plan: QuestionPlan,
    bundle: IssueRetrievalBundle,
    *,
    snapshot_hash: str,
) -> dict[str, object]:
    """Project issue-aware retrieval into the stable review-request bundle shape."""
    if len(snapshot_hash) != 64:
        raise ValueError("snapshot_hash must be a SHA-256")

    candidate_by_evidence: dict[str, list[IssueClauseCandidate]] = {}
    for candidate in bundle.candidates:
        for hit in candidate.evidence:
            candidate_by_evidence.setdefault(hit.evidence_id, []).append(candidate)

    primary_request = next(
        (request for request in plan.search_requests if request.role == "rule"),
        plan.search_requests[0],
    )
    derived_compound = derive_korean_compound_variants(primary_request.text)
    derived_variants = derive_korean_query_variants(primary_request.text)
    entity_variants = derived_variants.entity or derived_compound

    hit_documents: list[dict[str, object]] = []
    for hit in bundle.selected_evidence:
        candidates = candidate_by_evidence.get(hit.evidence_id, [])
        match_documents: dict[
            tuple[str, str, str, str, str, str], dict[str, object]
        ] = {}
        issue_ids: set[str] = set()
        roles: set[str] = set()
        for candidate in candidates:
            for match in candidate.matches:
                issue_ids.add(match.issue_id)
                roles.add(match.role)
                key = (
                    match.search_request_id,
                    match.issue_id,
                    match.query_text,
                    match.retrieval_query,
                    match.role,
                    match.fallback_stage.value,
                )
                match_documents[key] = {
                    "search_request_id": match.search_request_id,
                    "issue_ids": [match.issue_id],
                    "query_text": match.query_text,
                    "retrieval_query": match.retrieval_query,
                    "origin": "llm",
                    "role": match.role,
                    "fallback_stage": match.fallback_stage.value,
                }
        hit_documents.append(
            {
                "evidence_id": hit.evidence_id,
                "text": hit.text,
                "citation": _citation_document(hit),
                "issue_ids": sorted(issue_ids),
                "roles": sorted(roles),
                "matches": [match_documents[key] for key in sorted(match_documents)],
            }
        )

    return {
        "snapshot_hash": snapshot_hash,
        "query": {
            "primary": plan.original_question,
            "terms": [
                {
                    "text": request.text,
                    "origin": "llm",
                    "search_request_ids": [request.id],
                    "issue_ids": list(request.issue_ids),
                    "role": request.role,
                }
                for request in plan.search_requests
            ],
            "attempted_terms": [
                {"text": request.text, "origin": "llm"}
                for request in plan.search_requests
            ],
            "derived_variants": {
                "compound": list(derived_compound),
                "entity": list(entity_variants),
                "numeric": list(derived_variants.numeric),
                "concept": list(derived_variants.concept),
            },
        },
        "hits": hit_documents,
        "budget_drops": [
            {
                "issue_id": item.issue_id,
                "search_request_id": item.search_request_id,
                "reason": item.reason,
                "clause_id": item.clause_id,
            }
            for item in bundle.budget_drops
        ],
        "fallback_traces": [
            {
                "issue_id": item.issue_id,
                "search_request_id": item.search_request_id,
                "role": item.role,
                "stage": item.stage.value,
                "input_query": item.input_query,
                "derived_query": item.derived_query,
                "hit_count": item.hit_count,
            }
            for item in bundle.fallback_traces
        ],
    }


def _retrieval_match_sort_key(
    item: dict[str, object],
) -> tuple[str, tuple[str, ...], str, str, str, str, str]:
    """Return a strict deterministic sort key for one validated lineage match."""
    return (
        cast(str, item["search_request_id"]),
        tuple(cast(list[str], item["issue_ids"])),
        cast(str, item["query_text"]),
        cast(str, item["origin"]),
        cast(str, item.get("role", "")),
        cast(str, item.get("fallback_stage", "")),
        cast(str, item.get("retrieval_query", "")),
    )


def _retrieval_lineage_sort_key(item: dict[str, object]) -> tuple[str, str]:
    """Return a strict deterministic sort key for one evidence-lineage entry."""
    return cast(str, item["evidence_id"]), cast(str, item["citation_id"])


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
            required = {"search_request_id", "issue_ids", "query_text", "origin"}
            optional = {"role", "fallback_stage", "retrieval_query"}
            if not required.issubset(match_value) or set(match_value) - required - optional:
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
            match_document: dict[str, object] = {
                "search_request_id": search_request_id,
                "issue_ids": sorted(set(issue_ids)),
                "query_text": query_text,
                "origin": origin,
            }
            for field in ("role", "fallback_stage", "retrieval_query"):
                value = match_value.get(field)
                if value is not None:
                    if not isinstance(value, str) or not value:
                        raise ValueError(f"retrieval match {field} must be non-empty")
                    match_document[field] = value
            matches.append(match_document)
        matches.sort(key=_retrieval_match_sort_key)
        lineage.append(
            {
                "evidence_id": evidence_id,
                "citation_id": citation_id,
                "matches": matches,
            }
        )

    bound = dict(request)
    inputs = dict(inputs_value)
    inputs["retrieval_lineage"] = sorted(lineage, key=_retrieval_lineage_sort_key)
    bound["inputs"] = inputs
    return bound


def query_request_from_plan(
    plan: QuestionPlan, *, user_expansions: Sequence[str] = ()
) -> dict[str, object]:
    """Convert a validated plan to the legacy bounded retrieval request contract.

    Kept for compatibility and tests. Planned review execution uses the issue-aware
    coordinator when no explicit user expansion terms are supplied.
    """
    primary_request = next(
        (request for request in plan.search_requests if request.role == "rule"),
        plan.search_requests[0],
    )
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
        "question": primary_request.text,
        "expansions": expansions,
        "synonym_manifest": {},
        "filters": {},
        "clause_ids": [],
        "seed_ids": [],
        "graph_depth": 1,
        "limit": 20,
    }
