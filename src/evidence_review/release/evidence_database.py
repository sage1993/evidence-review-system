"""Verify the evidence database as an exact release input."""

from __future__ import annotations

import hashlib
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from evidence_review.evidence.finalization import (
    EvidenceDatabaseNotFinalized,
    EvidenceIndexStale,
    EvidenceLogicalSnapshotMismatch,
    FinalizedEvidenceState,
    validate_finalized_evidence,
)
from evidence_review.evidence.schema_version import (
    SchemaUpgradeRequired,
    UnsupportedSchemaVersion,
)
from evidence_review.evidence.store import EvidenceStore, reject_sqlite_sidecars
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.release.config import ReleaseConfig, resolve_evidence_database

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ReleaseEvidenceDatabaseError(ValueError):
    """A stable release-validation failure for one evidence database."""

    def __init__(self, reason_code: str, detail: str) -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}")


@dataclass(frozen=True, slots=True)
class VerifiedReleaseEvidence:
    """The exact physical file and finalized logical snapshot validated for release."""

    path: Path
    file_sha256: str
    snapshot_sha256: str
    schema_version: int
    retrieval_record_count: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _raise_validation_error(error: BaseException) -> NoReturn:
    if isinstance(error, EvidenceDatabaseNotFinalized):
        code = "EVIDENCE_DATABASE_NOT_FINALIZED"
    elif isinstance(error, EvidenceLogicalSnapshotMismatch):
        code = "EVIDENCE_LOGICAL_SNAPSHOT_MISMATCH"
    elif isinstance(error, EvidenceIndexStale):
        code = "EVIDENCE_INDEX_STALE"
    elif isinstance(error, UnsupportedSchemaVersion):
        code = "EVIDENCE_DATABASE_NOT_FINALIZED"
    elif isinstance(error, SchemaUpgradeRequired):
        code = "EVIDENCE_SCHEMA_NOT_CURRENT"
    elif isinstance(error, sqlite3.DatabaseError):
        code = "SQLITE_DATABASE_INVALID"
    elif isinstance(error, RuntimeError):
        message = str(error)
        known_codes = (
            "EVIDENCE_DATABASE_INTEGRITY_FAILED",
            "EVIDENCE_DATABASE_FOREIGN_KEY_FAILED",
        )
        code = next((item for item in known_codes if item in message), "EVIDENCE_VALIDATION_FAILED")
    else:
        code = "EVIDENCE_VALIDATION_FAILED"
    raise ReleaseEvidenceDatabaseError(code, type(error).__name__) from error


def _verified_path(
    workspace: Path,
    config: ReleaseConfig,
) -> tuple[Path, tuple[str, ...]]:
    selected = resolve_evidence_database(workspace, config)
    try:
        relative = selected.relative_to(workspace)
    except ValueError as error:
        raise ReleaseEvidenceDatabaseError(
            "EVIDENCE_DATABASE_PATH_UNTRUSTED",
            "selected evidence database is outside the workspace",
        ) from error
    relative_parts = relative.parts
    if not relative_parts:
        raise ReleaseEvidenceDatabaseError(
            "EVIDENCE_DATABASE_PATH_UNTRUSTED",
            "selected evidence database path is empty",
        )
    try:
        verified = verified_regular_file_below(
            workspace,
            relative_parts,
            field="release evidence database",
        )
    except FileNotFoundError as error:
        raise ReleaseEvidenceDatabaseError(
            "EVIDENCE_DATABASE_MISSING",
            "selected evidence database does not exist",
        ) from error
    except PermissionError as error:
        raise ReleaseEvidenceDatabaseError(
            "EVIDENCE_DATABASE_UNREADABLE",
            "selected evidence database cannot be inspected",
        ) from error
    except ValueError as error:
        raise ReleaseEvidenceDatabaseError(
            "EVIDENCE_DATABASE_PATH_UNTRUSTED",
            "selected evidence database path contains a link or escapes the workspace",
        ) from error
    return verified, relative_parts


def _reject_sidecars(path: Path) -> None:
    try:
        reject_sqlite_sidecars(path)
    except RuntimeError as error:
        raise ReleaseEvidenceDatabaseError(
            "EVIDENCE_DATABASE_SIDECAR_PRESENT",
            "SQLite sidecar files are not allowed for release evidence",
        ) from error


