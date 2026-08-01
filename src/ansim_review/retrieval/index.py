"""SQLite FTS5 indexing and lexical retrieval."""
from __future__ import annotations

import json
import sqlite3
import unicodedata
from decimal import Decimal

from ansim_review.canonical_json import dumps
from ansim_review.contracts.common import BBox
from ansim_review.retrieval.models import ChannelScore, RetrievalHit


class StaleRetrievalIndexError(RuntimeError):
    """Raised when the FTS index and evidence snapshot hashes differ."""


def _nfc(value: str | None) -> str:
    return unicodedata.normalize("NFC", value or "")


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
        SELECT e.id, e.element_type, r.document_id, e.revision_id, e.page_number,
               e.bbox_json, r.source_hash, d.title, e.raw_text, e.normalized_text
        FROM elements e
        JOIN revisions r ON r.id = e.revision_id
        JOIN documents d ON d.id = r.document_id
        WHERE e.bbox_json IS NOT NULL
        ORDER BY e.id
        """
    ):
        bbox = _bbox(row[5])
        if bbox is None:
            continue
        rows.append(
            (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                dumps([bbox.left, bbox.bottom, bbox.right, bbox.top]),
                row[6],
                _nfc(row[7]),
                _nfc(row[8]),
                _nfc(row[9] or row[8]),
            )
        )
    for row in connection.execute(
        """
        SELECT t.id, r.document_id, t.revision_id, t.page_number, t.bbox_json,
               r.source_hash, d.title, t.raw_json, t.normalized_json
        FROM tables t
        JOIN revisions r ON r.id = t.revision_id
        JOIN documents d ON d.id = r.document_id
        WHERE t.bbox_json IS NOT NULL
        ORDER BY t.id
        """
    ):
        bbox = _bbox(row[4])
        if bbox is None:
            continue
        rows.append(
            (
                row[0],
                "table",
                row[1],
                row[2],
                row[3],
                dumps([bbox.left, bbox.bottom, bbox.right, bbox.top]),
                row[5],
                _nfc(f"{row[6]} 표 {row[0]}"),
                _nfc(row[7]),
                _nfc(row[8] or row[7]),
            )
        )
    for row in connection.execute(
        """
        SELECT v.id, r.document_id, v.revision_id, v.page_number, v.bbox_json,
               r.source_hash, d.title, v.kind, v.relative_path
        FROM visuals v
        JOIN revisions r ON r.id = v.revision_id
        JOIN documents d ON d.id = r.document_id
        WHERE v.bbox_json IS NOT NULL
        ORDER BY v.id
        """
    ):
        bbox = _bbox(row[4])
        if bbox is None:
            continue
        text = _nfc(f"{row[7]} {row[8]}")
        rows.append(
            (
                row[0],
                "visual",
                row[1],
                row[2],
                row[3],
                dumps([bbox.left, bbox.bottom, bbox.right, bbox.top]),
                row[5],
                _nfc(f"{row[6]} {row[7]}"),
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
                evidence_id, evidence_type, document_id, revision_id, page_number,
                bbox_json, source_hash, title, raw_text, normalized_text
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.executemany(
            """
            INSERT INTO evidence_fts(evidence_id, title, raw_text, normalized_text)
            VALUES(?, ?, ?, ?)
            """,
            ((row[0], row[7], row[8], row[9]) for row in rows),
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


def _match_expression(query: str) -> str:
    normalized = unicodedata.normalize("NFC", " ".join(query.split()))
    if not normalized:
        raise ValueError("query must not be empty")
    return '"' + normalized.replace('"', '""') + '"'


def _row_to_hit(row: sqlite3.Row, rank_index: int, query: str) -> RetrievalHit:
    bbox_payload = json.loads(row["bbox_json"])
    bbox = BBox(*(float(item) for item in bbox_payload))
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
        channel_scores=(ChannelScore("fts", score, query),),
    )


def search_fts(
    connection: sqlite3.Connection,
    query: str,
    limit: int = 20,
) -> tuple[RetrievalHit, ...]:
    """Return deterministic page-resolved lexical hits."""
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
        (_match_expression(query), limit),
    ).fetchall()
    return tuple(
        _row_to_hit(row, index, query) for index, row in enumerate(rows)
    )


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
    bbox_payload = json.loads(row["bbox_json"])
    return RetrievalHit(
        evidence_id=row["evidence_id"],
        evidence_type=row["evidence_type"],
        document_id=row["document_id"],
        revision_id=row["revision_id"],
        page_number=row["page_number"],
        bbox=BBox(*(float(item) for item in bbox_payload)),
        source_hash=row["source_hash"],
        title=row["title"],
        text=row["normalized_text"] or row["raw_text"],
        channel_scores=(channel,),
    )
