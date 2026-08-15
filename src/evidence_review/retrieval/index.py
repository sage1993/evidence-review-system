"""SQLite FTS5 indexing and lexical retrieval."""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from decimal import Decimal

from evidence_review.canonical_json import dumps
from evidence_review.contracts.common import BBox
from evidence_review.retrieval.models import ChannelScore, RetrievalHit

_GROUP_CHANNELS = frozenset({
    "fts_entity",
    "fts_numeric",
    "fts_concept",
    "fts_korean_compound",
})


class StaleRetrievalIndexError(RuntimeError):
    """Raised when the FTS index and evidence snapshot hashes differ."""


def _nfc(value: str | None) -> str:
    return unicodedata.normalize("NFC", value or "")


_HANGUL_TOKEN = re.compile(r"^[\uac00-\ud7a3]+$")


def _fts_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", " ".join(value.split()))
    for marker in ("\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"):
        normalized = normalized.replace(marker, "")

    tokens = normalized.split()
    aliases: list[str] = []
    for size in (2, 3):
        for start in range(0, len(tokens) - size + 1):
            group = tokens[start : start + size]
            cleaned = [
                token.strip(".,!?;:()[]{}<>\\\"'“”‘’") for token in group
            ]
            if all(_HANGUL_TOKEN.fullmatch(token) for token in cleaned):
                aliases.append("".join(cleaned))

    values = [normalized, *aliases]
    return " ".join(dict.fromkeys(value for value in values if value))

def _bbox(value: str | None) -> BBox | None:
    if value is None:
        return None
    payload = json.loads(value)
    if not isinstance(payload, list) or len(payload) != 4:
        return None
    if any(
        isinstance(item, bool) or not isinstance(item, (int, float))
        for item in payload
    ):
        return None
    return BBox(*(float(item) for item in payload))


def _bbox_json(value: str | None) -> str | None:
    bbox = _bbox(value)
    if value is not None and bbox is None:
        return None
    if bbox is None:
        return dumps(None)
    return dumps([bbox.left, bbox.bottom, bbox.right, bbox.top])


def _snapshot_hash(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT value FROM snapshot_meta WHERE key = 'snapshot_hash'"
    ).fetchone()
    if row is None or not isinstance(row[0], str):
        raise RuntimeError("evidence snapshot hash is missing")
    return row[0]


def _record_rows(connection: sqlite3.Connection) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for row in connection.execute(
        """
        SELECT e.id, e.element_type, r.document_id, p.revision_id, p.id,
               p.page_number, e.bbox_json, r.source_hash, d.title,
               e.raw_text, e.normalized_text
        FROM elements e
        JOIN pages p ON p.id = e.page_id
        JOIN revisions r ON r.id = p.revision_id
        JOIN documents d ON d.id = r.document_id
        ORDER BY e.id
        """
    ):
        bbox_json = _bbox_json(row[6])
        if bbox_json is None:
            continue
        rows.append(
            (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                bbox_json,
                row[7],
                _nfc(row[8]),
                _nfc(row[9]),
                _nfc(row[10] or row[9]),
            )
        )
    for row in connection.execute(
        """
        SELECT t.id, r.document_id, p.revision_id, p.id, p.page_number,
               t.bbox_json, r.source_hash, d.title, t.raw_json,
               t.normalized_json
        FROM tables t
        JOIN pages p ON p.id = t.page_id
        JOIN revisions r ON r.id = p.revision_id
        JOIN documents d ON d.id = r.document_id
        ORDER BY t.id
        """
    ):
        bbox_json = _bbox_json(row[5])
        if bbox_json is None:
            continue
        rows.append(
            (
                row[0],
                "table",
                row[1],
                row[2],
                row[3],
                row[4],
                bbox_json,
                row[6],
                _nfc(f"{row[7]} 표 {row[0]}"),
                _nfc(row[8]),
                _nfc(row[9] or row[8]),
            )
        )
    for row in connection.execute(
        """
        SELECT v.id, r.document_id, p.revision_id, p.id, p.page_number,
               v.bbox_json, r.source_hash, d.title, v.kind, v.relative_path
        FROM visuals v
        JOIN pages p ON p.id = v.page_id
        JOIN revisions r ON r.id = p.revision_id
        JOIN documents d ON d.id = r.document_id
        ORDER BY v.id
        """
    ):
        bbox_json = _bbox_json(row[5])
        if bbox_json is None:
            continue
        text = _nfc(f"{row[8]} {row[9]}")
        rows.append(
            (
                row[0],
                "visual",
                row[1],
                row[2],
                row[3],
                row[4],
                bbox_json,
                row[6],
                _nfc(f"{row[7]} {row[8]}"),
                text,
                text,
            )
        )
    return rows


