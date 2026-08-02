from __future__ import annotations

import datetime
import hashlib
import sqlite3
from dataclasses import replace
from pathlib import Path

from ansim_review.evidence.lineage_contract import (
    DocumentLineageMapping,
    LegacyLineageManifest,
    RevisionMapping,
)
from ansim_review.evidence.lineage_graph import plan_legacy_lineage_migration
from ansim_review.evidence.store import EvidenceStore

LEGACY_DOCUMENT = "LAW3"
CANONICAL_DOCUMENT = "DOC-ACFD68E34043268C"
LEGACY_REVISION = "REV-LAW3-001"
CANONICAL_REVISION = "REV-DOC-001"
SOURCE_HASH = "b" * 64


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _insert_graph(connection: sqlite3.Connection, prefix: str, document_id: str) -> None:
    revision_id = LEGACY_REVISION if prefix == "L" else CANONICAL_REVISION
    page_id = f"PAGE-{prefix}-001"
    element_id = f"ELEMENT-{prefix}-001"
    clause_id = f"CLAUSE-{prefix}-001"
    table_id = f"TABLE-{prefix}-001"
    visual_id = f"VISUAL-{prefix}-001"
    link_id = f"LINK-{prefix}-001"
    flag_id = f"FLAG-{prefix}-001"
    retrieval_id = f"RETRIEVAL-{prefix}-001"

    connection.execute(
        "INSERT INTO documents(id, title) VALUES(?, ?)",
        (document_id, "Same source document"),
    )
    connection.execute(
        """
        INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
        VALUES(?, ?, ?, 100, 1)
        """,
        (revision_id, document_id, SOURCE_HASH),
    )
    connection.execute(
        """
        INSERT INTO pages(id, revision_id, page_number, width, height)
        VALUES(?, ?, 1, 595.0, 842.0)
        """,
        (page_id, revision_id),
    )
    connection.execute(
        """
        INSERT INTO elements(
            id, page_id, element_type, raw_json, raw_text, normalized_text,
            raw_payload_hash, bbox_json, parser_order
        ) VALUES(?, ?, 'text', '{"text":"same"}', 'same', 'same', ?,
                 '[1,2,3,4]', 0)
        """,
        (element_id, page_id, "c" * 64),
    )
    connection.execute(
        """
        INSERT INTO clauses(
            id, revision_id, title, raw_text, normalized_text, review_status
        ) VALUES(?, ?, 'Article 1', 'same clause', 'same clause', 'REVIEWED')
        """,
        (clause_id, revision_id),
    )
    connection.execute(
        """
        INSERT INTO tables(id, page_id, bbox_json, raw_json, normalized_json)
        VALUES(?, ?, '[10,20,30,40]', '{"rows":[["same"]]}',
               '{"rows":[["same"]]}')
        """,
        (table_id, page_id),
    )
    connection.execute(
        """
        INSERT INTO visuals(
            id, page_id, kind, relative_path, sha256, bbox_json, duplicate_group
        ) VALUES(?, ?, 'page_render', 'assets/page-1.png', ?,
                 '[0,0,595,842]', 'DUP-SAME')
        """,
        (visual_id, page_id, "d" * 64),
    )
    connection.execute(
        """
        INSERT INTO links(id, source_id, target_id, relation_type)
        VALUES(?, ?, ?, 'supports')
        """,
        (link_id, element_id, clause_id),
    )
    connection.execute(
        """
        INSERT INTO review_flags(id, evidence_id, code, status, detail)
        VALUES(?, ?, 'CHECKED', 'CLOSED', 'same detail')
        """,
        (flag_id, clause_id),
    )
    connection.execute(
        """
        INSERT INTO retrieval_records(
            evidence_id, evidence_type, document_id, revision_id, page_id,
            page_number, bbox_json, source_hash, title, raw_text, normalized_text
        ) VALUES(?, 'clause', ?, ?, ?, 1, '[1,2,3,4]', ?, 'Article 1',
                 'same clause', 'same clause')
        """,
        (retrieval_id, document_id, revision_id, page_id, SOURCE_HASH),
    )


