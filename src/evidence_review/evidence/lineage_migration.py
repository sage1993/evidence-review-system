"""Copy-on-write application of explicit legacy document lineage plans."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.formats import (
    LEGACY_LINEAGE_ALIASES_FORMAT,
    LEGACY_LINEAGE_MIGRATION_REPORT_FORMAT,
)
from evidence_review.evidence.lineage_contract import (
    LegacyLineageManifest,
    decode_legacy_lineage_manifest,
)
from evidence_review.evidence.lineage_graph import (
    EntityMapping,
    LegacyLineagePlan,
    plan_legacy_lineage_migration,
)

_TABLE_KEYS: Mapping[str, str] = {
    "documents": "id",
    "revisions": "id",
    "pages": "id",
    "elements": "id",
    "clauses": "id",
    "tables": "id",
    "visuals": "id",
    "links": "id",
    "review_flags": "id",
    "retrieval_records": "evidence_id",
}
_DELETE_ORDER = (
    "retrieval_records",
    "links",
    "review_flags",
    "elements",
    "tables",
    "visuals",
    "clauses",
    "pages",
    "revisions",
    "documents",
)


@dataclass(frozen=True, slots=True)
class LegacyLineageMigrationResult:
    """Verified outputs of one successful copy-on-write migration."""

    output_database: Path
    aliases_path: Path
    report_path: Path
    output_sha256: str
    logical_lineage_digest: str
    removed_counts: Mapping[str, int]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_absent(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)


def _write_create_only(path: Path, payload: bytes) -> None:
    """Write one fsynced file without replacing any existing path."""

    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _load_manifest(path: Path) -> tuple[LegacyLineageManifest, bytes]:
    payload_bytes = path.read_bytes()
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError("lineage manifest must be UTF-8 JSON") from error
    return decode_legacy_lineage_manifest(payload), payload_bytes


def _artifact_paths(output: Path) -> tuple[Path, Path, Path, Path, Path]:
    aliases = output.with_name(f"{output.name}.legacy-lineage-aliases.json")
    report = output.with_name(
        f"{output.name}.legacy-lineage-migration-report.json"
    )
    temporary_output = output.with_name(f".{output.name}.lineage.tmp")
    temporary_aliases = aliases.with_name(f".{aliases.name}.tmp")
    temporary_report = report.with_name(f".{report.name}.tmp")
    return aliases, report, temporary_output, temporary_aliases, temporary_report


def _table_rows(
    connection: sqlite3.Connection,
    table: str,
    key: str,
) -> list[dict[str, Any]]:
    query = f"SELECT * FROM {table} ORDER BY {key}"  # noqa: S608
    cursor = connection.execute(query)
    columns = tuple(item[0] for item in cursor.description or ())
    return [
        {column: row[index] for index, column in enumerate(columns)}
        for row in cursor.fetchall()
    ]


def _logical_lineage_document(connection: sqlite3.Connection) -> dict[str, object]:
    return {
        "schema_version": 2,
        "tables": {
            table: _table_rows(connection, table, key)
            for table, key in _TABLE_KEYS.items()
        },
    }


def _logical_lineage_digest(connection: sqlite3.Connection) -> str:
    return _sha256_bytes(dump_bytes(_logical_lineage_document(connection)))


def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in _TABLE_KEYS:
        query = f"SELECT COUNT(*) FROM {table}"  # noqa: S608
        row = connection.execute(query).fetchone()
        counts[table] = 0 if row is None else int(row[0])
    return counts


def _group_mappings(plan: LegacyLineagePlan) -> dict[str, tuple[EntityMapping, ...]]:
    grouped: dict[str, list[EntityMapping]] = defaultdict(list)
    for mapping in plan.entity_mappings:
        grouped[mapping.table].append(mapping)
    return {
        table: tuple(sorted(items, key=lambda item: item.legacy_id))
        for table, items in grouped.items()
    }


def _delete_one(
    connection: sqlite3.Connection,
    table: str,
    key: str,
    row_id: str,
) -> None:
    query = f"DELETE FROM {table} WHERE {key} = ?"  # noqa: S608
    cursor = connection.execute(query, (row_id,))
    if cursor.rowcount != 1:
        raise ValueError(f"OUTPUT_VERIFICATION_FAILED: missing {table}:{row_id}")


def _delete_legacy_graph(
    connection: sqlite3.Connection,
    plan: LegacyLineagePlan,
) -> dict[str, int]:
    grouped = _group_mappings(plan)
    removed: Counter[str] = Counter()

    all_legacy_ids = sorted(
        {mapping.legacy_id for mapping in plan.entity_mappings}
    )
    for legacy_id in all_legacy_ids:
        connection.execute(
            "DELETE FROM evidence_fts WHERE evidence_id = ?",
            (legacy_id,),
        )

    derived_clause_tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "clause_retrieval_records" in derived_clause_tables:
        for clause_id in sorted(mapping.legacy_id for mapping in grouped.get("clauses", ())):
            connection.execute(
                "DELETE FROM clause_fts WHERE clause_id = ?",
                (clause_id,),
            )
            connection.execute(
                "DELETE FROM clause_evidence_links WHERE clause_id = ?",
                (clause_id,),
            )
            connection.execute(
                "DELETE FROM clause_retrieval_records WHERE clause_id = ?",
                (clause_id,),
            )

    for table in _DELETE_ORDER:
        key = _TABLE_KEYS[table]
        for mapping in grouped.get(table, ()):
            _delete_one(connection, table, key, mapping.legacy_id)
            removed[table] += 1
    return dict(sorted(removed.items()))


def _verify_mapping_state(
    connection: sqlite3.Connection,
    plan: LegacyLineagePlan,
) -> None:
    for mapping in plan.entity_mappings:
        key = _TABLE_KEYS[mapping.table]
        query = f"SELECT 1 FROM {mapping.table} WHERE {key} = ?"  # noqa: S608
        if connection.execute(query, (mapping.legacy_id,)).fetchone() is not None:
            raise ValueError(
                f"OUTPUT_VERIFICATION_FAILED: legacy row remains "
                f"{mapping.table}:{mapping.legacy_id}"
            )
        if connection.execute(query, (mapping.canonical_id,)).fetchone() is None:
            raise ValueError(
                f"OUTPUT_VERIFICATION_FAILED: canonical row missing "
                f"{mapping.table}:{mapping.canonical_id}"
            )


def _update_snapshot_metadata(
    connection: sqlite3.Connection,
    logical_digest: str,
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO snapshot_meta(key, value)
        VALUES('snapshot_hash', ?)
        """,
        (logical_digest,),
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO snapshot_meta(key, value)
        VALUES('database_snapshot_hash', ?)
        """,
        (logical_digest,),
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO retrieval_meta(key, value)
        VALUES('snapshot_hash', ?)
        """,
        (logical_digest,),
    )


