"""Project issue-bound reference evidence into the stable retrieval bundle document."""

from __future__ import annotations

from evidence_review.retrieval.issue_bundle import IssueRetrievalBundle


def apply_reference_lineage_to_bundle_document(
    document: dict[str, object],
    retrieval: IssueRetrievalBundle,
) -> dict[str, object]:
    """Attach reference-expansion lineage to already projected selected hits."""
    hits_value = document.get("hits")
    if not isinstance(hits_value, list):
        raise ValueError("retrieval bundle document hits must be an array")

    projected_hits: list[dict[str, object]] = []
    by_evidence: dict[str, dict[str, object]] = {}
    for index, value in enumerate(hits_value):
        if not isinstance(value, dict):
            raise ValueError(f"hits[{index}] must be an object")
        hit = dict(value)
        evidence_id = hit.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise ValueError(f"hits[{index}].evidence_id must be non-empty")
        hit["issue_ids"] = list(hit.get("issue_ids", []))
        hit["roles"] = list(hit.get("roles", []))
        matches_value = hit.get("matches", [])
        if not isinstance(matches_value, list):
            raise ValueError("projected hit matches must be an array")
        match_documents: list[dict[str, object]] = []
        for match_index, match_value in enumerate(matches_value):
            if not isinstance(match_value, dict):
                raise ValueError(
                    f"hits[{index}].matches[{match_index}] must be an object"
                )
            match_documents.append(dict(match_value))
        hit["matches"] = match_documents
        projected_hits.append(hit)
        by_evidence[evidence_id] = hit

    for reference in retrieval.reference_matches:
        reference_hit = by_evidence.get(reference.evidence_id)
        if reference_hit is None:
            raise ValueError(
                f"reference evidence is not selected: {reference.evidence_id}"
            )
        issue_values = reference_hit.get("issue_ids", [])
        role_values = reference_hit.get("roles", [])
        if not isinstance(issue_values, list) or not all(
            isinstance(item, str) for item in issue_values
        ):
            raise ValueError("projected hit issue_ids must be an array of strings")
        if not isinstance(role_values, list) or not all(
            isinstance(item, str) for item in role_values
        ):
            raise ValueError("projected hit roles must be an array of strings")
        issue_ids = set(issue_values)
        roles = set(role_values)
        issue_ids.add(reference.issue_id)
        roles.add(reference.role)
        reference_hit["issue_ids"] = sorted(issue_ids)
        reference_hit["roles"] = sorted(roles)
        matches = reference_hit["matches"]
        if not isinstance(matches, list):
            raise ValueError("projected hit matches must be an array")
        match = {
            "search_request_id": reference.search_request_id,
            "issue_ids": [reference.issue_id],
            "query_text": reference.query_text,
            "retrieval_query": reference.retrieval_query,
            "origin": "llm",
            "role": reference.role,
            "fallback_stage": "REFERENCE_EXPANSION",
        }
        if match not in matches:
            matches.append(match)
            matches.sort(
                key=lambda item: (
                    str(item.get("search_request_id", "")),
                    tuple(item.get("issue_ids", [])),
                    str(item.get("query_text", "")),
                    str(item.get("fallback_stage", "")),
                )
            )

    result = dict(document)
    result["hits"] = projected_hits
    return result
