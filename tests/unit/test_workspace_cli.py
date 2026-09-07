from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

import evidence_review.command_dispatch as command_dispatch
from evidence_review.evidence.store import EvidenceStore

dispatch = command_dispatch.main


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


def test_decision_import_rejects_linked_run_before_packet_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    run_id = "RUN-1234567890ABCDEF1234"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    external_runs = tmp_path / "external-runs"
    external_run = external_runs / run_id
    external_run.mkdir(parents=True)
    (external_run / "final-review-packet.json").write_bytes(b"external packet")
    runs = workspace / "runs"
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(runs), str(external_runs)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            pytest.skip(
                "directory junction creation unavailable: "
                f"exit={completed.returncode}; detail={detail or '<empty>'}"
            )
    else:
        try:
            runs.symlink_to(external_runs, target_is_directory=True)
        except OSError as error:
            pytest.skip(f"directory symlink creation unavailable: {error}")
    envelope = tmp_path / "envelope.json"
    envelope.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        command_dispatch,
        "import_human_decision_envelope",
        lambda *_args, **_kwargs: external_run / "decision.json",
    )

    result = command_dispatch._review_import_decision(
        type(
            "Args",
            (),
            {
                "workspace": workspace,
                "run_id": run_id,
                "envelope": envelope,
            },
        )()
    )

    assert result == 2
    assert capsys.readouterr().out == ""