def verify_release_evidence_database(
    workspace_root: Path,
    config: ReleaseConfig,
    *,
    expected_snapshot_sha256: str | None,
    expected_file_sha256: str | None,
) -> VerifiedReleaseEvidence:
    """Verify trust, finalization, lineage, sidecars, and byte stability."""
    if expected_snapshot_sha256 is None:
        raise ReleaseEvidenceDatabaseError(
            "PACKET_SNAPSHOT_REQUIRED",
            "release packet must declare an evidence snapshot hash",
        )
    if not isinstance(expected_snapshot_sha256, str) or not _SHA256.fullmatch(
        expected_snapshot_sha256
    ):
        raise ReleaseEvidenceDatabaseError(
            "PACKET_SNAPSHOT_INVALID",
            "release packet evidence snapshot hash must be a lowercase SHA-256",
        )
    if expected_file_sha256 is None:
        raise ReleaseEvidenceDatabaseError(
            "RUN_EVIDENCE_DATABASE_HASH_REQUIRED",
            "manifest-bound review inputs must declare the exact evidence database hash",
        )
    if not isinstance(expected_file_sha256, str) or not _SHA256.fullmatch(
        expected_file_sha256
    ):
        raise ReleaseEvidenceDatabaseError(
            "RUN_EVIDENCE_DATABASE_HASH_INVALID",
            "manifest-bound review inputs contain an invalid evidence database hash",
        )

    try:
        workspace = verified_regular_directory(
            workspace_root,
            field="release workspace root",
        )
    except (FileNotFoundError, PermissionError, ValueError) as error:
        raise ReleaseEvidenceDatabaseError(
            "EVIDENCE_DATABASE_PATH_UNTRUSTED",
            "release workspace root is not a trusted regular directory",
        ) from error

    path, relative_parts = _verified_path(workspace, config)
    _reject_sidecars(path)
    try:
        before_sha256 = _sha256_file(path)
    except OSError as error:
        raise ReleaseEvidenceDatabaseError(
            "EVIDENCE_DATABASE_UNREADABLE",
            "selected evidence database cannot be hashed",
        ) from error
    try:
        with tempfile.TemporaryDirectory(
            prefix="evidence-review-release-evidence-"
        ) as temporary:
            validation_path = Path(temporary) / path.name
            shutil.copyfile(path, validation_path)
            validation_sha256 = _sha256_file(validation_path)
            if validation_sha256 != before_sha256:
                raise ReleaseEvidenceDatabaseError(
                    "PHYSICAL_FILE_CHANGED_DURING_VALIDATION",
                    "evidence database bytes changed while creating validation snapshot",
                )
            _reject_sidecars(validation_path)
            try:
                with EvidenceStore(validation_path, read_only=True) as store:
                    state: FinalizedEvidenceState = validate_finalized_evidence(store)
            except (
                EvidenceDatabaseNotFinalized,
                EvidenceLogicalSnapshotMismatch,
                EvidenceIndexStale,
                SchemaUpgradeRequired,
                UnsupportedSchemaVersion,
                sqlite3.DatabaseError,
                RuntimeError,
                ValueError,
                OSError,
            ) as error:
                _raise_validation_error(error)
            _reject_sidecars(validation_path)
            if _sha256_file(validation_path) != validation_sha256:
                raise ReleaseEvidenceDatabaseError(
                    "PHYSICAL_FILE_CHANGED_DURING_VALIDATION",
                    "validation snapshot bytes changed during SQLite validation",
                )
    except ReleaseEvidenceDatabaseError:
        raise
    except OSError as error:
        raise ReleaseEvidenceDatabaseError(
            "EVIDENCE_DATABASE_UNREADABLE",
            "selected evidence database cannot be copied for validation",
        ) from error

    _reject_sidecars(path)
    path_after, _ = _verified_path(workspace, config)
    if path_after != path:
        raise ReleaseEvidenceDatabaseError(
            "EVIDENCE_DATABASE_PATH_CHANGED_DURING_VALIDATION",
            "selected evidence database path changed during validation",
        )
    try:
        after_sha256 = _sha256_file(path_after)
    except OSError as error:
        raise ReleaseEvidenceDatabaseError(
            "EVIDENCE_DATABASE_UNREADABLE",
            "selected evidence database cannot be rehashed",
        ) from error
    if before_sha256 != after_sha256 or validation_sha256 != after_sha256:
        raise ReleaseEvidenceDatabaseError(
            "PHYSICAL_FILE_CHANGED_DURING_VALIDATION",
            "evidence database bytes changed during validation",
        )
    if state.snapshot_hash != expected_snapshot_sha256:
        raise ReleaseEvidenceDatabaseError(
            "PACKET_SNAPSHOT_MISMATCH",
            "finalized evidence snapshot does not match the release packet",
        )
    if after_sha256 != expected_file_sha256:
        raise ReleaseEvidenceDatabaseError(
            "RUN_EVIDENCE_DATABASE_HASH_MISMATCH",
            "evidence database bytes do not match the manifest-bound review inputs",
        )

    return VerifiedReleaseEvidence(
        path=path_after,
        file_sha256=after_sha256,
        snapshot_sha256=state.snapshot_hash,
        schema_version=state.schema_version,
        retrieval_record_count=state.retrieval_record_count,
    )
