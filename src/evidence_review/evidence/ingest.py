"""Transactional ingest for deterministic evidence snapshots."""
from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from evidence_review.canonical_json import dumps, sha256_json
from evidence_review.evidence.page_geometry import (
    PageGeometry,
    load_page_geometry,
    validate_bbox_within_page,
)
from evidence_review.evidence.store import EvidenceStore

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


def _positive_page_number(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _resolve_page(
    connection: sqlite3.Connection,
    row: Row,
) -> PageGeometry:
    page_id_value = row.get("page_id")
    if page_id_value is not None:
        if not isinstance(page_id_value, str) or not page_id_value:
            raise ValueError("page_id must be a non-empty string")
        page = load_page_geometry(connection, page_id_value)
    else:
        revision_id = row.get("revision_id")
        if not isinstance(revision_id, str) or not revision_id:
            raise ValueError("PAGE_REFERENCE_NOT_FOUND: revision_id is required")
        page_number = _positive_page_number(row.get("page_number"), "page_number")
        resolved = connection.execute(
            """
            SELECT id
            FROM pages
            WHERE revision_id = ? AND page_number = ?
            """,
            (revision_id, page_number),
        ).fetchone()
        if resolved is None:
            raise ValueError(
                f"PAGE_REFERENCE_NOT_FOUND: {revision_id} page {page_number}"
            )
        page = load_page_geometry(connection, str(resolved[0]))

    declared_revision = row.get("revision_id")
    if declared_revision is not None and declared_revision != page.revision_id:
        raise ValueError(
            "PAGE_REFERENCE_MISMATCH: "
            f"{page.page_id} belongs to {page.revision_id}, not {declared_revision}"
        )
    declared_page_number = row.get("page_number")
    if declared_page_number is not None:
        page_number = _positive_page_number(declared_page_number, "page_number")
        if page_number != page.page_number:
            raise ValueError(
                "PAGE_REFERENCE_MISMATCH: "
                f"{page.page_id} is page {page.page_number}, not {page_number}"
            )
    return page


def _bbox_json(row: Row, page: PageGeometry) -> str | None:
    bbox = validate_bbox_within_page(row.get("bbox"), page)
    if bbox is None:
        return None
    return dumps([bbox.left, bbox.bottom, bbox.right, bbox.top])


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
                    row["id"],
                    row["document_id"],
                    row["source_hash"],
                    row["byte_size"],
                    row["page_count"],
                )
                for row in snapshot.revisions
            ),
        )
        page_columns = {
            str(item[1])
            for item in connection.execute("PRAGMA table_info(pages)").fetchall()
        }
        if "origin_x" in page_columns:
            connection.executemany(
                """
                INSERT INTO pages(
                    id, revision_id, page_number, width, height,
                    origin_x, origin_y, rotation, box_kind
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        row["id"],
                        row["revision_id"],
                        row["page_number"],
                        row["width"],
                        row["height"],
                        row.get("origin_x", 0.0),
                        row.get("origin_y", 0.0),
                        row.get("rotation", 0),
                        row.get("box_kind", "MEDIA_BOX"),
                    )
                    for row in snapshot.pages
                ),
            )
        else:
            connection.executemany(
                """
                INSERT INTO pages(id, revision_id, page_number, width, height)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    (
                        row["id"],
                        row["revision_id"],
                        row["page_number"],
                        row["width"],
                        row["height"],
                    )
                    for row in snapshot.pages
                ),
            )

        element_rows = []
        for row in snapshot.elements:
            page = _resolve_page(connection, row)
            element_rows.append(
                (
                    row["id"],
                    page.page_id,
                    row["element_type"],
                    dumps(row["raw_json"]),
                    row.get("raw_text"),
                    row.get("normalized_text"),
                    row["raw_payload_hash"],
                    _bbox_json(row, page),
                    row["parser_order"],
                )
            )
        connection.executemany(
            """
            INSERT INTO elements(
                id, page_id, element_type, raw_json, raw_text, normalized_text,
                raw_payload_hash, bbox_json, parser_order
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            element_rows,
        )

        connection.executemany(
            """
            INSERT INTO clauses(id, revision_id, title, raw_text, normalized_text, review_status)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    row["id"],
                    row["revision_id"],
                    row["title"],
                    row.get("raw_text"),
                    row.get("normalized_text"),
                    row.get("review_status", "AUTOMATIC"),
                )
                for row in snapshot.clauses
            ),
        )

        table_rows = []
        for row in snapshot.tables:
            page = _resolve_page(connection, row)
            table_rows.append(
                (
                    row["id"],
                    page.page_id,
                    _bbox_json(row, page),
                    dumps(row["raw_json"]),
                    _json_or_none(row.get("normalized_json")),
                )
            )
        connection.executemany(
            """
            INSERT INTO tables(id, page_id, bbox_json, raw_json, normalized_json)
            VALUES(?, ?, ?, ?, ?)
            """,
            table_rows,
        )

        visual_rows = []
        for row in snapshot.visuals:
            page = _resolve_page(connection, row)
            visual_rows.append(
                (
                    row["id"],
                    page.page_id,
                    row["kind"],
                    row["relative_path"],
                    row["sha256"],
                    _bbox_json(row, page),
                    row["duplicate_group"],
                )
            )
        connection.executemany(
            """
            INSERT INTO visuals(
                id, page_id, kind, relative_path, sha256, bbox_json,
                duplicate_group
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            visual_rows,
        )
        connection.executemany(
            "INSERT INTO links(id, source_id, target_id, relation_type) VALUES(?, ?, ?, ?)",
            (
                (
                    row["id"],
                    row["source_id"],
                    row["target_id"],
                    row["relation_type"],
                )
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
                    row["id"],
                    row["evidence_id"],
                    row["code"],
                    row["status"],
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
