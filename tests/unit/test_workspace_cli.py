from __future__ import annotations

import json
from pathlib import Path

from evidence_review.command_dispatch import main as dispatch
from evidence_review.evidence.store import EvidenceStore


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


def test_workspace_cli_binds_then_resolves_exact_workspace(
    tmp_path: Path,
    capsys,
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
    assert bound["format"] == "evidence-review/active-workspace-status"
    assert bound["stage"] == "bind"
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
    assert active["stage"] == "active"
    assert active["status"] == "ACTIVE"
    assert active["workspace"] == str(workspace)
    assert active["evidence_snapshot_hash"] == bound["evidence_snapshot_hash"]
    assert active["evidence_db_sha256"] == bound["evidence_db_sha256"]


def test_workspace_cli_missing_binding_fails_closed(
    tmp_path: Path,
    capsys,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()

    assert (
        dispatch(
            [
                "workspace",
                "active",
                "--repository-root",
                str(repository_root),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ACTIVE_WORKSPACE_NOT_BOUND" in captured.err