def _verify_integrity(connection: sqlite3.Connection) -> None:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    if row is None or row[0] != "ok":
        raise ValueError("OUTPUT_VERIFICATION_FAILED: integrity_check")
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise ValueError(
            "OUTPUT_VERIFICATION_FAILED: foreign_key_check "
            f"returned {len(violations)} row(s)"
        )


def _alias_entries(manifest: LegacyLineageManifest) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for mapping in manifest.mappings:
        for revision in mapping.revision_mappings:
            entries.append(
                {
                    "legacy_document_id": mapping.legacy_document_id,
                    "canonical_document_id": mapping.canonical_document_id,
                    "source_sha256": mapping.source_sha256,
                    "legacy_revision_id": revision.legacy_revision_id,
                    "canonical_revision_id": revision.canonical_revision_id,
                    "reviewer_id": manifest.reviewer_id,
                    "reviewed_at": manifest.reviewed_at.isoformat(),
                    "reason": mapping.reason,
                }
            )
    return sorted(
        entries,
        key=lambda item: (
            str(item["legacy_document_id"]),
            str(item["legacy_revision_id"]),
        ),
    )


def _unresolved_document(plan: LegacyLineagePlan) -> list[dict[str, str]]:
    return [
        {
            "code": item.code,
            "legacy_id": item.legacy_id,
            "canonical_id": item.canonical_id,
            "detail": item.detail,
        }
        for item in plan.unresolved
    ]


def _report_body(
    *,
    source: Path,
    output: Path,
    source_sha256: str,
    output_sha256: str,
    manifest_sha256: str,
    manifest: LegacyLineageManifest,
    logical_digest: str,
    before_counts: Mapping[str, int],
    after_counts: Mapping[str, int],
    removed_counts: Mapping[str, int],
    plan: LegacyLineagePlan,
) -> dict[str, object]:
    return {
        "format": LEGACY_LINEAGE_MIGRATION_REPORT_FORMAT,
        "version": 1,
        "status": "MIGRATED",
        "source_database": {"file": source.name, "sha256": source_sha256},
        "output_database": {"file": output.name, "sha256": output_sha256},
        "manifest_sha256": manifest_sha256,
        "reviewer_id": manifest.reviewer_id,
        "reviewed_at": manifest.reviewed_at.isoformat(),
        "logical_lineage_digest": logical_digest,
        "mapping_count": len(manifest.mappings),
        "revision_mapping_count": sum(
            len(mapping.revision_mappings) for mapping in manifest.mappings
        ),
        "before_counts": dict(sorted(before_counts.items())),
        "after_counts": dict(sorted(after_counts.items())),
        "removed_counts": dict(sorted(removed_counts.items())),
        "preserved_counts": dict(
            sorted(Counter(mapping.table for mapping in plan.entity_mappings).items())
        ),
        "removed_legacy_ids": sorted(
            mapping.legacy_id for mapping in plan.entity_mappings
        ),
        "preserved_canonical_ids": sorted(
            mapping.canonical_id for mapping in plan.entity_mappings
        ),
        "integrity_check": "ok",
        "foreign_key_violations": 0,
        "unresolved": _unresolved_document(plan),
    }