def build_fts_index(connection: sqlite3.Connection) -> str:
    """Rebuild the page-resolved retrieval index for the current snapshot."""
    snapshot_hash = _snapshot_hash(connection)
    rows = _record_rows(connection)
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("DELETE FROM evidence_fts")
        connection.execute("DELETE FROM retrieval_records")
        connection.executemany(
            """
            INSERT INTO retrieval_records(
                evidence_id, evidence_type, document_id, revision_id, page_id,
                page_number, bbox_json, source_hash, title, raw_text,
                normalized_text
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.executemany(
            """
            INSERT INTO evidence_fts(evidence_id, title, raw_text, normalized_text)
            VALUES(?, ?, ?, ?)
            """,
            ((row[0], row[8], row[9], _fts_search_text(str(row[10]))) for row in rows),
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO retrieval_meta(key, value)
            VALUES('snapshot_hash', ?)
            """,
            (snapshot_hash,),
        )
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
    return snapshot_hash


def require_fresh_index(connection: sqlite3.Connection) -> str:
    """Return the snapshot hash after enforcing index freshness."""
    evidence_hash = _snapshot_hash(connection)
    row = connection.execute(
        "SELECT value FROM retrieval_meta WHERE key = 'snapshot_hash'"
    ).fetchone()
    index_hash = None if row is None else row[0]
    if index_hash != evidence_hash:
        raise StaleRetrievalIndexError("retrieval index snapshot hash mismatch")
    return evidence_hash


def _normalized_query(query: str) -> str:
    normalized = unicodedata.normalize("NFC", " ".join(query.split()))
    if not normalized:
        raise ValueError("query must not be empty")
    return normalized


def _quoted_literal(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _phrase_match_expression(query: str) -> str:
    return _quoted_literal(_normalized_query(query))


def _prefix_match_expression(query: str) -> str:
    return f"{_quoted_literal(_normalized_query(query))}*"


def _token_and_match_expression(query: str) -> str:
    tokens = _normalized_query(query).split(" ")
    return " AND ".join(_quoted_literal(token) for token in tokens)


def _indexed_bbox(value: str) -> BBox | None:
    payload = json.loads(value)
    if payload is None:
        return None
    if not isinstance(payload, list) or len(payload) != 4:
        raise ValueError("INVALID_INDEXED_BBOX")
    if any(
        isinstance(item, bool) or not isinstance(item, (int, float))
        for item in payload
    ):
        raise ValueError("INVALID_INDEXED_BBOX")
    return BBox(*(float(item) for item in payload))


def _row_to_hit(
    row: sqlite3.Row,
    rank_index: int,
    query: str,
    channel: str,
) -> RetrievalHit:
    bbox = _indexed_bbox(row["bbox_json"])
    score = Decimal(1) / Decimal(rank_index + 1)
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
        channel_scores=(ChannelScore(channel, score, query),),
    )


def _search_fts(
    connection: sqlite3.Connection,
    query: str,
    *,
    match_expression: str,
    channel: str,
    limit: int,
) -> tuple[RetrievalHit, ...]:
    require_fresh_index(connection)
    if limit < 1:
        return ()
    rows = connection.execute(
        """
        SELECT rr.*, bm25(evidence_fts) AS bm25_rank
        FROM evidence_fts
        JOIN retrieval_records rr ON rr.evidence_id = evidence_fts.evidence_id
        WHERE evidence_fts MATCH ?
        ORDER BY bm25_rank ASC, rr.evidence_id ASC
        LIMIT ?
        """,
        (match_expression, limit),
    ).fetchall()
    return tuple(
        _row_to_hit(row, index, query, channel)
        for index, row in enumerate(rows)
    )


