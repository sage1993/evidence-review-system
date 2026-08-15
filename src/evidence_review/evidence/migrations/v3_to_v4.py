"""Copy-on-write migration from evidence schema v3 to schema v4."""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.evidence.schema_version import detect_schema_version
from evidence_review.evidence.snapshot import compute_logical_snapshot_hash


@dataclass(frozen=True, slots=True)
class MigrationReport:
    """Deterministic result of one successful v3-to-v4 migration."""

    source_db: Path
    output_db: Path
    report_path: Path
    source_schema_version: int
    output_schema_version: int
    source_sha256: str
    output_sha256: str
    logical_snapshot_hash: str
    clause_count: int


def migration_report_document(report: MigrationReport) -> dict[str, object]:
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
        "clause_count": report.clause_count,
        "retrieval_rebuild_required": True,
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
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _require_absent(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)


def _upgrade_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE clause_retrieval_records (
            clause_id TEXT PRIMARY KEY REFERENCES clauses(id),
            document_id TEXT NOT NULL REFERENCES documents(id),
            revision_id TEXT NOT NULL REFERENCES revisions(id),
            title TEXT NOT NULL,
            chapter TEXT,
            section TEXT,
            clause_number TEXT,
            raw_text TEXT NOT NULL,
            normalized_text TEXT NOT NULL
        ) STRICT;

        CREATE VIRTUAL TABLE clause_fts USING fts5(
            clause_id UNINDEXED,
            title,
            chapter,
            section,
            clause_number,
            raw_text,
            normalized_text,
            tokenize = 'unicode61'
        );

        CREATE TABLE clause_evidence_links (
            clause_id TEXT NOT NULL REFERENCES clauses(id),
            evidence_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            PRIMARY KEY(clause_id, evidence_id, relation_type)
        ) STRICT;

        CREATE INDEX idx_clause_retrieval_source
            ON clause_retrieval_records(document_id, revision_id, clause_id);
        CREATE INDEX idx_clause_evidence_links_evidence
            ON clause_evidence_links(evidence_id, clause_id, relation_type);

        CREATE TRIGGER rebuild_clause_index_after_retrieval_publish
        AFTER INSERT ON retrieval_meta
        WHEN NEW.key = 'snapshot_hash'
        BEGIN
            DELETE FROM clause_fts;
            DELETE FROM clause_evidence_links;
            DELETE FROM clause_retrieval_records;

            INSERT INTO clause_retrieval_records(
                clause_id, document_id, revision_id, title, chapter, section,
                clause_number, raw_text, normalized_text
            )
            SELECT c.id, r.document_id, c.revision_id, c.title,
                   NULL, NULL, NULL,
                   COALESCE(c.raw_text, ''),
                   COALESCE(c.normalized_text, c.raw_text, '')
            FROM clauses c
            JOIN revisions r ON r.id = c.revision_id
            WHERE COALESCE(c.normalized_text, c.raw_text, '') <> ''
            ORDER BY c.id;

            INSERT INTO clause_fts(
                clause_id, title, chapter, section, clause_number, raw_text,
                normalized_text
            )
            SELECT clause_id, title, chapter, section, clause_number, raw_text,
                   normalized_text
            FROM clause_retrieval_records
            ORDER BY clause_id;

            INSERT OR IGNORE INTO clause_evidence_links(
                clause_id, evidence_id, relation_type
            )
            SELECT c.id, l.target_id, l.relation_type
            FROM clauses c
            JOIN links l ON l.source_id = c.id
            JOIN retrieval_records rr ON rr.evidence_id = l.target_id
            UNION
            SELECT c.id, l.source_id, l.relation_type
            FROM clauses c
            JOIN links l ON l.target_id = c.id
            JOIN retrieval_records rr ON rr.evidence_id = l.source_id;
        END;
        """
    )
    connection.execute("DELETE FROM retrieval_meta WHERE key = 'snapshot_hash'")
    connection.execute(
        "UPDATE schema_meta SET value = '4' WHERE key = 'schema_version'"
    )


def migrate_v3_to_v4(source: Path, output: Path) -> MigrationReport:
    """Create a v4 copy while leaving the v3 source immutable.

    The migration creates the clause semantic-index schema but intentionally leaves
    derived clause retrieval rows empty and invalidates retrieval freshness. A
    subsequent deterministic `build_fts_index` call must rebuild both evidence and
    clause indexes from the canonical snapshot.
    """
    source_path = source.resolve()
    output_path = output.resolve(strict=False)
    report_path = output_path.with_name(f"{output_path.name}.migration-report.json")
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")

    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if source_path == output_path:
        raise ValueError("source and output database paths must differ")
    _require_absent(output_path)
    _require_absent(report_path)
    _require_absent(temporary_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_sha256 = _sha256_file(source_path)
    source_connection = _read_only_connection(source_path)
    try:
        source_version = detect_schema_version(source_connection)
        if source_version != 3:
            raise ValueError(
                f"source database must use schema version 3, found {source_version}"
            )
        logical_hash = compute_logical_snapshot_hash(source_connection)
        source_clause_count = int(
            source_connection.execute("SELECT COUNT(*) FROM clauses").fetchone()[0]
        )
    finally:
        source_connection.close()

    connection: sqlite3.Connection | None = None
    try:
        shutil.copyfile(source_path, temporary_path)
        connection = sqlite3.connect(temporary_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        _upgrade_schema(connection)
        connection.commit()
        if detect_schema_version(connection) != 4:
            raise ValueError("MIGRATION_SCHEMA_VERSION_MISMATCH")
        if int(connection.execute("SELECT COUNT(*) FROM clauses").fetchone()[0]) != source_clause_count:
            raise ValueError("MIGRATION_CLAUSE_COUNT_MISMATCH")
        if connection.execute("SELECT COUNT(*) FROM clause_retrieval_records").fetchone() != (0,):
            raise ValueError("MIGRATION_DERIVED_INDEX_NOT_EMPTY")
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("migration integrity_check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("migration foreign_key_check failed")
    except BaseException:
        if connection is not None:
            connection.close()
        temporary_path.unlink(missing_ok=True)
        raise
    else:
        assert connection is not None
        connection.close()

    if _sha256_file(source_path) != source_sha256:
        temporary_path.unlink(missing_ok=True)
        raise ValueError("source database changed during migration")

    output_sha256 = _sha256_file(temporary_path)
    report = MigrationReport(
        source_db=source_path,
        output_db=output_path,
        report_path=report_path,
        source_schema_version=3,
        output_schema_version=4,
        source_sha256=source_sha256,
        output_sha256=output_sha256,
        logical_snapshot_hash=logical_hash,
        clause_count=source_clause_count,
    )
    report_temporary = report_path.with_name(f".{report_path.name}.tmp")
    try:
        _require_absent(report_temporary)
        with report_temporary.open("xb") as stream:
            stream.write(dump_bytes(migration_report_document(report)))
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(output_path)
        report_temporary.replace(report_path)
    except BaseException:
        output_path.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        temporary_path.unlink(missing_ok=True)
        report_temporary.unlink(missing_ok=True)
        raise
    return report
