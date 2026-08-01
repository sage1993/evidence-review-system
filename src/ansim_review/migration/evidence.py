"""Preserve reviewed evidence across deterministic Ansim rebuilds."""
from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from ansim_review.canonical_json import dump_bytes, sha256_json

_SHA = re.compile(r"^[0-9a-f]{64}$")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _string(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(f"{field} must be a string")
    return value


def _load_records(workspace_root: Path) -> tuple[dict[str, str], ...]:
    candidates = (
        workspace_root / "migration" / "evidence-input.json",
        workspace_root / "05_exports" / "evidence-records.json",
    )
    source = next((path for path in candidates if path.is_file()), None)
    if source is None:
        return ()
    payload = json.loads(source.read_text(encoding="utf-8"))
    records: list[dict[str, str]] = []
    for index, item in enumerate(_sequence(payload, "evidence records")):
        record = _mapping(item, f"records[{index}]")
        source_hash = _string(record.get("source_hash"), "source_hash")
        if not _SHA.fullmatch(source_hash):
            raise ValueError("source_hash must be a lowercase SHA-256 digest")
        review_status = _string(
            record.get("review_status", "AUTOMATIC"), "review_status"
        )
        if review_status not in {"AUTOMATIC", "REVIEWED"}:
            raise ValueError(f"unsupported review_status: {review_status}")
        page_number = record.get("page_number")
        if isinstance(page_number, bool) or not isinstance(page_number, int):
            raise ValueError("page_number must be an integer")
        records.append(
            {
                "stable_id": _string(record.get("stable_id"), "stable_id"),
                "revision_id": _string(record.get("revision_id"), "revision_id"),
                "source_hash": source_hash,
                "document_id": _string(record.get("document_id"), "document_id"),
                "page_number": str(page_number),
                "bbox_json": _string(record.get("bbox_json"), "bbox_json"),
                "raw_text": _string(
                    record.get("raw_text", ""), "raw_text", allow_empty=True
                ),
                "normalized_text": _string(
                    record.get("normalized_text", ""),
                    "normalized_text",
                    allow_empty=True,
                ),
                "review_status": review_status,
            }
        )
    return tuple(records)


def _record_id(record: Mapping[str, str]) -> str:
    digest = sha256_json(
        {
            "stable_id": record["stable_id"],
            "revision_id": record["revision_id"],
            "source_hash": record["source_hash"],
        }
    )
    return f"EVID-{digest[:20].upper()}"


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS migration_records (
          record_id TEXT PRIMARY KEY,
          stable_id TEXT NOT NULL,
          revision_id TEXT NOT NULL,
          source_hash TEXT NOT NULL,
          document_id TEXT NOT NULL,
          page_number INTEGER NOT NULL,
          bbox_json TEXT NOT NULL,
          raw_text TEXT NOT NULL,
          normalized_text TEXT NOT NULL,
          review_status TEXT NOT NULL,
          UNIQUE(stable_id, revision_id, source_hash)
        ) STRICT;
        CREATE TABLE IF NOT EXISTS retrieval_records (
          evidence_id TEXT PRIMARY KEY,
          evidence_type TEXT NOT NULL,
          document_id TEXT NOT NULL,
          revision_id TEXT NOT NULL,
          page_number INTEGER NOT NULL,
          bbox_json TEXT NOT NULL,
          source_hash TEXT NOT NULL,
          title TEXT NOT NULL,
          raw_text TEXT NOT NULL,
          normalized_text TEXT NOT NULL
        ) STRICT;
        """
    )


def migrate_evidence(workspace_root: Path, output_root: Path) -> dict[str, object]:
    """Rebuild records while preserving reviewed identical sources only."""
    records = _load_records(workspace_root)
    database = output_root / "evidence" / "ansim-evidence.sqlite"
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    unresolved: list[dict[str, object]] = []
    try:
        _create_schema(connection)
        for record in records:
            existing_rows = connection.execute(
                "SELECT record_id, revision_id, source_hash, normalized_text, "
                "review_status FROM migration_records WHERE stable_id = ? "
                "ORDER BY record_id",
                (record["stable_id"],),
            ).fetchall()
            identical = next(
                (row for row in existing_rows if row[2] == record["source_hash"]),
                None,
            )
            normalized = record["normalized_text"]
            review_status = record["review_status"]
            if identical is not None and identical[4] == "REVIEWED":
                normalized = identical[3]
                review_status = "REVIEWED"
            elif existing_rows and identical is None:
                review_status = "AUTOMATIC"
                for old in existing_rows:
                    unresolved.append(
                        {
                            "code": "SOURCE_REVISION_REVIEW_REQUIRED",
                            "stable_id": record["stable_id"],
                            "previous_record_id": old[0],
                            "new_record_id": _record_id(record),
                            "previous_source_hash": old[2],
                            "new_source_hash": record["source_hash"],
                        }
                    )
            page_number = int(record["page_number"])
            record_id = _record_id(record)
            connection.execute(
                """INSERT INTO migration_records VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(record_id) DO UPDATE SET
                     raw_text=excluded.raw_text,
                     normalized_text=CASE
                       WHEN migration_records.review_status='REVIEWED'
                       THEN migration_records.normalized_text
                       ELSE excluded.normalized_text END,
                     review_status=CASE
                       WHEN migration_records.review_status='REVIEWED'
                       THEN 'REVIEWED' ELSE excluded.review_status END""",
                (
                    record_id,
                    record["stable_id"],
                    record["revision_id"],
                    record["source_hash"],
                    record["document_id"],
                    page_number,
                    record["bbox_json"],
                    record["raw_text"],
                    normalized,
                    review_status,
                ),
            )
            connection.execute(
                """INSERT INTO retrieval_records VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(evidence_id) DO UPDATE SET
                     raw_text=excluded.raw_text,
                     normalized_text=excluded.normalized_text""",
                (
                    record_id,
                    "clause",
                    record["document_id"],
                    record["revision_id"],
                    page_number,
                    record["bbox_json"],
                    record["source_hash"],
                    record["stable_id"],
                    record["raw_text"],
                    normalized,
                ),
            )
        connection.commit()
    finally:
        connection.close()
    unique = sorted(
        {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in unresolved}
    )
    unresolved_document = {
        "format": "ansim/unresolved-links",
        "version": 1,
        "items": [json.loads(item) for item in unique],
    }
    unresolved_path = output_root / "migration" / "unresolved-links.json"
    unresolved_path.parent.mkdir(parents=True, exist_ok=True)
    unresolved_path.write_bytes(dump_bytes(unresolved_document))
    return {
        "database": database,
        "unresolved_links": unresolved_path,
        "record_count": len(records),
    }
