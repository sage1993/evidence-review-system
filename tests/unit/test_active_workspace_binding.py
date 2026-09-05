from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from evidence_review.evidence.store import EvidenceStore


def _workspace_api() -> tuple[str, Any, Any]:
    try:
        module = importlib.import_module("evidence_review.workspace_binding")
    except ModuleNotFoundError:
        pytest.fail("evidence_review.workspace_binding is not implemented", pytrace=False)
    required = (
        "ACTIVE_WORKSPACE_BINDING_FORMAT",
        "bind_active_workspace",
        "resolve_active_workspace",
    )
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        pytest.fail(f"workspace binding API missing: {missing}", pytrace=False)
    return (
        module.ACTIVE_WORKSPACE_BINDING_FORMAT,
        module.bind_active_workspace,
        module.resolve_active_workspace,
    )


def _ready_workspace(root: Path, marker: str = "a") -> Path:
    workspace = root.resolve()
    database = workspace / "evidence" / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        connection = store.require_connection()
        snapshot_hash = marker * 64
        connection.execute(
            "INSERT OR REPLACE INTO snapshot_meta(key, value) VALUES('snapshot_hash', ?)",
            (snapshot_hash,),
        )
        connection.execute(
            "INSERT OR REPLACE INTO retrieval_meta(key, value) VALUES('snapshot_hash', ?)",
            (snapshot_hash,),
        )
        connection.commit()
    return workspace


def test_binding_round_trips_exact_workspace_and_snapshot(tmp_path: Path) -> None:
    binding_format, bind_active_workspace, resolve_active_workspace = _workspace_api()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    workspace = _ready_workspace(tmp_path / "workspace")

    binding = bind_active_workspace(repository_root, workspace)
    resolved = resolve_active_workspace(repository_root)

    assert resolved.workspace == workspace
    assert len(resolved.evidence_snapshot_hash) == 64
    assert len(resolved.evidence_db_sha256) == 64
    assert resolved.evidence_snapshot_hash == binding.evidence_snapshot_hash
    assert resolved.evidence_db_sha256 == binding.evidence_db_sha256

    document = json.loads(
        (repository_root / ".ers" / "active-workspace.json").read_text(encoding="utf-8")
    )
    assert document["format"] == binding_format
    assert document["workspace"] == str(workspace)


def test_rebinding_replaces_only_the_local_active_pointer(tmp_path: Path) -> None:
    _binding_format, bind_active_workspace, resolve_active_workspace = _workspace_api()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    first = _ready_workspace(tmp_path / "first", "a")
    second = _ready_workspace(tmp_path / "second", "b")

    bind_active_workspace(repository_root, first)
    bind_active_workspace(repository_root, second)

    assert resolve_active_workspace(repository_root).workspace == second
    assert (first / "evidence" / "evidence.sqlite").is_file()
    assert (second / "evidence" / "evidence.sqlite").is_file()


def test_active_binding_fails_closed_after_evidence_snapshot_changes(tmp_path: Path) -> None:
    _binding_format, bind_active_workspace, resolve_active_workspace = _workspace_api()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    workspace = _ready_workspace(tmp_path / "workspace")
    bind_active_workspace(repository_root, workspace)

    database = workspace / "evidence" / "evidence.sqlite"
    with EvidenceStore(database) as store:
        connection = store.require_connection()
        connection.execute(
            "UPDATE snapshot_meta SET value = ? WHERE key = 'snapshot_hash'",
            ("c" * 64,),
        )
        connection.execute(
            "UPDATE retrieval_meta SET value = ? WHERE key = 'snapshot_hash'",
            ("c" * 64,),
        )
        connection.commit()

    with pytest.raises(ValueError, match="ACTIVE_WORKSPACE_STALE"):
        resolve_active_workspace(repository_root)


def test_missing_active_binding_does_not_guess_from_available_databases(tmp_path: Path) -> None:
    _binding_format, _bind_active_workspace, resolve_active_workspace = _workspace_api()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    _ready_workspace(repository_root / "workspace-a")
    _ready_workspace(repository_root / "workspace-b")

    with pytest.raises(FileNotFoundError, match="ACTIVE_WORKSPACE_NOT_BOUND"):
        resolve_active_workspace(repository_root)

def test_binding_rejects_workspace_symlink(tmp_path: Path) -> None:
    _binding_format, bind_active_workspace, _resolve_active_workspace = _workspace_api()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    target = _ready_workspace(tmp_path / "workspace-target")
    link = tmp_path / "workspace-link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"workspace symlink creation unavailable: {error}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        bind_active_workspace(repository_root, link)
