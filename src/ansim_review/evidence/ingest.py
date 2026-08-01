"""Transactional ingest for deterministic evidence snapshots."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from ansim_review.canonical_json import dumps, sha256_json
from ansim_review.evidence.store import EvidenceStore

Row = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class EvidenceSnapshot:
    documents: tuple[Row, ...] = ()
    revisions: tuple[Row, ...] = ()
    pages: tuple[Row, ...] = ()
    elements: tuple[Row, ...] = ()
    clauses: tuple[Row, ...] = ()
    tables: tuple[Row, ...] = ()
    visuals: tuple[Row, ...] = ()
    links: tuple[Row, ...] = ()
    review_flags: tuple[Row, ...] = ()


def _json_or_none(value: Any) -> str | None:
    return None if value is None else dumps(value)


def _snapshot_payload(snapshot: EvidenceSnapshot) -> dict[str, list[dict[str, Any]]]:
    payload = asdict(snapshot)
    return {
        key: sorted(
            (dict(row) for row in rows),
            key=lambda row: str(row.get("id", "")),
        )
        for key, rows in payload.items()
    }


def ingest_snapshot(store: EvidenceStore, snapshot: EvidenceSnapshot) -> str:
    """Insert all snapshot records atomically and return its canonical hash."""
    connection = store.require_connection()
    snapshot_hash = sha256_json(_snapshot_payload(snapshot))
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.executemany(
            "INSERT INTO documents(id, title) VALUES(?, ?)",
            ((row["id"], row["title"]) for row in snapshot.documents),
        )
        connection.executemany(
            """
            INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                (
                    row["id"], row["document_id"], row["source_hash"],
                    row["byte_size"], row["page_count"],
                )
                for row in snapshot.revisions
            ),
        )
        connection.executemany(
            """
            INSERT INTO pages(id, revision_id, page_number, width, height)
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                (row["id"], row["revision_id"], row["page_number"], row["width"], row["height"])
                for row in snapshot.pages
            ),
        )
        connection.executemany(
            """
            INSERT INTO elements(
                id, revision_id, page_id, page_number, element_type, raw_json,
                raw_text, normalized_text, raw_payload_hash, bbox_json, parser_order
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    row["id"], row["revision_id"], row["page_id"], row["page_number"],
                    row["element_type"], dumps(row["raw_json"]), row.get("raw_text"),
                    row.get("normalized_text"), row["raw_payload_hash"],
                    _json_or_none(row.get("bbox")), row["parser_order"],
                )
                for row in snapshot.elements
            ),
        )
        connection.executemany(
            """
            INSERT INTO clauses(id, revision_id, title, raw_text, normalized_text, review_status)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    row["id"], row["revision_id"], row["title"], row.get("raw_text"),
                    row.get("normalized_text"), row.get("review_status", "AUTOMATIC"),
                )
                for row in snapshot.clauses
            ),
        )
        connection.executemany(
            """
            INSERT INTO tables(id, revision_id, page_number, bbox_json, raw_json, normalized_json)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    row["id"], row["revision_id"], row["page_number"],
                    _json_or_none(row.get("bbox")), dumps(row["raw_json"]),
                    _json_or_none(row.get("normalized_json")),
                )
                for row in snapshot.tables
            ),
        )
        connection.executemany(
            """
            INSERT INTO visuals(
                id, revision_id, page_number, kind, relative_path, sha256,
                bbox_json, duplicate_group
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    row["id"], row["revision_id"], row["page_number"], row["kind"],
                    row["relative_path"], row["sha256"], _json_or_none(row.get("bbox")),
                    row["duplicate_group"],
                )
                for row in snapshot.visuals
            ),
        )
        connection.executemany(
            "INSERT INTO links(id, source_id, target_id, relation_type) VALUES(?, ?, ?, ?)",
            (
                (row["id"], row["source_id"], row["target_id"], row["relation_type"])
                for row in snapshot.links
            ),
        )
        connection.executemany(
            """
            INSERT INTO review_flags(id, evidence_id, code, status, detail)
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                (
                    row["id"], row["evidence_id"], row["code"], row["status"],
                    row.get("detail"),
                )
                for row in snapshot.review_flags
            ),
        )
        connection.execute(
            "INSERT INTO snapshot_meta(key, value) VALUES('snapshot_hash', ?)",
            (snapshot_hash,),
        )
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
    return snapshot_hash