def search_fts_phrase(
    connection: sqlite3.Connection,
    query: str,
    limit: int = 20,
) -> tuple[RetrievalHit, ...]:
    """Return exact-phrase lexical hits for precision-sensitive matching."""
    return _search_fts(
        connection,
        query,
        match_expression=_phrase_match_expression(query),
        channel="fts_phrase",
        limit=limit,
    )


def search_fts_token_and(
    connection: sqlite3.Connection,
    query: str,
    limit: int = 20,
) -> tuple[RetrievalHit, ...]:
    """Return order-insensitive hits requiring every whitespace-delimited token."""
    return _search_fts(
        connection,
        query,
        match_expression=_token_and_match_expression(query),
        channel="fts_token_and",
        limit=limit,
    )


def search_fts_literal(
    connection: sqlite3.Connection,
    query: str,
    *,
    channel: str,
    limit: int = 20,
) -> tuple[RetrievalHit, ...]:
    """Search one bounded derived term with Korean suffix-tolerant prefix matching."""
    if channel not in _GROUP_CHANNELS:
        raise ValueError(f"unsupported grouped FTS channel: {channel}")
    return _search_fts(
        connection,
        query,
        match_expression=_prefix_match_expression(query),
        channel=channel,
        limit=limit,
    )


def search_fts(
    connection: sqlite3.Connection,
    query: str,
    limit: int = 20,
) -> tuple[RetrievalHit, ...]:
    """Compatibility wrapper for the historical exact-phrase FTS behavior."""
    return search_fts_phrase(connection, query, limit)


def load_indexed_hit(
    connection: sqlite3.Connection,
    evidence_id: str,
    channel: ChannelScore,
) -> RetrievalHit | None:
    """Load one indexed evidence record with an attached channel score."""
    require_fresh_index(connection)
    row = connection.execute(
        "SELECT * FROM retrieval_records WHERE evidence_id = ?",
        (evidence_id,),
    ).fetchone()
    if row is None:
        return None
    return RetrievalHit(
        evidence_id=row["evidence_id"],
        evidence_type=row["evidence_type"],
        document_id=row["document_id"],
        revision_id=row["revision_id"],
        page_number=row["page_number"],
        bbox=_indexed_bbox(row["bbox_json"]),
        source_hash=row["source_hash"],
        title=row["title"],
        text=row["normalized_text"] or row["raw_text"],
        channel_scores=(channel,),
    )


def load_adjacent_element_hits(
    connection: sqlite3.Connection,
    seed: RetrievalHit,
    *,
    radius: int = 1,
) -> tuple[RetrievalHit, ...]:
    """Load separately cited parser-order neighbors from the seed page only."""
    require_fresh_index(connection)
    if radius < 1:
        return ()
    seed_row = connection.execute(
        "SELECT page_id, parser_order FROM elements WHERE id = ?",
        (seed.evidence_id,),
    ).fetchone()
    if seed_row is None:
        return ()
    page_id = seed_row["page_id"]
    parser_order = seed_row["parser_order"]
    rows = connection.execute(
        """
        SELECT e.id
        FROM elements e
        JOIN retrieval_records rr ON rr.evidence_id = e.id
        WHERE e.page_id = ?
          AND e.parser_order BETWEEN ? AND ?
          AND e.id <> ?
        ORDER BY ABS(e.parser_order - ?), e.parser_order, e.id
        """,
        (
            page_id,
            parser_order - radius,
            parser_order + radius,
            seed.evidence_id,
            parser_order,
        ),
    ).fetchall()
    channel = ChannelScore(
        channel="structural_context",
        score=Decimal("1"),
        detail=f"seed:{seed.evidence_id}",
    )
    hits: list[RetrievalHit] = []
    for row in rows:
        hit = load_indexed_hit(connection, row["id"], channel)
        if hit is not None:
            hits.append(hit)
    return tuple(hits)
