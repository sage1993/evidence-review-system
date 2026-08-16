"""Deterministically bind CLI user retrieval expansions to a validated QuestionPlan."""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Sequence
from dataclasses import replace

from evidence_review.contracts.question_plan import (
    MAX_SEARCH_REQUESTS,
    QuestionPlan,
    SearchRequest,
)


def _normalize_expansion(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = unicodedata.normalize("NFC", " ".join(value.split()))
    if not normalized:
        raise ValueError(f"{field} must be a non-empty string")
    return normalized


def plan_with_user_expansions(
    plan: QuestionPlan,
    user_expansions: Sequence[str] = (),
) -> QuestionPlan:
    """Return an effective plan with manual expansions bound to the primary issue/role."""
    if not user_expansions:
        return plan

    primary_request = next(
        (request for request in plan.search_requests if request.role == "rule"),
        plan.search_requests[0],
    )
    existing_keys = {(request.text, request.kind) for request in plan.search_requests}
    existing_ids = {request.id for request in plan.search_requests}
    additions: list[SearchRequest] = []

    for index, value in enumerate(user_expansions):
        text = _normalize_expansion(value, f"user_expansions[{index}]")
        key = (text, primary_request.kind)
        if key in existing_keys:
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12].upper()
        request_id = f"USER-EXP-{index + 1:02d}-{digest}"
        if request_id in existing_ids:
            raise ValueError(f"user expansion search request id collision: {request_id}")
        additions.append(
            SearchRequest(
                id=request_id,
                issue_ids=primary_request.issue_ids,
                text=text,
                kind=primary_request.kind,
                source="user",
                role=primary_request.role,
            )
        )
        existing_ids.add(request_id)
        existing_keys.add(key)

    if not additions:
        return plan
    if len(plan.search_requests) + len(additions) > MAX_SEARCH_REQUESTS:
        raise ValueError(f"search_requests exceeds maximum of {MAX_SEARCH_REQUESTS}")
    return replace(plan, search_requests=tuple(additions) + plan.search_requests)


def apply_search_request_origins(
    bundle: dict[str, object],
    plan: QuestionPlan,
) -> dict[str, object]:
    """Project SearchRequest.source into query and evidence-match origin fields."""
    origin_by_id = {
        request.id: ("user" if request.source == "user" else "llm")
        for request in plan.search_requests
    }
    user_texts = {
        request.text for request in plan.search_requests if request.source == "user"
    }

    result = dict(bundle)
    query_value = bundle.get("query")
    if not isinstance(query_value, dict):
        raise ValueError("evidence bundle query must be an object")
    query = dict(query_value)

    terms_value = query.get("terms", [])
    if not isinstance(terms_value, list):
        raise ValueError("evidence bundle query terms must be an array")
    terms: list[dict[str, object]] = []
    for index, value in enumerate(terms_value):
        if not isinstance(value, dict):
            raise ValueError(f"query.terms[{index}] must be an object")
        term = dict(value)
        request_ids_value = term.get("search_request_ids", [])
        if not isinstance(request_ids_value, list) or not all(
            isinstance(item, str) for item in request_ids_value
        ):
            raise ValueError(f"query.terms[{index}].search_request_ids must be strings")
        request_ids = tuple(item for item in request_ids_value if isinstance(item, str))
        origins = {origin_by_id[item] for item in request_ids if item in origin_by_id}
        if len(origins) == 1:
            term["origin"] = next(iter(origins))
        terms.append(term)
    query["terms"] = terms

    attempted_value = query.get("attempted_terms", [])
    if not isinstance(attempted_value, list):
        raise ValueError("evidence bundle attempted_terms must be an array")
    attempted: list[dict[str, object]] = []
    for index, value in enumerate(attempted_value):
        if not isinstance(value, dict):
            raise ValueError(f"query.attempted_terms[{index}] must be an object")
        item = dict(value)
        text = item.get("text")
        if isinstance(text, str) and text in user_texts:
            item["origin"] = "user"
        attempted.append(item)
    query["attempted_terms"] = attempted
    result["query"] = query

    hits_value = bundle.get("hits", [])
    if not isinstance(hits_value, list):
        raise ValueError("evidence bundle hits must be an array")
    hits: list[dict[str, object]] = []
    for hit_index, value in enumerate(hits_value):
        if not isinstance(value, dict):
            raise ValueError(f"hits[{hit_index}] must be an object")
        hit = dict(value)
        matches_value = hit.get("matches", [])
        if not isinstance(matches_value, list):
            raise ValueError(f"hits[{hit_index}].matches must be an array")
        matches: list[dict[str, object]] = []
        for match_index, match_value in enumerate(matches_value):
            if not isinstance(match_value, dict):
                raise ValueError(
                    f"hits[{hit_index}].matches[{match_index}] must be an object"
                )
            match = dict(match_value)
            request_id = match.get("search_request_id")
            if isinstance(request_id, str) and request_id in origin_by_id:
                match["origin"] = origin_by_id[request_id]
            matches.append(match)
        hit["matches"] = matches
        hits.append(hit)
    result["hits"] = hits
    return result