def build_equivalent_graph(tmp_path: Path) -> tuple[Path, LegacyLineageManifest]:
    database = tmp_path / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        connection = store.require_connection()
        _insert_graph(connection, "L", LEGACY_DOCUMENT)
        _insert_graph(connection, "C", CANONICAL_DOCUMENT)
        connection.commit()
    manifest = LegacyLineageManifest(
        source_database_sha256=_sha256_file(database),
        reviewer_id="ksh",
        reviewed_at=datetime.datetime.fromisoformat("2026-08-02T16:49:00+09:00"),
        mappings=(
            DocumentLineageMapping(
                legacy_document_id=LEGACY_DOCUMENT,
                canonical_document_id=CANONICAL_DOCUMENT,
                source_sha256=SOURCE_HASH,
                reason="same immutable PDF registered under a legacy alias",
                revision_mappings=(
                    RevisionMapping(
                        legacy_revision_id=LEGACY_REVISION,
                        canonical_revision_id=CANONICAL_REVISION,
                    ),
                ),
            ),
        ),
    )
    return database, manifest


def _execute(database: Path, sql: str, parameters: tuple[object, ...] = ()) -> None:
    connection = sqlite3.connect(database)
    try:
        connection.execute(sql, parameters)
        connection.commit()
    finally:
        connection.close()


def _refreshed_manifest(
    database: Path,
    manifest: LegacyLineageManifest,
) -> LegacyLineageManifest:
    return replace(manifest, source_database_sha256=_sha256_file(database))


def test_equivalent_duplicate_graph_builds_ready_plan(tmp_path: Path) -> None:
    database, manifest = build_equivalent_graph(tmp_path)
    plan = plan_legacy_lineage_migration(database, manifest)

    assert plan.status == "READY"
    assert plan.unresolved == ()
    mapping_set = {
        (item.table, item.legacy_id, item.canonical_id)
        for item in plan.entity_mappings
    }
    assert {
        ("documents", LEGACY_DOCUMENT, CANONICAL_DOCUMENT),
        ("revisions", LEGACY_REVISION, CANONICAL_REVISION),
        ("pages", "PAGE-L-001", "PAGE-C-001"),
        ("elements", "ELEMENT-L-001", "ELEMENT-C-001"),
        ("clauses", "CLAUSE-L-001", "CLAUSE-C-001"),
        ("tables", "TABLE-L-001", "TABLE-C-001"),
        ("visuals", "VISUAL-L-001", "VISUAL-C-001"),
        ("links", "LINK-L-001", "LINK-C-001"),
        ("review_flags", "FLAG-L-001", "FLAG-C-001"),
        ("retrieval_records", "RETRIEVAL-L-001", "RETRIEVAL-C-001"),
    } <= mapping_set


def test_source_database_hash_mismatch_blocks_before_graph_use(tmp_path: Path) -> None:
    database, manifest = build_equivalent_graph(tmp_path)
    plan = plan_legacy_lineage_migration(
        database,
        replace(manifest, source_database_sha256="f" * 64),
    )

    assert plan.status == "BLOCKED"
    assert [item.code for item in plan.unresolved] == [
        "SOURCE_DATABASE_HASH_MISMATCH"
    ]
    assert plan.entity_mappings == ()


def test_element_payload_difference_blocks_plan(tmp_path: Path) -> None:
    database, manifest = build_equivalent_graph(tmp_path)
    _execute(
        database,
        "UPDATE elements SET normalized_text = 'different' WHERE id = 'ELEMENT-L-001'",
    )
    plan = plan_legacy_lineage_migration(
        database,
        _refreshed_manifest(database, manifest),
    )

    assert plan.status == "BLOCKED"
    assert "EVIDENCE_COUNTERPART_MISSING" in {
        item.code for item in plan.unresolved
    }