def _publish_atomically(
    temporary_paths: tuple[Path, Path, Path],
    final_paths: tuple[Path, Path, Path],
) -> None:
    """Publish same-directory files without ever replacing an existing path."""

    published: list[Path] = []
    try:
        for temporary, final in zip(temporary_paths, final_paths, strict=True):
            os.link(temporary, final)
            published.append(final)
        for temporary in temporary_paths:
            temporary.unlink()
    except BaseException:
        for final in reversed(published):
            final.unlink(missing_ok=True)
        raise


def apply_legacy_lineage_migration(
    source_database: Path,
    manifest_path: Path,
    output_database: Path,
) -> LegacyLineageMigrationResult:
    """Apply one verified lineage plan without mutating the source database."""

    source = source_database.resolve()
    manifest_file = manifest_path.resolve()
    output = output_database.resolve(strict=False)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not manifest_file.is_file():
        raise FileNotFoundError(manifest_file)
    if source == output:
        raise ValueError("source and output database paths must differ")

    aliases, report, temp_output, temp_aliases, temp_report = _artifact_paths(output)
    for path in (output, aliases, report, temp_output, temp_aliases, temp_report):
        _require_absent(path)

    manifest, manifest_bytes = _load_manifest(manifest_file)
    source_sha256 = _sha256_file(source)
    plan = plan_legacy_lineage_migration(source, manifest)
    if plan.status != "READY":
        codes = ",".join(item.code for item in plan.unresolved)
        raise ValueError(f"legacy lineage migration BLOCKED: {codes}")

    output.parent.mkdir(parents=True, exist_ok=True)
    generated_final_paths = (output, aliases, report)
    generated_temp_paths = (temp_output, temp_aliases, temp_report)
    for path in generated_temp_paths:
        _require_absent(path)

    try:
        shutil.copyfile(source, temp_output)
        connection = sqlite3.connect(temp_output)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            before_counts = _table_counts(connection)
            connection.execute("BEGIN IMMEDIATE")
            removed_counts = _delete_legacy_graph(connection, plan)
            _verify_mapping_state(connection, plan)
            logical_digest = _logical_lineage_digest(connection)
            _update_snapshot_metadata(connection, logical_digest)
            _verify_integrity(connection)
            after_counts = _table_counts(connection)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

        output_sha256 = _sha256_file(temp_output)
        manifest_sha256 = _sha256_bytes(manifest_bytes)
        report_body = _report_body(
            source=source,
            output=output,
            source_sha256=source_sha256,
            output_sha256=output_sha256,
            manifest_sha256=manifest_sha256,
            manifest=manifest,
            logical_digest=logical_digest,
            before_counts=before_counts,
            after_counts=after_counts,
            removed_counts=removed_counts,
            plan=plan,
        )
        report_body_sha256 = _sha256_bytes(dump_bytes(report_body))
        aliases_document = {
            "format": LEGACY_LINEAGE_ALIASES_FORMAT,
            "version": 1,
            "source_database_sha256": source_sha256,
            "manifest_sha256": manifest_sha256,
            "migration_report_body_sha256": report_body_sha256,
            "entries": _alias_entries(manifest),
        }
        aliases_bytes = dump_bytes(aliases_document)
        report_document = dict(report_body)
        report_document["aliases_sha256"] = _sha256_bytes(aliases_bytes)
        report_document["report_body_sha256"] = report_body_sha256
        report_bytes = dump_bytes(report_document)

        _write_create_only(temp_aliases, aliases_bytes)
        _write_create_only(temp_report, report_bytes)
        if _sha256_file(source) != source_sha256:
            raise ValueError("SOURCE_CHANGED_DURING_MIGRATION")
        _publish_atomically(
            (temp_output, temp_aliases, temp_report),
            generated_final_paths,
        )
    except BaseException:
        for path in generated_temp_paths:
            path.unlink(missing_ok=True)
        raise

    return LegacyLineageMigrationResult(
        output_database=output,
        aliases_path=aliases,
        report_path=report,
        output_sha256=output_sha256,
        logical_lineage_digest=logical_digest,
        removed_counts=removed_counts,
    )
