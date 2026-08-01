"""Copy-on-write migration from evidence schema v1 to schema v2."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ansim_review.canonical_json import dump_bytes
from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.page_geometry import (
    PageGeometry,
    validate_bbox_within_page,
)
from ansim_review.evidence.schema_version import SCHEMA_VERSION, detect_schema_version
from ansim_review.evidence.snapshot import (
    compute_logical_snapshot_hash,
    compute_snapshot_hash,
    snapshot_counts,
)
from ansim_review.evidence.store import EvidenceStore
from ansim_review.retrieval.index import build_fts_index


@dataclass(frozen=True, slots=True)
class MigrationReport:
    """Deterministic result of one successful v1-to-v2 migration."""

    source_db: Path
    output_db: Path
    report_path: Path
    source_schema_version: int
    output_schema_version: int
    source_sha256: str
    output_sha256: str
    logical_snapshot_hash: str
    counts: dict[str, int]


def migration_report_document(report: MigrationReport) -> dict[str, object]:
    """Return the canonical external migration report document."""
    return {
        "format": "evidence-review/evidence-migration-report",
        "version": 1,
        "source_file": report.source_db.name,
        "output_file": report.output_db.name,
        "source_schema_version": report.source_schema_version,
        "output_schema_version": report.output_schema_version,
        "source_sha256": report.source_sha256,
        "output_sha256": report.output_sha256,
        "logical_snapshot_hash": report.logical_snapshot_hash,
        "counts": report.counts,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_only_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _json_value(value: object, field: str) -> object:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must contain JSON text or null")
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"{field} contains invalid JSON") from error


def _bbox_value(
    value: object,
    page: PageGeometry,
    field: str,
) -> list[float] | None:
    payload = _json_value(value, field)
    bbox = validate_bbox_within_page(payload, page)
    if bbox is None:
        return None
    return [bbox.left, bbox.bottom, bbox.right, bbox.top]


def _plain_rows(
    connection: sqlite3.Connection,
    query: str,
    columns: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {column: row[index] for index, column in enumerate(columns)}
        for row in connection.execute(query).fetchall()
    )


def _source_snapshot(connection: sqlite3.Connection) -> EvidenceSnapshot:
    documents = _plain_rows(
        connection,
        "SELECT id, title FROM documents ORDER BY id",
        ("id", "title"),
    )
    revisions = _plain_rows(
        connection,
        """
        SELECT id, document_id, source_hash, byte_size, page_count
        FROM revisions ORDER BY id
        """,
        ("id", "document_id", "source_hash", "byte_size", "page_count"),
    )
    pages = _plain_rows(
        connection,
        """
        SELECT id, revision_id, page_number, width, height
        FROM pages ORDER BY id
        """,
        ("id", "revision_id", "page_number", "width", "height"),
    )
    page_by_id = {
        str(row["id"]): PageGeometry(
            page_id=str(row["id"]),
            revision_id=str(row["revision_id"]),
            page_number=int(row["page_number"]),
            width=float(row["width"]),
            height=float(row["height"]),
        )
        for row in pages
    }
    page_by_revision_number = {
        (page.revision_id, page.page_number): page for page in page_by_id.values()
    }

    elements: list[dict[str, Any]] = []
    for row in connection.execute(
        """
        SELECT id, revision_id, page_id, page_number, element_type, raw_json,
               raw_text, normalized_text, raw_payload_hash, bbox_json,
               parser_order
        FROM elements ORDER BY id
        """
    ):
        page = page_by_id.get(str(row["page_id"]))
        if page is None:
            raise ValueError(f"PAGE_REFERENCE_NOT_FOUND: {row['page_id']}")
        if (
            str(row["revision_id"]) != page.revision_id
            or int(row["page_number"]) != page.page_number
        ):
            raise ValueError(f"PAGE_REFERENCE_MISMATCH: {row['id']}")
        elements.append(
            {
                "id": row["id"],
                "page_id": page.page_id,
                "element_type": row["element_type"],
                "raw_json": _json_value(row["raw_json"], "elements.raw_json"),
                "raw_text": row["raw_text"],
                "normalized_text": row["normalized_text"],
                "raw_payload_hash": row["raw_payload_hash"],
                "bbox": _bbox_value(row["bbox_json"], page, "elements.bbox_json"),
                "parser_order": row["parser_order"],
            }
        )

    clauses = _plain_rows(
        connection,
        """
        SELECT id, revision_id, title, raw_text, normalized_text, review_status
        FROM clauses ORDER BY id
        """,
        (
            "id",
            "revision_id",
            "title",
            "raw_text",
            "normalized_text",
            "review_status",
        ),
    )

    tables: list[dict[str, Any]] = []
    for row in connection.execute(
        """
        SELECT id, revision_id, page_number, bbox_json, raw_json,
               normalized_json
        FROM tables ORDER BY id
        """
    ):
        key = (str(row["revision_id"]), int(row["page_number"]))
        page = page_by_revision_number.get(key)
        if page is None:
            raise ValueError(
                f"PAGE_REFERENCE_NOT_FOUND: {key[0]} page {key[1]}"
            )
        tables.append(
            {
                "id": row["id"],
                "page_id": page.page_id,
                "bbox": _bbox_value(row["bbox_json"], page, "tables.bbox_json"),
                "raw_json": _json_value(row["raw_json"], "tables.raw_json"),
                "normalized_json": _json_value(
                    row["normalized_json"], "tables.normalized_json"
                ),
            }
        )

    visuals: list[dict[str, Any]] = []
    for row in connection.execute(
        """
        SELECT id, revision_id, page_number, kind, relative_path, sha256,
               bbox_json, duplicate_group
        FROM visuals ORDER BY id
        """
    ):
        key = (str(row["revision_id"]), int(row["page_number"]))
        page = page_by_revision_number.get(key)
        if page is None:
            raise ValueError(
                f"PAGE_REFERENCE_NOT_FOUND: {key[0]} page {key[1]}"
            )
        visuals.append(
            {
                "id": row["id"],
                "page_id": page.page_id,
                "kind": row["kind"],
                "relative_path": row["relative_path"],
                "sha256": row["sha256"],
                "bbox": _bbox_value(row["bbox_json"], page, "visuals.bbox_json"),
                "duplicate_group": row["duplicate_group"],
            }
        )

    links = _plain_rows(
        connection,
        """
        SELECT id, source_id, target_id, relation_type
        FROM links ORDER BY id
        """,
        ("id", "source_id", "target_id", "relation_type"),
    )
    review_flags = _plain_rows(
        connection,
        """
        SELECT id, evidence_id, code, status, detail
        FROM review_flags ORDER BY id
        """,
        ("id", "evidence_id", "code", "status", "detail"),
    )
    return EvidenceSnapshot(
        documents=documents,
        revisions=revisions,
        pages=pages,
        elements=tuple(elements),
        clauses=clauses,
        tables=tuple(tables),
        visuals=tuple(visuals),
        links=links,
        review_flags=review_flags,
    )


def _require_absent(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)


def _write_create_only(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def migrate_v1_to_v2(source: Path, output: Path) -> MigrationReport:
    """Create a validated v2 copy while leaving the v1 source unchanged."""
    source_path = source.resolve()
    output_path = output.resolve(strict=False)
    report_path = output_path.with_name(f"{output_path.name}.migration-report.json")
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    report_temporary_path = report_path.with_name(f".{report_path.name}.tmp")

    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if source_path == output_path:
        raise ValueError("source and output database paths must differ")
    _require_absent(output_path)
    _require_absent(report_path)
    generated_paths = {temporary_path, report_temporary_path}
    if source_path in generated_paths:
        raise ValueError("source path conflicts with migration temporary path")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _require_absent(temporary_path)
    _require_absent(report_temporary_path)

    source_sha256 = _sha256_file(source_path)
    source_connection = _read_only_connection(source_path)
    output_created = False
    report_created = False
    try:
        source_version = detect_schema_version(source_connection)
        if source_version != 1:
            raise ValueError(
                f"source database must use schema version 1, found {source_version}"
            )
        logical_hash = compute_logical_snapshot_hash(source_connection)
        snapshot = _source_snapshot(source_connection)

        with EvidenceStore(temporary_path, create=True) as store:
            ingest_snapshot(store, snapshot)
            connection = store.require_connection()
            physical_snapshot_hash = compute_snapshot_hash(store)
            connection.execute(
                """
                INSERT INTO snapshot_meta(key, value)
                VALUES('database_snapshot_hash', ?)
                """,
                (physical_snapshot_hash,),
            )
            connection.commit()
            build_fts_index(connection)
            migrated_logical_hash = compute_logical_snapshot_hash(connection)
            if migrated_logical_hash != logical_hash:
                raise ValueError("MIGRATION_LOGICAL_HASH_MISMATCH")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise ValueError("migration integrity_check failed")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("migration foreign_key_check failed")
            counts = snapshot_counts(store)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        report_temporary_path.unlink(missing_ok=True)
        raise
    finally:
        source_connection.close()

    if _sha256_file(source_path) != source_sha256:
        temporary_path.unlink(missing_ok=True)
        raise ValueError("source database changed during migration")

    output_sha256 = _sha256_file(temporary_path)
    report = MigrationReport(
        source_db=source_path,
        output_db=output_path,
        report_path=report_path,
        source_schema_version=1,
        output_schema_version=SCHEMA_VERSION,
        source_sha256=source_sha256,
        output_sha256=output_sha256,
        logical_snapshot_hash=logical_hash,
        counts=counts,
    )
    try:
        _write_create_only(
            report_temporary_path,
            dump_bytes(migration_report_document(report)),
        )
        temporary_path.replace(output_path)
        output_created = True
        report_temporary_path.replace(report_path)
        report_created = True
    except BaseException:
        if output_created:
            output_path.unlink(missing_ok=True)
        if report_created:
            report_path.unlink(missing_ok=True)
        temporary_path.unlink(missing_ok=True)
        report_temporary_path.unlink(missing_ok=True)
        raise
    return report
