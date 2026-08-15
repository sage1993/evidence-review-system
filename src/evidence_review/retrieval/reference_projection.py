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
        hit["matches"] = [dict(item) for item in hit.get("matches", [])]
        projected_hits.append(hit)
        by_evidence[evidence_id] = hit

    for reference in retrieval.reference_matches:
        hit = by_evidence.get(reference.evidence_id)
        if hit is None:
            raise ValueError(
                f"reference evidence is not selected: {reference.evidence_id}"
            )
        issue_ids = set(hit["issue_ids"])
        roles = set(hit["roles"])
        issue_ids.add(reference.issue_id)
        roles.add(reference.role)
        hit["issue_ids"] = sorted(issue_ids)
        hit["roles"] = sorted(roles)
        matches = hit["matches"]
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
