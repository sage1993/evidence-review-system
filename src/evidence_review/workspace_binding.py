"""Local active-workspace binding for the user-facing ERS skill handoff."""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from evidence_review.canonical_json import dump_bytes
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.runtime_filesystem import create_inherited_temp_file

ACTIVE_WORKSPACE_BINDING_FORMAT = "evidence-review/active-workspace-binding"
ACTIVE_WORKSPACE_BINDING_VERSION = 1
_ACTIVE_WORKSPACE_RELATIVE_PATH = Path(".ers") / "active-workspace.json"


@dataclass(frozen=True)
class ActiveWorkspaceBinding:
    """Exact local workspace and evidence snapshot selected for the next review."""

    workspace: Path
    evidence_snapshot_hash: str
    evidence_db_sha256: str
    schema_version: int
    retrieval_record_count: int
    clause_record_count: int

    def to_document(self) -> dict[str, object]:
        return {
            "format": ACTIVE_WORKSPACE_BINDING_FORMAT,
            "version": ACTIVE_WORKSPACE_BINDING_VERSION,
            "workspace": str(self.workspace),
            "evidence_snapshot_hash": self.evidence_snapshot_hash,
            "evidence_db_sha256": self.evidence_db_sha256,
            "schema_version": self.schema_version,
            "retrieval_record_count": self.retrieval_record_count,
            "clause_record_count": self.clause_record_count,
        }


def active_workspace_binding_path(repository_root: Path) -> Path:
    """Return the repository-local control-state path used by ERS skills."""
    root = verified_regular_directory(repository_root, field="repository root")
    return root / _ACTIVE_WORKSPACE_RELATIVE_PATH


def _hash_value(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{label} must be a 64-character SHA-256 value")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{label} must be hexadecimal") from error
    return value.lower()


def _integer_value(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _binding_for_workspace(workspace: Path) -> ActiveWorkspaceBinding:
    resolved_workspace = verified_regular_directory(workspace, field="workspace")
    try:
        database = verified_regular_file_below(
            resolved_workspace,
            ("evidence", "evidence.sqlite"),
            field="evidence database",
        )
        provenance = finalized_evidence_provenance(database)
    except (FileNotFoundError, sqlite3.Error, RuntimeError, ValueError) as error:
        raise ValueError(f"ACTIVE_WORKSPACE_INVALID: {error}") from error

    return ActiveWorkspaceBinding(
        workspace=resolved_workspace,
        evidence_snapshot_hash=_hash_value(
            provenance["evidence_snapshot_hash"],
            "evidence_snapshot_hash",
        ),
        evidence_db_sha256=_hash_value(
            provenance["evidence_db_sha256"],
            "evidence_db_sha256",
        ),
        schema_version=_integer_value(
            provenance["schema_version"],
            "schema_version",
        ),
        retrieval_record_count=_integer_value(
            provenance["retrieval_record_count"],
            "retrieval_record_count",
        ),
        clause_record_count=_integer_value(
            provenance["clause_record_count"],
            "clause_record_count",
        ),
    )


def _write_binding(path: Path, binding: ActiveWorkspaceBinding) -> None:
    state_directory = path.parent
    state_directory.mkdir(parents=True, exist_ok=True)
    state_directory = verified_regular_directory(
        state_directory,
        field="active workspace state directory",
    )
    path = state_directory / path.name

    temporary_path: Path | None = None
    try:
        with create_inherited_temp_file(
            state_directory,
            prefix=".active-workspace-",
            delete=False,
        ) as (temporary_path, stream):
            stream.write(dump_bytes(binding.to_document()))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def bind_active_workspace(
    repository_root: Path,
    workspace: Path,
) -> ActiveWorkspaceBinding:
    """Atomically select a validated workspace for ``$ERS_REVIEW``."""
    binding_path = active_workspace_binding_path(repository_root)
    binding = _binding_for_workspace(workspace)
    _write_binding(binding_path, binding)
    return binding


def _decode_binding(payload: object) -> ActiveWorkspaceBinding:
    if not isinstance(payload, dict):
        raise ValueError("active workspace binding must be a JSON object")
    document = cast(dict[str, object], payload)
    expected_keys = {
        "format",
        "version",
        "workspace",
        "evidence_snapshot_hash",
        "evidence_db_sha256",
        "schema_version",
        "retrieval_record_count",
        "clause_record_count",
    }
    if set(document) != expected_keys:
        raise ValueError("active workspace binding fields are invalid")
    if document["format"] != ACTIVE_WORKSPACE_BINDING_FORMAT:
        raise ValueError("active workspace binding format is invalid")
    if document["version"] != ACTIVE_WORKSPACE_BINDING_VERSION:
        raise ValueError("active workspace binding version is invalid")
    workspace_value = document["workspace"]
    if not isinstance(workspace_value, str) or not workspace_value:
        raise ValueError("active workspace path is invalid")
    workspace = Path(workspace_value)
    if not workspace.is_absolute():
        raise ValueError("active workspace path must be absolute")
    return ActiveWorkspaceBinding(
        workspace=workspace,
        evidence_snapshot_hash=_hash_value(
            document["evidence_snapshot_hash"],
            "evidence_snapshot_hash",
        ),
        evidence_db_sha256=_hash_value(
            document["evidence_db_sha256"],
            "evidence_db_sha256",
        ),
        schema_version=_integer_value(
            document["schema_version"],
            "schema_version",
        ),
        retrieval_record_count=_integer_value(
            document["retrieval_record_count"],
            "retrieval_record_count",
        ),
        clause_record_count=_integer_value(
            document["clause_record_count"],
            "clause_record_count",
        ),
    )


def resolve_active_workspace(repository_root: Path) -> ActiveWorkspaceBinding:
    """Resolve and revalidate the active workspace without filesystem guessing."""
    active_workspace_binding_path(repository_root)
    try:
        binding_path = verified_regular_file_below(
            repository_root,
            (".ers", "active-workspace.json"),
            field="active workspace binding",
        )
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"ACTIVE_WORKSPACE_NOT_BOUND: {Path(repository_root) / _ACTIVE_WORKSPACE_RELATIVE_PATH}"
        ) from error
    try:
        payload = json.loads(binding_path.read_text(encoding="utf-8"))
        stored = _decode_binding(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"ACTIVE_WORKSPACE_BINDING_INVALID: {error}") from error

    try:
        current = _binding_for_workspace(stored.workspace)
    except PermissionError as error:
        raise ValueError(f"PERMISSION_DENIED: {error}") from error
    except (FileNotFoundError, OSError, ValueError) as error:
        raise ValueError(f"ACTIVE_WORKSPACE_STALE: {error}") from error
    if stored != current:
        reason = (
            "SOURCE_MISMATCH"
            if (
                stored.evidence_snapshot_hash != current.evidence_snapshot_hash
                or stored.evidence_db_sha256 != current.evidence_db_sha256
            )
            else "ACTIVE_WORKSPACE_STALE"
        )
        raise ValueError(
            f"ACTIVE_WORKSPACE_STALE: {reason}: evidence snapshot or workspace identity changed"
        )
    return current
