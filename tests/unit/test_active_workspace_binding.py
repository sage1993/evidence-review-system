from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.command_dispatch import main as dispatch
from evidence_review.evidence.store import EvidenceStore
from evidence_review.workspace_binding import (
    ACTIVE_WORKSPACE_BINDING_FORMAT,
    bind_active_workspace,
    resolve_active_workspace,
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
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    workspace = _ready_workspace(tmp_path / "workspace")

    binding = bind_active_workspace(repository_root, workspace)
    resolved = resolve_active_workspace(repository_root)

    assert resolved.workspace == workspace
    assert resolved.evidence_snapshot_hash == binding.evidence_snapshot_hash
    assert resolved.evidence_db_sha256 == binding.evidence_db_sha256

    document = json.loads(
        (repository_root / ".ers" / "active-workspace.json").read_text(encoding="utf-8")
    )
    assert document["format"] == ACTIVE_WORKSPACE_BINDING_FORMAT
    assert document["workspace"] == str(workspace)


def test_rebinding_replaces_only_the_local_active_pointer(tmp_path: Path) -> None:
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
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    _ready_workspace(repository_root / "workspace-a")
    _ready_workspace(repository_root / "workspace-b")

    with pytest.raises(FileNotFoundError, match="ACTIVE_WORKSPACE_NOT_BOUND"):
        resolve_active_workspace(repository_root)


def test_workspace_cli_binds_and_resolves_the_same_workspace(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    workspace = _ready_workspace(tmp_path / "workspace")

    assert (
        dispatch(
            [
                "workspace",
                "bind",
                "--repository-root",
                str(repository_root),
                "--workspace",
                str(workspace),
            ]
        )
        == 0
    )
    bound = json.loads(capsys.readouterr().out)
    assert bound["status"] == "BOUND"
    assert bound["workspace"] == str(workspace)

    assert (
        dispatch(
            [
                "workspace",
                "active",
                "--repository-root",
                str(repository_root),
            ]
        )
        == 0
    )
    active = json.loads(capsys.readouterr().out)
    assert active["status"] == "ACTIVE"
    assert active["workspace"] == str(workspace)
    assert active["evidence_snapshot_hash"] == bound["evidence_snapshot_hash"]
