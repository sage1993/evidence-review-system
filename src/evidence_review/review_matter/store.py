"""Transactional SQLite persistence for mutable ReviewMatter work."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from evidence_review.canonical_json import dumps
from evidence_review.review_matter.contracts import (
    MatterIssue,
    MatterSourceBinding,
    ReviewMatter,
    decode_review_matter,
    review_matter_document,
)

if TYPE_CHECKING:
    from evidence_review.review_matter.events import MatterEvent
    from evidence_review.review_matter.projection import MatterProjection


class MatterStoreError(RuntimeError):
    """Base class for fail-closed Matter store errors."""


class MatterAlreadyExists(MatterStoreError):
    """Raised when a create operation would replace existing work."""


class MatterNotFound(MatterStoreError):
    """Raised when a requested Matter does not exist."""


class MatterRevisionConflict(MatterStoreError):
    """Raised when a mutation uses a stale expected Matter revision."""


class MatterSchemaError(MatterStoreError):
    """Raised when a Matter database does not have the supported schema."""


class MatterStore:
    """Own one separate SQLite database for ReviewMatter work state."""

    SCHEMA_VERSION = 2

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        if self.path.exists() and not self.path.is_file():
            raise ValueError("Matter store path must be a file")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self.path.exists()
        self.connection = sqlite3.connect(str(self.path), timeout=30.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 30000")
        try:
            if is_new:
                schema = (
                    files("evidence_review.review_matter")
                    .joinpath("schema.sql")
                    .read_text(encoding="utf-8")
                )
                self.connection.executescript(schema)
                self.connection.commit()
            else:
                self._migrate_schema()
            self._require_schema()
        except BaseException:
            self.connection.close()
            if is_new:
                self.path.unlink(missing_ok=True)
            raise

    def _migrate_schema(self) -> None:
        """Upgrade mutable Matter storage without touching Matter projections."""
        version = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if version == 1:
            with self.transaction():
                try:
                    metadata_rows = self.connection.execute(
                        """
                        SELECT value FROM matter_meta
                        WHERE key = 'schema_version'
                        """
                    ).fetchall()
                except sqlite3.Error as error:
                    raise MatterSchemaError("MATTER_SCHEMA_VERSION_MISSING") from error
                if len(metadata_rows) != 1:
                    raise MatterSchemaError("MATTER_SCHEMA_VERSION_MISSING")
                if metadata_rows[0]["value"] != "1":
                    raise MatterSchemaError("MATTER_SCHEMA_VERSION_INVALID")
                metadata_update = self.connection.execute(
                    """
                    UPDATE matter_meta SET value = '2'
                    WHERE key = 'schema_version' AND value = '1'
                    """
                )
                if metadata_update.rowcount != 1:
                    raise MatterSchemaError("MATTER_SCHEMA_VERSION_UPDATE_FAILED")
                self.connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS formalization_snapshots (
                        snapshot_id TEXT PRIMARY KEY,
                        matter_id TEXT NOT NULL,
                        matter_revision INTEGER NOT NULL CHECK (matter_revision >= 1),
                        canonical_document BLOB NOT NULL,
                        UNIQUE(matter_id, matter_revision),
                        FOREIGN KEY (matter_id) REFERENCES matters(matter_id) ON DELETE RESTRICT
                    )
                    """
                )
                self.connection.execute("PRAGMA user_version = 2")
        elif version != self.SCHEMA_VERSION:
            raise MatterSchemaError(f"MATTER_SCHEMA_UNSUPPORTED: {version}")

    def _require_schema(self) -> None:
        version = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if version != self.SCHEMA_VERSION:
            raise MatterSchemaError(f"MATTER_SCHEMA_UNSUPPORTED: {version}")
        row = self.connection.execute(
            "SELECT value FROM matter_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None or row[0] != str(self.SCHEMA_VERSION):
            raise MatterSchemaError("MATTER_SCHEMA_VERSION_MISSING")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Serialize one mutation and roll back every exception."""
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> MatterStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _write_matter(self, matter: ReviewMatter) -> None:
        document = review_matter_document(matter)
        self.connection.execute(
            """
            INSERT INTO matters(matter_id, title, revision, document_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(matter_id) DO UPDATE SET
                title = excluded.title,
                revision = excluded.revision,
                document_json = excluded.document_json
            """,
            (matter.matter_id, matter.title, matter.revision, dumps(document)),
        )
        self.connection.execute(
            """
            INSERT INTO matter_projections(matter_id, revision, document_json)
            VALUES (?, ?, ?)
            ON CONFLICT(matter_id) DO UPDATE SET
                revision = excluded.revision,
                document_json = excluded.document_json
            """,
            (matter.matter_id, matter.revision, dumps(document)),
        )

    def _row_to_matter(self, row: sqlite3.Row) -> ReviewMatter:
        try:
            document = json.loads(str(row["document_json"]))
        except json.JSONDecodeError as error:
            raise MatterSchemaError("MATTER_DOCUMENT_INVALID_JSON") from error
        matter = decode_review_matter(document)
        if matter.matter_id != row["matter_id"] or matter.revision != row["revision"]:
            raise MatterSchemaError("MATTER_DOCUMENT_REVISION_MISMATCH")
        return matter

    def create(
        self,
        *,
        matter_id: str,
        title: str,
        issues: Sequence[MatterIssue] = (),
        source_bindings: Sequence[MatterSourceBinding] = (),
    ) -> ReviewMatter:
        """Create one Matter at revision 1 without replacing existing work."""
        matter = ReviewMatter(
            matter_id=matter_id,
            title=title,
            revision=1,
            issues=tuple(issues),
            source_bindings=tuple(source_bindings),
        )
        decode_review_matter(review_matter_document(matter))
        with self.transaction():
            try:
                self.connection.execute(
                    """
                    INSERT INTO matters(matter_id, title, revision, document_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        matter.matter_id,
                        matter.title,
                        matter.revision,
                        dumps(review_matter_document(matter)),
                    ),
                )
                self.connection.execute(
                    """
                    INSERT INTO matter_baselines(matter_id, document_json)
                    VALUES (?, ?)
                    """,
                    (matter.matter_id, dumps(review_matter_document(matter))),
                )
                self.connection.execute(
                    """
                    INSERT INTO matter_projections(matter_id, revision, document_json)
                    VALUES (?, ?, ?)
                    """,
                    (matter.matter_id, matter.revision, dumps(review_matter_document(matter))),
                )
            except sqlite3.IntegrityError as error:
                raise MatterAlreadyExists("MATTER_ALREADY_EXISTS") from error
        return matter

    def load(self, matter_id: str) -> ReviewMatter:
        """Load and strictly revalidate one Matter projection."""
        row = self.connection.execute(
            "SELECT matter_id, title, revision, document_json FROM matters WHERE matter_id = ?",
            (matter_id,),
        ).fetchone()
        if row is None:
            raise MatterNotFound("MATTER_NOT_FOUND")
        return self._row_to_matter(row)

    def apply_projection(self, matter: ReviewMatter) -> None:
        """Apply a decoded projection inside the caller's open transaction."""
        self._write_matter(matter)

    def apply_event_side_effects(self, matter_id: str, event: object) -> None:
        """Apply event-owned metadata inside the caller's open transaction."""
        kind = getattr(event, "kind", None)
        payload = getattr(event, "payload", None)
        if not isinstance(kind, str) or not isinstance(payload, dict):
            raise ValueError("invalid Matter event")
        if kind in {"EVIDENCE_BOUND", "EVIDENCE_REBOUND"}:
            self.connection.execute(
                """
                INSERT INTO matter_evidence_bindings(
                    matter_id, evidence_snapshot_hash, evidence_db_sha256,
                    schema_version, bound_revision
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(matter_id) DO UPDATE SET
                    evidence_snapshot_hash = excluded.evidence_snapshot_hash,
                    evidence_db_sha256 = excluded.evidence_db_sha256,
                    schema_version = excluded.schema_version,
                    bound_revision = excluded.bound_revision
                """,
                (
                    matter_id,
                    payload["evidence_snapshot_hash"],
                    payload["evidence_db_sha256"],
                    payload["schema_version"],
                    payload["bound_revision"],
                ),
            )
        elif kind == "SOURCE_DEPENDENCY_REGISTERED":
            self.connection.execute(
                """
                INSERT INTO matter_source_dependencies(
                    matter_id, issue_id, source_key, source_hash
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(matter_id, issue_id, source_key) DO UPDATE SET
                    source_hash = excluded.source_hash
                """,
                (
                    matter_id,
                    payload["issue_id"],
                    payload["source_key"],
                    payload["source_hash"],
                ),
            )
        elif kind == "ISSUES_INVALIDATED":
            source_key = payload.get("source_key")
            if isinstance(source_key, str):
                for issue_id in payload["issue_ids"]:
                    self.connection.execute(
                        """
                        UPDATE matter_source_dependencies
                        SET source_hash = ?
                        WHERE matter_id = ? AND issue_id = ? AND source_key = ?
                        """,
                        (
                            payload["new_source_hash"],
                            matter_id,
                            issue_id,
                            source_key,
                        ),
                    )

    def get_evidence_binding(self, matter_id: str) -> dict[str, object] | None:
        """Return the exact evidence identity currently bound to a Matter."""
        row = self.connection.execute(
            """
            SELECT evidence_snapshot_hash, evidence_db_sha256,
                   schema_version, bound_revision
            FROM matter_evidence_bindings
            WHERE matter_id = ?
            """,
            (matter_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "evidence_snapshot_hash": str(row["evidence_snapshot_hash"]),
            "evidence_db_sha256": str(row["evidence_db_sha256"]),
            "schema_version": int(row["schema_version"]),
            "bound_revision": int(row["bound_revision"]),
        }

    def persist_formalization_snapshot(
        self,
        *,
        snapshot_id: str,
        matter_id: str,
        matter_revision: int,
        canonical_document: bytes,
    ) -> bytes:
        """Create one immutable snapshot inside the caller's transaction."""
        existing = self.connection.execute(
            """
            SELECT snapshot_id, matter_id, matter_revision, canonical_document
            FROM formalization_snapshots
            WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchone()
        if existing is not None:
            if (
                existing["snapshot_id"] != snapshot_id
                or existing["matter_id"] != matter_id
                or existing["matter_revision"] != matter_revision
            ):
                raise MatterAlreadyExists("FORMALIZATION_SNAPSHOT_METADATA_MISMATCH")
            current = bytes(existing["canonical_document"])
            if current != canonical_document:
                raise MatterAlreadyExists("FORMALIZATION_SNAPSHOT_ID_CONFLICT")
            return current
        try:
            self.connection.execute(
                """
                INSERT INTO formalization_snapshots(
                    snapshot_id, matter_id, matter_revision, canonical_document
                ) VALUES (?, ?, ?, ?)
                """,
                (snapshot_id, matter_id, matter_revision, canonical_document),
            )
        except sqlite3.IntegrityError as error:
            raise MatterAlreadyExists("FORMALIZATION_SNAPSHOT_ALREADY_EXISTS") from error
        return canonical_document

    def load_formalization_snapshot_record(
        self, snapshot_id: str
    ) -> tuple[str, str, int, bytes] | None:
        """Return one persisted snapshot with its independently stored metadata."""
        row = self.connection.execute(
            """
            SELECT snapshot_id, matter_id, matter_revision, canonical_document
            FROM formalization_snapshots
            WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchone()
        if row is None:
            return None
        return (
            str(row["snapshot_id"]),
            str(row["matter_id"]),
            int(row["matter_revision"]),
            bytes(row["canonical_document"]),
        )

    def list_formalization_snapshot_records(self) -> tuple[tuple[str, str, int, bytes], ...]:
        """Return persisted snapshots with metadata in deterministic identity order."""
        rows = self.connection.execute(
            """
            SELECT snapshot_id, matter_id, matter_revision, canonical_document
            FROM formalization_snapshots
            ORDER BY snapshot_id
            """
        ).fetchall()
        return tuple(
            (
                str(row["snapshot_id"]),
                str(row["matter_id"]),
                int(row["matter_revision"]),
                bytes(row["canonical_document"]),
            )
            for row in rows
        )

    def list_formalization_snapshot_documents(self) -> tuple[bytes, ...]:
        """Return immutable snapshot documents in deterministic identity order."""
        return tuple(
            document
            for _, _, _, document in self.list_formalization_snapshot_records()
        )

    def list_source_dependencies(self, matter_id: str) -> tuple[dict[str, str], ...]:
        """Return exact Matter source dependencies in stable order."""
        rows = self.connection.execute(
            """
            SELECT issue_id, source_key, source_hash
            FROM matter_source_dependencies
            WHERE matter_id = ?
            ORDER BY issue_id, source_key
            """,
            (matter_id,),
        ).fetchall()
        return tuple(
            {
                "issue_id": str(row["issue_id"]),
                "source_key": str(row["source_key"]),
                "source_hash": str(row["source_hash"]),
            }
            for row in rows
        )

    def list_events(self, matter_id: str) -> tuple[MatterEvent, ...]:
        """Return the validated append-only event sequence."""
        from evidence_review.review_matter.events import list_matter_events

        return list_matter_events(self, matter_id)

    def rebuild_projection(self, matter_id: str) -> MatterProjection:
        """Rebuild a Matter projection from its baseline and event journal."""
        from evidence_review.review_matter.projection import rebuild_projection

        return rebuild_projection(self, matter_id)

    def rename(self, matter_id: str, expected_revision: int, title: str) -> ReviewMatter:
        """Rename a Matter using compare-and-swap revision semantics."""
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise ValueError("expected_revision is required")
        from evidence_review.review_matter.events import MatterEvent, append_matter_event

        return append_matter_event(
            self,
            matter_id,
            expected_revision,
            MatterEvent(kind="TITLE_CHANGED", payload={"title": title}),
        ).matter
