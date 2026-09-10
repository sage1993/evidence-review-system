from __future__ import annotations

import json
from pathlib import Path

from evidence_review.command_dispatch import main
from evidence_review.review_matter.service import ReviewMatterService

MATTER_ID = "MATTER-001"
REVIEWER_ID = "reviewer-01"


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ReviewMatterService.open(workspace).create(
        matter_id=MATTER_ID,
        title="Workbench CLI lifecycle",
    )
    return workspace


def _run(arguments: list[str], capsys) -> tuple[int, dict[str, object], str]:
    capsys.readouterr()
    code = main(arguments)
    captured = capsys.readouterr()
    return code, json.loads(captured.out) if captured.out else {}, captured.err


def test_workbench_cli_serves_and_manages_only_the_bound_matter(
    tmp_path: Path,
    capsys,
) -> None:
    workspace = _workspace(tmp_path)
    common = ["--workspace", str(workspace), "--matter-id", MATTER_ID]

    code, served, error = _run(
        [
            "review-matter",
            "workbench",
            "serve",
            *common,
            "--reviewer-id",
            REVIEWER_ID,
            "--idle-timeout-seconds",
            "10",
        ],
        capsys,
    )
    assert code == 0, error
    assert served == {
        "format": "evidence-review/workbench-cli-status",
        "version": 1,
        "stage": "serve",
        "status": "DETACHED",
        "matter_id": MATTER_ID,
        "reviewer_id": REVIEWER_ID,
        "url": served["url"],
        "idle_timeout_seconds": 10.0,
    }
    assert f"/workbench/{MATTER_ID}/" in served["url"]
    assert "/runs/" not in served["url"]

    try:
        code, status, error = _run(["review-matter", "workbench", "serve-status", *common], capsys)
        assert code == 0, error
        assert status["status"] == "RUNNING"
        assert status["server"]["matter_id"] == MATTER_ID
        assert status["server"]["reviewer_id"] == REVIEWER_ID
        assert "run_id" not in status["server"]
    finally:
        code, stopped, error = _run(["review-matter", "workbench", "serve-stop", *common], capsys)
        assert code == 0, error
        assert stopped == {
            "format": "evidence-review/workbench-cli-status",
            "version": 1,
            "stage": "serve-stop",
            "status": "STOPPED",
            "matter_id": MATTER_ID,
        }
