from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from evidence_review.workflow import events


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


def test_event_directory_uses_canonical_trust_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_directory = tmp_path / "runs" / "RUN-0123456789ABCDEF0123"
    events_directory = run_directory / "events"
    events_directory.mkdir(parents=True)
    calls: list[tuple[Path, str]] = []
    original = events.verified_regular_directory

    def recording_verifier(path: Path, *, field: str) -> Path:
        calls.append((path, field))
        return original(path, field=field)

    monkeypatch.setattr(events, "verified_regular_directory", recording_verifier)

    assert events.load_workflow_events(events_directory) == ()
    assert any(path == events_directory for path, _field in calls)


def test_event_directory_link_is_rejected_before_external_read(tmp_path: Path) -> None:
    run_directory = tmp_path / "runs" / "RUN-0123456789ABCDEF0123"
    events_directory = run_directory / "events"
    events_directory.mkdir(parents=True)
    external = tmp_path / "external-events"
    external.mkdir()
    events_directory.rmdir()
    _directory_link(events_directory, external)

    with pytest.raises(ValueError, match="symlink|reparse|workflow"):
        events.load_workflow_events(events_directory)
