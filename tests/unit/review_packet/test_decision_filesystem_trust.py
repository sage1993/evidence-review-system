from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from evidence_review.review_packet.decision_record import (
    load_latest_valid_human_decision,
    write_human_decision,
)


def _directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
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
        return
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink creation unavailable: {error}")


def _record(run: Path, notes: str) -> Path:
    return write_human_decision(
        run,
        reviewer_id="reviewer-01",
        reviewed_at=datetime.now(UTC).isoformat(),
        packet_hash="a" * 64,
        decision="SATISFIED",
        notes=notes,
    )


def test_loader_does_not_consume_run_reached_through_linked_ancestor(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    runs = workspace / "runs"
    runs.mkdir(parents=True)
    external_runs = tmp_path / "external-runs"
    external_runs.mkdir()
    external_run = external_runs / "RUN-0123456789ABCDEF0123"
    external_run.mkdir()
    _record(external_run, "external decision")
    runs.rmdir()
    _directory_link(runs, external_runs)

    assert load_latest_valid_human_decision(
        runs / external_run.name,
        "a" * 64,
    ) is None


def test_writer_does_not_store_decision_through_linked_ancestor(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    runs = workspace / "runs"
    runs.mkdir(parents=True)
    external_runs = tmp_path / "external-runs"
    external_runs.mkdir()
    external_run = external_runs / "RUN-0123456789ABCDEF0123"
    external_run.mkdir()
    runs.rmdir()
    _directory_link(runs, external_runs)

    with pytest.raises(ValueError, match="symlink|reparse"):
        _record(runs / external_run.name, "must not escape")

    assert not (external_run / "human-decisions").exists()
