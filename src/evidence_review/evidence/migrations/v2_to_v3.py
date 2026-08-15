"""Copy-on-write migration from evidence schema v2 to schema v3."""

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
    """Deterministic result of one successful v2-to-v3 migration."""

    source_db: Path
    output_db: Path
    report_path: Path
    source_schema_version: int
    output_schema_version: int
    source_sha256: str
    output_sha256: str
    logical_snapshot_hash: str
    page_count: int


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
        "page_count": report.page_count,
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


def _require_absent(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)


def migrate_v2_to_v3(source: Path, output: Path) -> MigrationReport:
    """Create a v3 copy while leaving the v2 source immutable."""
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
        if source_version != 2:
            raise ValueError(
                f"source database must use schema version 2, found {source_version}"
            )
        logical_hash = compute_logical_snapshot_hash(source_connection)
        source_page_count = int(
            source_connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        )
    finally:
        source_connection.close()

    try:
        shutil.copyfile(source_path, temporary_path)
        connection = sqlite3.connect(temporary_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "ALTER TABLE pages ADD COLUMN origin_x REAL NOT NULL DEFAULT 0"
        )
        connection.execute(
            "ALTER TABLE pages ADD COLUMN origin_y REAL NOT NULL DEFAULT 0"
        )
        connection.execute(
            "ALTER TABLE pages ADD COLUMN rotation INTEGER NOT NULL DEFAULT 0 "
            "CHECK(rotation IN (0,90,180,270))"
        )
        connection.execute(
            "ALTER TABLE pages ADD COLUMN box_kind TEXT NOT NULL DEFAULT 'MEDIA_BOX' "
            "CHECK(box_kind IN ('CROP_BOX','MEDIA_BOX'))"
        )
        connection.execute(
            "UPDATE schema_meta SET value = '3' WHERE key = 'schema_version'"
        )
        connection.commit()
        if detect_schema_version(connection) != 3:
            raise ValueError("MIGRATION_SCHEMA_VERSION_MISMATCH")
        if int(connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0]) != source_page_count:
            raise ValueError("MIGRATION_PAGE_COUNT_MISMATCH")
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("migration integrity_check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("migration foreign_key_check failed")
        connection.close()
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise

    if _sha256_file(source_path) != source_sha256:
        temporary_path.unlink(missing_ok=True)
        raise ValueError("source database changed during migration")

    output_sha256 = _sha256_file(temporary_path)
    report = MigrationReport(
        source_db=source_path,
        output_db=output_path,
        report_path=report_path,
        source_schema_version=2,
        output_schema_version=3,
        source_sha256=source_sha256,
        output_sha256=output_sha256,
        logical_snapshot_hash=logical_hash,
        page_count=source_page_count,
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
