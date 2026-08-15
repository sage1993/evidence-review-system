"""Exact structured retrieval over indexed evidence metadata."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from decimal import Decimal

from evidence_review.canonical_json import dumps
from evidence_review.contracts.common import BBox
from evidence_review.retrieval.index import require_fresh_index
from evidence_review.retrieval.models import ChannelScore, RetrievalHit

_ALLOWED_FILTERS = {
    "evidence_id",
    "evidence_type",
    "document_id",
    "revision_id",
    "page_number",
    "title",
}


def _hit(row: sqlite3.Row, channel: str, detail: str) -> RetrievalHit:
    bbox_payload = json.loads(row["bbox_json"])
    bbox = (
        None
        if bbox_payload is None
        else BBox(*(float(item) for item in bbox_payload))
    )
    return RetrievalHit(
        evidence_id=row["evidence_id"],
        evidence_type=row["evidence_type"],
        document_id=row["document_id"],
        revision_id=row["revision_id"],
        page_number=row["page_number"],
        bbox=bbox,
        source_hash=row["source_hash"],
        title=row["title"],
        text=row["normalized_text"] or row["raw_text"],
        channel_scores=(ChannelScore(channel, Decimal("1"), detail),),
    )


def retrieve_structured(
    connection: sqlite3.Connection,
    filters: Mapping[str, object],
    limit: int = 100,
) -> tuple[RetrievalHit, ...]:
    """Retrieve exact metadata matches with stable evidence-ID ordering."""
    require_fresh_index(connection)
    unknown = sorted(set(filters) - _ALLOWED_FILTERS)
    if unknown:
        raise ValueError(
            f"unsupported structured filters: {', '.join(unknown)}"
        )
    if limit < 1:
        return ()
    clauses: list[str] = []
    parameters: list[object] = []
    for key in sorted(filters):
        value = filters[key]
        if key == "page_number":
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
            ):
                raise ValueError(
                    "page_number filter must be a positive integer"
                )
        elif not isinstance(value, str) or not value:
            raise ValueError(f"{key} filter must be a non-empty string")
        clauses.append(f"{key} = ?")
        parameters.append(value)
    where = " AND ".join(clauses) if clauses else "1 = 1"
    parameters.append(limit)
    rows = connection.execute(
        f"SELECT * FROM retrieval_records WHERE {where} "
        "ORDER BY evidence_id LIMIT ?",
        tuple(parameters),
    ).fetchall()
    detail = dumps(dict(sorted(filters.items())))
    return tuple(_hit(row, "structured_exact", detail) for row in rows)


def retrieve_clause_ids(
    connection: sqlite3.Connection,
    clause_ids: Sequence[str],
) -> tuple[RetrievalHit, ...]:
    """Retrieve explicit clause/evidence identifiers as a separate channel."""
    require_fresh_index(connection)
    identifiers = tuple(sorted(set(clause_ids)))
    if not identifiers:
        return ()
    placeholders = ",".join("?" for _ in identifiers)
    rows = connection.execute(
        "SELECT * FROM retrieval_records "
        f"WHERE evidence_id IN ({placeholders}) ORDER BY evidence_id",
        identifiers,
    ).fetchall()
    return tuple(
        _hit(row, "clause_id", row["evidence_id"]) for row in rows
    )
