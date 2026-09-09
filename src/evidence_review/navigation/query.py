"""Navigation query validation and deterministic retrieval requests."""

from __future__ import annotations

from evidence_review.retrieval.query import normalize_text


def navigation_request(query: str, *, limit: int) -> tuple[str, dict[str, object]]:
    """Normalize one navigation query and create its retrieval request."""
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    normalized = normalize_text(query)
    if not normalized:
        raise ValueError("query must not be empty")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    return normalized, {"question": normalized, "limit": limit}