def test_reviewed_value_conflict_blocks_without_promotion(tmp_path: Path) -> None:
    database, manifest = build_equivalent_graph(tmp_path)
    _execute(
        database,
        """
        UPDATE clauses
        SET normalized_text = 'human-only value'
        WHERE id = 'CLAUSE-L-001'
        """,
    )
    plan = plan_legacy_lineage_migration(
        database,
        _refreshed_manifest(database, manifest),
    )

    assert plan.status == "BLOCKED"
    assert "REVIEWED_VALUE_CONFLICT" in {item.code for item in plan.unresolved}


def test_page_geometry_difference_blocks_plan(tmp_path: Path) -> None:
    database, manifest = build_equivalent_graph(tmp_path)
    _execute(
        database,
        "UPDATE pages SET width = 600.0 WHERE id = 'PAGE-L-001'",
    )
    plan = plan_legacy_lineage_migration(
        database,
        _refreshed_manifest(database, manifest),
    )

    assert plan.status == "BLOCKED"
    assert [item.code for item in plan.unresolved] == [
        "PAGE_GEOMETRY_MISMATCH"
    ]


def test_revision_ownership_and_metadata_are_explicitly_verified(
    tmp_path: Path,
) -> None:
    database, manifest = build_equivalent_graph(tmp_path)
    _execute(
        database,
        "UPDATE revisions SET byte_size = 101 WHERE id = ?",
        (LEGACY_REVISION,),
    )
    plan = plan_legacy_lineage_migration(
        database,
        _refreshed_manifest(database, manifest),
    )
    assert "REVISION_METADATA_MISMATCH" in {
        item.code for item in plan.unresolved
    }


def test_missing_link_flag_and_retrieval_counterparts_block(tmp_path: Path) -> None:
    database, manifest = build_equivalent_graph(tmp_path)
    _execute(database, "DELETE FROM links WHERE id = 'LINK-C-001'")
    _execute(database, "DELETE FROM review_flags WHERE id = 'FLAG-C-001'")
    _execute(
        database,
        "DELETE FROM retrieval_records WHERE evidence_id = 'RETRIEVAL-C-001'",
    )
    plan = plan_legacy_lineage_migration(
        database,
        _refreshed_manifest(database, manifest),
    )

    assert plan.status == "BLOCKED"
    assert [item.code for item in plan.unresolved] == [
        "LINK_COUNTERPART_MISSING",
        "RETRIEVAL_COUNTERPART_MISSING",
        "REVIEW_FLAG_COUNTERPART_MISSING",
    ]


def test_unknown_user_table_blocks_preservation_claim(tmp_path: Path) -> None:
    database, manifest = build_equivalent_graph(tmp_path)
    _execute(database, "CREATE TABLE legacy_comments(id TEXT PRIMARY KEY) STRICT")
    plan = plan_legacy_lineage_migration(
        database,
        _refreshed_manifest(database, manifest),
    )

    assert plan.status == "BLOCKED"
    assert [item.code for item in plan.unresolved] == [
        "SOURCE_SCHEMA_VERSION_UNSUPPORTED"
    ]


def test_unresolved_items_and_entity_mappings_are_deterministic(tmp_path: Path) -> None:
    database, manifest = build_equivalent_graph(tmp_path)
    _execute(database, "DELETE FROM links WHERE id = 'LINK-C-001'")
    _execute(database, "DELETE FROM review_flags WHERE id = 'FLAG-C-001'")
    refreshed = _refreshed_manifest(database, manifest)

    first = plan_legacy_lineage_migration(database, refreshed)
    second = plan_legacy_lineage_migration(database, refreshed)

    assert first == second
    assert first.unresolved == tuple(
        sorted(
            first.unresolved,
            key=lambda item: (item.code, item.legacy_id, item.canonical_id),
        )
    )
