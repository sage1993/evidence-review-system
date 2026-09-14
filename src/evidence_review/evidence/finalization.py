"""Finalize mutable evidence databases before they become review authority."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from evidence_review.evidence.clause_rebuild import materialize_clause_structure
from evidence_review.evidence.reference_materialization import (
    materialize_legal_reference_links,
)
from evidence_review.evidence.schema_version import (
    detect_schema_version,
    require_current_schema,
)
from evidence_review.evidence.snapshot import compute_snapshot_hash
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.index import build_fts_index, validate_fresh_index

FINALIZATION_VERSION = "1"


@dataclass(frozen=True, slots=True)
class FinalizedEvidenceState:
    """Immutable state required to bind one finalized evidence artifact."""

    snapshot_hash: str
    schema_version: int
    retrieval_record_count: int
    clause_record_count: int


class EvidenceDatabaseNotFinalized(RuntimeError):
    """Raised when a database is not a supported finalized review authority."""


class EvidenceLogicalSnapshotMismatch(RuntimeError):
    """Raised when canonical rows differ from the stored logical snapshot hash."""


class EvidenceIndexStale(RuntimeError):
    """Raised when retrieval storage is not bound to the logical snapshot."""


def _metadata(
    connection: sqlite3.Connection,
    table: str,
    key: str,
) -> str | None:
    row = connection.execute(
        f"SELECT value FROM {table} WHERE key = ?",  # noqa: S608
        (key,),
    ).fetchone()
    if row is None:
        return None
    value = row[0]
    return None if value is None else str(value)


def _require_metadata(
    connection: sqlite3.Connection,
    table: str,
    key: str,
) -> str:
    value = _metadata(connection, table, key)
    if value is None:
        raise EvidenceDatabaseNotFinalized(
            f"EVIDENCE_DATABASE_NOT_FINALIZED: missing {table}.{key}"
        )
    return value


def _verify_sqlite_integrity(connection: sqlite3.Connection) -> None:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()
    if integrity is None or integrity[0] != "ok":
        raise RuntimeError("EVIDENCE_DATABASE_INTEGRITY_FAILED")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("EVIDENCE_DATABASE_FOREIGN_KEY_FAILED")


def _state_from_connection(
    connection: sqlite3.Connection,
    snapshot_hash: str,
) -> FinalizedEvidenceState:
    return FinalizedEvidenceState(
        snapshot_hash=snapshot_hash,
        schema_version=detect_schema_version(connection),
        retrieval_record_count=int(
            connection.execute(
                "SELECT COUNT(*) FROM retrieval_records"
            ).fetchone()[0]
        ),
        clause_record_count=int(
            connection.execute(
                "SELECT COUNT(*) FROM clause_retrieval_records"
            ).fetchone()[0]
        ),
    )


def finalize_evidence_database(store: EvidenceStore) -> FinalizedEvidenceState:
    """Complete all deterministic evidence derivation while the store is mutable."""
    connection = store.require_connection()
    require_current_schema(connection)

    if _metadata(connection, "snapshot_meta", "lifecycle_state") == "FINALIZED":
        return validate_finalized_evidence(store)

    materialize_clause_structure(connection)

    # The provisional index is required before reference links can resolve
    # against clause retrieval records and clause/evidence lineage.
    build_fts_index(connection)
    materialize_legal_reference_links(connection)

    final_snapshot_hash = compute_snapshot_hash(store)
    connection.execute(
        """
        INSERT OR REPLACE INTO snapshot_meta(key, value)
        VALUES('snapshot_hash', ?)
        """,
        (final_snapshot_hash,),
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO snapshot_meta(key, value)
        VALUES('database_snapshot_hash', ?)
        """,
        (final_snapshot_hash,),
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO snapshot_meta(key, value)
        VALUES('lifecycle_state', 'FINALIZED')
        """
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO snapshot_meta(key, value)
        VALUES('finalization_version', ?)
        """,
        (FINALIZATION_VERSION,),
    )
    connection.commit()

    # Rebuild against the final logical hash. The trigger refreshes the clause
    # retrieval projection without changing canonical snapshot rows.
    build_fts_index(connection)
    if validate_fresh_index(connection) != final_snapshot_hash:
        raise EvidenceIndexStale("EVIDENCE_INDEX_STALE")
    if compute_snapshot_hash(store) != final_snapshot_hash:
        raise EvidenceLogicalSnapshotMismatch(
            "EVIDENCE_LOGICAL_SNAPSHOT_MISMATCH"
        )
    _verify_sqlite_integrity(connection)
    return _state_from_connection(connection, final_snapshot_hash)


def validate_finalized_evidence(store: EvidenceStore) -> FinalizedEvidenceState:
    """Validate a finalized database without repairing or mutating it."""
    connection = store.require_connection()
    require_current_schema(connection)

    lifecycle = _metadata(connection, "snapshot_meta", "lifecycle_state")
    version = _metadata(connection, "snapshot_meta", "finalization_version")
    if lifecycle != "FINALIZED" or version != FINALIZATION_VERSION:
        raise EvidenceDatabaseNotFinalized(
            "EVIDENCE_DATABASE_NOT_FINALIZED: finalized lifecycle metadata required"
        )

    stored_snapshot_hash = _require_metadata(
        connection,
        "snapshot_meta",
        "snapshot_hash",
    )
    if compute_snapshot_hash(store) != stored_snapshot_hash:
        raise EvidenceLogicalSnapshotMismatch(
            "EVIDENCE_LOGICAL_SNAPSHOT_MISMATCH"
        )

    try:
        retrieval_hash = validate_fresh_index(connection)
    except (RuntimeError, sqlite3.Error) as error:
        raise EvidenceIndexStale("EVIDENCE_INDEX_STALE") from error
    if retrieval_hash != stored_snapshot_hash:
        raise EvidenceIndexStale("EVIDENCE_INDEX_STALE")

    _verify_sqlite_integrity(connection)
    return _state_from_connection(connection, stored_snapshot_hash)
