"""Read-only planning for explicit legacy document lineage migrations."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from evidence_review.canonical_json import dump_bytes
from evidence_review.evidence.lineage_contract import (
    DocumentLineageMapping,
    LegacyLineageManifest,
    RevisionMapping,
)

PlanStatus: TypeAlias = Literal["READY", "BLOCKED"]

_EXPECTED_USER_TABLES = {
    "schema_meta",
    "documents",
    "revisions",
    "pages",
    "elements",
    "clauses",
    "tables",
    "visuals",
    "links",
    "review_flags",
    "snapshot_meta",
    "retrieval_records",
    "retrieval_meta",
    "evidence_fts",
}


@dataclass(frozen=True, slots=True, order=True)
class UnresolvedLineageItem:
    """One deterministic reason why a lineage migration cannot proceed."""

    code: str
    legacy_id: str
    canonical_id: str
    detail: str


@dataclass(frozen=True, slots=True, order=True)
class EntityMapping:
    """One proven equivalent legacy row and canonical row."""

    table: str
    legacy_id: str
    canonical_id: str


@dataclass(frozen=True, slots=True)
class LegacyLineagePlan:
    """Complete read-only plan or a fail-closed unresolved result."""

    status: PlanStatus
    entity_mappings: tuple[EntityMapping, ...]
    unresolved: tuple[UnresolvedLineageItem, ...]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(value: object) -> str:
    return hashlib.sha256(dump_bytes(value)).hexdigest()


def _blocked(
    code: str,
    *,
    legacy_id: str = "",
    canonical_id: str = "",
    detail: str = "",
) -> LegacyLineagePlan:
    return LegacyLineagePlan(
        status="BLOCKED",
        entity_mappings=(),
        unresolved=(
            UnresolvedLineageItem(
                code=code,
                legacy_id=legacy_id,
                canonical_id=canonical_id,
                detail=detail,
            ),
        ),
    )


def _final_plan(
    mappings: Iterable[EntityMapping],
    unresolved: Iterable[UnresolvedLineageItem],
) -> LegacyLineagePlan:
    sorted_mappings = tuple(
        sorted(
            set(mappings),
            key=lambda item: (item.table, item.legacy_id, item.canonical_id),
        )
    )
    sorted_unresolved = tuple(
        sorted(
            set(unresolved),
            key=lambda item: (
                item.code,
                item.legacy_id,
                item.canonical_id,
                item.detail,
            ),
        )
    )
    return LegacyLineagePlan(
        status="BLOCKED" if sorted_unresolved else "READY",
        entity_mappings=sorted_mappings,
        unresolved=sorted_unresolved,
    )


def _read_only_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _user_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    }


def _schema_is_supported(connection: sqlite3.Connection) -> bool:
    try:
        row = connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.Error:
        return False
    if row is None or str(row[0]) not in {"2", "3"}:
        return False
    tables = _user_tables(connection)
    unexpected = {
        table
        for table in tables
        if table not in _EXPECTED_USER_TABLES
        and not table.startswith("evidence_fts_")
    }
    missing = _EXPECTED_USER_TABLES - tables
    return not unexpected and not missing


def _source_integrity_error(connection: sqlite3.Connection) -> str | None:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    if row is None or row[0] != "ok":
        return "integrity_check did not return ok"
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        return f"foreign_key_check returned {len(violations)} row(s)"
    return None


def _row_by_id(
    connection: sqlite3.Connection,
    table: str,
    row_id: str,
) -> sqlite3.Row | None:
    query = f"SELECT * FROM {table} WHERE id = ?"  # noqa: S608
    row: sqlite3.Row | None = connection.execute(query, (row_id,)).fetchone()
    return row


def _json_text(value: object, field: str) -> object:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must contain JSON text or null")
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"{field} contains invalid JSON") from error


def _document_payload(row: sqlite3.Row) -> dict[str, object]:
    return {"title": row["title"]}


def _element_payload(row: sqlite3.Row) -> dict[str, object]:
    return {
        "element_type": row["element_type"],
        "raw_json": _json_text(row["raw_json"], "elements.raw_json"),
        "raw_text": row["raw_text"],
        "normalized_text": row["normalized_text"],
        "raw_payload_hash": row["raw_payload_hash"],
        "bbox": _json_text(row["bbox_json"], "elements.bbox_json"),
        "parser_order": row["parser_order"],
    }


def _clause_payload(row: sqlite3.Row) -> dict[str, object]:
    return {
        "title": row["title"],
        "raw_text": row["raw_text"],
        "normalized_text": row["normalized_text"],
        "review_status": row["review_status"],
    }


def _clause_base_payload(row: sqlite3.Row) -> dict[str, object]:
    return {
        "title": row["title"],
        "raw_text": row["raw_text"],
    }


def _table_payload(row: sqlite3.Row) -> dict[str, object]:
    return {
        "bbox": _json_text(row["bbox_json"], "tables.bbox_json"),
        "raw_json": _json_text(row["raw_json"], "tables.raw_json"),
        "normalized_json": _json_text(
            row["normalized_json"],
            "tables.normalized_json",
        ),
    }


def _visual_payload(row: sqlite3.Row) -> dict[str, object]:
    return {
        "kind": row["kind"],
        "relative_path": row["relative_path"],
        "sha256": row["sha256"],
        "bbox": _json_text(row["bbox_json"], "visuals.bbox_json"),
        "duplicate_group": row["duplicate_group"],
    }


def _rows_for_parent(
    connection: sqlite3.Connection,
    table: str,
    parent_column: str,
    parent_id: str,
) -> tuple[sqlite3.Row, ...]:
    query = (
        f"SELECT * FROM {table} "
        f"WHERE {parent_column} = ? ORDER BY id"  # noqa: S608
    )
    return tuple(connection.execute(query, (parent_id,)).fetchall())


def _match_payload_rows(
    *,
    table: str,
    legacy_rows: Sequence[sqlite3.Row],
    canonical_rows: Sequence[sqlite3.Row],
    payload: Callable[[sqlite3.Row], object],
    missing_code: str = "EVIDENCE_COUNTERPART_MISSING",
    ambiguous_code: str = "EVIDENCE_COUNTERPART_AMBIGUOUS",
) -> tuple[list[EntityMapping], list[UnresolvedLineageItem]]:
    canonical_by_fingerprint: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in canonical_rows:
        canonical_by_fingerprint[_fingerprint(payload(row))].append(row)

    mappings: list[EntityMapping] = []
    unresolved: list[UnresolvedLineageItem] = []
    used_canonical: set[str] = set()
    for legacy in legacy_rows:
        legacy_id = str(legacy["id"])
        candidates = [
            row
            for row in canonical_by_fingerprint[_fingerprint(payload(legacy))]
            if str(row["id"]) not in used_canonical
        ]
        if not candidates:
            unresolved.append(
                UnresolvedLineageItem(
                    code=missing_code,
                    legacy_id=legacy_id,
                    canonical_id="",
                    detail=f"{table} payload has no canonical counterpart",
                )
            )
            continue
        if len(candidates) != 1:
            unresolved.append(
                UnresolvedLineageItem(
                    code=ambiguous_code,
                    legacy_id=legacy_id,
                    canonical_id="",
                    detail=(
                        f"{table} payload has {len(candidates)} "
                        "canonical counterparts"
                    ),
                )
            )
            continue
        canonical_id = str(candidates[0]["id"])
        used_canonical.add(canonical_id)
        mappings.append(
            EntityMapping(
                table=table,
                legacy_id=legacy_id,
                canonical_id=canonical_id,
            )
        )
    return mappings, unresolved


def _match_clauses(
    legacy_rows: Sequence[sqlite3.Row],
    canonical_rows: Sequence[sqlite3.Row],
) -> tuple[list[EntityMapping], list[UnresolvedLineageItem]]:
    mappings, unresolved = _match_payload_rows(
        table="clauses",
        legacy_rows=legacy_rows,
        canonical_rows=canonical_rows,
        payload=_clause_payload,
    )
    mapped_legacy = {item.legacy_id for item in mappings}
    unresolved_legacy = {item.legacy_id for item in unresolved}
    canonical_by_base: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in canonical_rows:
        canonical_by_base[_fingerprint(_clause_base_payload(row))].append(row)

    replacement: list[UnresolvedLineageItem] = []
    for legacy in legacy_rows:
        legacy_id = str(legacy["id"])
        if legacy_id in mapped_legacy or legacy_id not in unresolved_legacy:
            continue
        candidates = canonical_by_base[_fingerprint(_clause_base_payload(legacy))]
        if len(candidates) == 1 and (
            legacy["normalized_text"] != candidates[0]["normalized_text"]
            or legacy["review_status"] != candidates[0]["review_status"]
        ):
            replacement.append(
                UnresolvedLineageItem(
                    code="REVIEWED_VALUE_CONFLICT",
                    legacy_id=legacy_id,
                    canonical_id=str(candidates[0]["id"]),
                    detail="review_status or normalized_text differs",
                )
            )

    replaced_ids = {item.legacy_id for item in replacement}
    unresolved = [
        item for item in unresolved if item.legacy_id not in replaced_ids
    ]
    unresolved.extend(replacement)
    return mappings, unresolved


def _revision_rows(
    connection: sqlite3.Connection,
    revision: RevisionMapping,
) -> tuple[sqlite3.Row | None, sqlite3.Row | None]:
    legacy = _row_by_id(connection, "revisions", revision.legacy_revision_id)
    canonical = _row_by_id(
        connection,
        "revisions",
        revision.canonical_revision_id,
    )
    return legacy, canonical


def _plan_revision(
    connection: sqlite3.Connection,
    document_mapping: DocumentLineageMapping,
    revision_mapping: RevisionMapping,
    mappings: list[EntityMapping],
    unresolved: list[UnresolvedLineageItem],
) -> dict[str, str]:
    legacy, canonical = _revision_rows(connection, revision_mapping)
    if legacy is None or canonical is None:
        unresolved.append(
            UnresolvedLineageItem(
                code="REVISION_NOT_FOUND",
                legacy_id=revision_mapping.legacy_revision_id,
                canonical_id=revision_mapping.canonical_revision_id,
                detail="declared legacy or canonical revision does not exist",
            )
        )
        return {}
    if (
        legacy["document_id"] != document_mapping.legacy_document_id
        or canonical["document_id"] != document_mapping.canonical_document_id
    ):
        unresolved.append(
            UnresolvedLineageItem(
                code="REVISION_OWNERSHIP_MISMATCH",
                legacy_id=revision_mapping.legacy_revision_id,
                canonical_id=revision_mapping.canonical_revision_id,
                detail="revision does not belong to its declared document",
            )
        )
        return {}
    if (
        legacy["source_hash"] != document_mapping.source_sha256
        or canonical["source_hash"] != document_mapping.source_sha256
    ):
        unresolved.append(
            UnresolvedLineageItem(
                code="REVISION_SOURCE_HASH_MISMATCH",
                legacy_id=revision_mapping.legacy_revision_id,
                canonical_id=revision_mapping.canonical_revision_id,
                detail="revision source hash differs from reviewed mapping",
            )
        )
        return {}
    if (
        legacy["byte_size"] != canonical["byte_size"]
        or legacy["page_count"] != canonical["page_count"]
    ):
        unresolved.append(
            UnresolvedLineageItem(
                code="REVISION_METADATA_MISMATCH",
                legacy_id=revision_mapping.legacy_revision_id,
                canonical_id=revision_mapping.canonical_revision_id,
                detail="byte_size or page_count differs",
            )
        )
        return {}

    mappings.append(
        EntityMapping(
            table="revisions",
            legacy_id=revision_mapping.legacy_revision_id,
            canonical_id=revision_mapping.canonical_revision_id,
        )
    )

    legacy_pages = {
        int(row["page_number"]): row
        for row in connection.execute(
            "SELECT * FROM pages WHERE revision_id = ? ORDER BY page_number",
            (revision_mapping.legacy_revision_id,),
        )
    }
    canonical_pages = {
        int(row["page_number"]): row
        for row in connection.execute(
            "SELECT * FROM pages WHERE revision_id = ? ORDER BY page_number",
            (revision_mapping.canonical_revision_id,),
        )
    }
    if set(legacy_pages) != set(canonical_pages):
        unresolved.append(
            UnresolvedLineageItem(
                code="PAGE_SET_MISMATCH",
                legacy_id=revision_mapping.legacy_revision_id,
                canonical_id=revision_mapping.canonical_revision_id,
                detail="page number sets differ",
            )
        )
        return {}

    id_map: dict[str, str] = {
        revision_mapping.legacy_revision_id: revision_mapping.canonical_revision_id
    }
    for page_number in sorted(legacy_pages):
        legacy_page = legacy_pages[page_number]
        canonical_page = canonical_pages[page_number]
        if (
            legacy_page["width"] != canonical_page["width"]
            or legacy_page["height"] != canonical_page["height"]
        ):
            unresolved.append(
                UnresolvedLineageItem(
                    code="PAGE_GEOMETRY_MISMATCH",
                    legacy_id=str(legacy_page["id"]),
                    canonical_id=str(canonical_page["id"]),
                    detail="page geometry differs",
                )
            )
            continue
        legacy_page_id = str(legacy_page["id"])
        canonical_page_id = str(canonical_page["id"])
        id_map[legacy_page_id] = canonical_page_id
        mappings.append(
            EntityMapping(
                table="pages",
                legacy_id=legacy_page_id,
                canonical_id=canonical_page_id,
            )
        )
        for table, payload in (
            ("elements", _element_payload),
            ("tables", _table_payload),
            ("visuals", _visual_payload),
        ):
            entity_mappings, entity_unresolved = _match_payload_rows(
                table=table,
                legacy_rows=_rows_for_parent(
                    connection,
                    table,
                    "page_id",
                    legacy_page_id,
                ),
                canonical_rows=_rows_for_parent(
                    connection,
                    table,
                    "page_id",
                    canonical_page_id,
                ),
                payload=payload,
            )
            mappings.extend(entity_mappings)
            unresolved.extend(entity_unresolved)
            id_map.update(
                {item.legacy_id: item.canonical_id for item in entity_mappings}
            )

    clause_mappings, clause_unresolved = _match_clauses(
        _rows_for_parent(
            connection,
            "clauses",
            "revision_id",
            revision_mapping.legacy_revision_id,
        ),
        _rows_for_parent(
            connection,
            "clauses",
            "revision_id",
            revision_mapping.canonical_revision_id,
        ),
    )
    mappings.extend(clause_mappings)
    unresolved.extend(clause_unresolved)
    id_map.update({item.legacy_id: item.canonical_id for item in clause_mappings})
    return id_map


def _match_links(
    connection: sqlite3.Connection,
    id_map: Mapping[str, str],
) -> tuple[list[EntityMapping], list[UnresolvedLineageItem]]:
    mappings: list[EntityMapping] = []
    unresolved: list[UnresolvedLineageItem] = []
    legacy_ids = set(id_map)
    rows = connection.execute("SELECT * FROM links ORDER BY id").fetchall()
    canonical_index: dict[tuple[str, str, str], list[sqlite3.Row]] = (
        defaultdict(list)
    )
    for row in rows:
        canonical_index[
            (
                str(row["source_id"]),
                str(row["target_id"]),
                str(row["relation_type"]),
            )
        ].append(row)
    for row in rows:
        source_id = str(row["source_id"])
        target_id = str(row["target_id"])
        if source_id not in legacy_ids and target_id not in legacy_ids:
            continue
        key = (
            id_map.get(source_id, source_id),
            id_map.get(target_id, target_id),
            str(row["relation_type"]),
        )
        candidates = canonical_index.get(key, [])
        if len(candidates) != 1:
            unresolved.append(
                UnresolvedLineageItem(
                    code="LINK_COUNTERPART_MISSING",
                    legacy_id=str(row["id"]),
                    canonical_id="",
                    detail="mapped link counterpart is missing or ambiguous",
                )
            )
            continue
        mappings.append(
            EntityMapping(
                table="links",
                legacy_id=str(row["id"]),
                canonical_id=str(candidates[0]["id"]),
            )
        )
    return mappings, unresolved


def _match_review_flags(
    connection: sqlite3.Connection,
    id_map: Mapping[str, str],
) -> tuple[list[EntityMapping], list[UnresolvedLineageItem]]:
    mappings: list[EntityMapping] = []
    unresolved: list[UnresolvedLineageItem] = []
    rows = connection.execute("SELECT * FROM review_flags ORDER BY id").fetchall()
    canonical_index: dict[tuple[object, ...], list[sqlite3.Row]] = (
        defaultdict(list)
    )
    for row in rows:
        canonical_index[
            (
                row["evidence_id"],
                row["code"],
                row["status"],
                row["detail"],
            )
        ].append(row)
    for row in rows:
        evidence_id = str(row["evidence_id"])
        if evidence_id not in id_map:
            continue
        key = (
            id_map[evidence_id],
            row["code"],
            row["status"],
            row["detail"],
        )
        candidates = canonical_index.get(key, [])
        if len(candidates) != 1:
            unresolved.append(
                UnresolvedLineageItem(
                    code="REVIEW_FLAG_COUNTERPART_MISSING",
                    legacy_id=str(row["id"]),
                    canonical_id="",
                    detail=(
                        "mapped review flag counterpart is missing or ambiguous"
                    ),
                )
            )
            continue
        mappings.append(
            EntityMapping(
                table="review_flags",
                legacy_id=str(row["id"]),
                canonical_id=str(candidates[0]["id"]),
            )
        )
    return mappings, unresolved


def _retrieval_payload(
    row: sqlite3.Row,
    *,
    document_id: str,
    revision_id: str,
    page_id: str,
) -> dict[str, object]:
    return {
        "evidence_type": row["evidence_type"],
        "document_id": document_id,
        "revision_id": revision_id,
        "page_id": page_id,
        "page_number": row["page_number"],
        "bbox": _json_text(
            row["bbox_json"],
            "retrieval_records.bbox_json",
        ),
        "source_hash": row["source_hash"],
        "title": row["title"],
        "raw_text": row["raw_text"],
        "normalized_text": row["normalized_text"],
    }


def _match_retrieval_records(
    connection: sqlite3.Connection,
    id_map: Mapping[str, str],
    legacy_document_ids: set[str],
) -> tuple[list[EntityMapping], list[UnresolvedLineageItem]]:
    rows = connection.execute(
        "SELECT * FROM retrieval_records ORDER BY evidence_id"
    ).fetchall()
    canonical_index: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        payload = _retrieval_payload(
            row,
            document_id=str(row["document_id"]),
            revision_id=str(row["revision_id"]),
            page_id=str(row["page_id"]),
        )
        canonical_index[_fingerprint(payload)].append(row)

    mappings: list[EntityMapping] = []
    unresolved: list[UnresolvedLineageItem] = []
    for row in rows:
        document_id = str(row["document_id"])
        revision_id = str(row["revision_id"])
        page_id = str(row["page_id"])
        if document_id not in legacy_document_ids:
            continue
        payload = _retrieval_payload(
            row,
            document_id=id_map.get(document_id, document_id),
            revision_id=id_map.get(revision_id, revision_id),
            page_id=id_map.get(page_id, page_id),
        )
        candidates = canonical_index.get(_fingerprint(payload), [])
        if len(candidates) != 1:
            unresolved.append(
                UnresolvedLineageItem(
                    code="RETRIEVAL_COUNTERPART_MISSING",
                    legacy_id=str(row["evidence_id"]),
                    canonical_id="",
                    detail=(
                        "mapped retrieval counterpart is missing or ambiguous"
                    ),
                )
            )
            continue
        mappings.append(
            EntityMapping(
                table="retrieval_records",
                legacy_id=str(row["evidence_id"]),
                canonical_id=str(candidates[0]["evidence_id"]),
            )
        )
    return mappings, unresolved


def plan_legacy_lineage_migration(
    source_database: Path,
    manifest: LegacyLineageManifest,
) -> LegacyLineagePlan:
    """Return a deterministic, read-only plan for graph-equivalent aliases."""

    source_path = source_database.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    actual_hash = _sha256_file(source_path)
    if actual_hash != manifest.source_database_sha256:
        return _blocked(
            "SOURCE_DATABASE_HASH_MISMATCH",
            detail="source database bytes do not match the reviewed manifest",
        )

    connection = _read_only_connection(source_path)
    try:
        if not _schema_is_supported(connection):
            return _blocked(
                "SOURCE_SCHEMA_VERSION_UNSUPPORTED",
                detail=(
                    "source must contain only the exact evidence schema "
                    "version 2 tables"
                ),
            )
        integrity_error = _source_integrity_error(connection)
        if integrity_error is not None:
            return _blocked("SOURCE_INTEGRITY_FAILED", detail=integrity_error)

        mappings: list[EntityMapping] = []
        unresolved: list[UnresolvedLineageItem] = []
        id_map: dict[str, str] = {}
        legacy_document_ids = {
            mapping.legacy_document_id for mapping in manifest.mappings
        }
        for document_mapping in manifest.mappings:
            legacy_document = _row_by_id(
                connection,
                "documents",
                document_mapping.legacy_document_id,
            )
            canonical_document = _row_by_id(
                connection,
                "documents",
                document_mapping.canonical_document_id,
            )
            if legacy_document is None:
                unresolved.append(
                    UnresolvedLineageItem(
                        code="LEGACY_DOCUMENT_NOT_FOUND",
                        legacy_id=document_mapping.legacy_document_id,
                        canonical_id=document_mapping.canonical_document_id,
                        detail="declared legacy document does not exist",
                    )
                )
                continue
            if canonical_document is None:
                unresolved.append(
                    UnresolvedLineageItem(
                        code="CANONICAL_DOCUMENT_NOT_FOUND",
                        legacy_id=document_mapping.legacy_document_id,
                        canonical_id=document_mapping.canonical_document_id,
                        detail="declared canonical document does not exist",
                    )
                )
                continue
            if _document_payload(legacy_document) != _document_payload(
                canonical_document
            ):
                unresolved.append(
                    UnresolvedLineageItem(
                        code="DOCUMENT_METADATA_MISMATCH",
                        legacy_id=document_mapping.legacy_document_id,
                        canonical_id=document_mapping.canonical_document_id,
                        detail="document title differs",
                    )
                )
                continue
            mappings.append(
                EntityMapping(
                    table="documents",
                    legacy_id=document_mapping.legacy_document_id,
                    canonical_id=document_mapping.canonical_document_id,
                )
            )
            id_map[document_mapping.legacy_document_id] = (
                document_mapping.canonical_document_id
            )
            for revision_mapping in document_mapping.revision_mappings:
                revision_id_map = _plan_revision(
                    connection,
                    document_mapping,
                    revision_mapping,
                    mappings,
                    unresolved,
                )
                id_map.update(revision_id_map)

        # Structural and evidence conflicts make downstream relation checks
        # derivative and noisy. Stop at the highest valid comparison layer.
        if unresolved:
            return _final_plan(mappings, unresolved)

        link_mappings, link_unresolved = _match_links(connection, id_map)
        mappings.extend(link_mappings)
        unresolved.extend(link_unresolved)
        flag_mappings, flag_unresolved = _match_review_flags(
            connection,
            id_map,
        )
        mappings.extend(flag_mappings)
        unresolved.extend(flag_unresolved)
        retrieval_mappings, retrieval_unresolved = _match_retrieval_records(
            connection,
            id_map,
            legacy_document_ids,
        )
        mappings.extend(retrieval_mappings)
        unresolved.extend(retrieval_unresolved)
        return _final_plan(mappings, unresolved)
    except (json.JSONDecodeError, sqlite3.Error, ValueError) as error:
        return _blocked("SOURCE_INTEGRITY_FAILED", detail=str(error))
    finally:
        connection.close()
