from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image


def _run(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    source = str(repo / "src")
    environment["PYTHONPATH"] = source + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=repo,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )



def test_acceptance_fixture_page_images_contain_visible_content(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    workspace = tmp_path / "acceptance-workspace"
    builder = repo / "scripts" / "build_issues_98_101_acceptance_workspace.py"

    seeded = _run(repo, str(builder), "seed", "--workspace", str(workspace))
    assert seeded.returncode == 0, seeded.stderr

    for page_number in (1, 2):
        image_path = (
            workspace
            / "page-images"
            / "REV-ACCEPT"
            / f"page-{page_number:04d}.png"
        )
        with Image.open(image_path) as image:
            assert any(channel_min < 255 for channel_min, _ in image.getextrema())


def test_acceptance_fixture_stays_on_public_review_question_contract(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    workspace = tmp_path / "acceptance-workspace"
    builder = repo / "scripts" / "build_issues_98_101_acceptance_workspace.py"

    seeded = _run(repo, str(builder), "seed", "--workspace", str(workspace))
    assert seeded.returncode == 0, seeded.stderr

    prepared_process = _run(
        repo,
        "-m",
        "evidence_review",
        "review-question",
        "prepare",
        "--workspace",
        str(workspace),
        "--question",
        "청소년문화의집 설치기준",
    )
    assert prepared_process.returncode == 0, prepared_process.stderr
    prepared = json.loads(prepared_process.stdout)
    assert prepared["status"] == "WAITING_TRACK_A"
    run_id = prepared["run_id"]
    run_directory = workspace / "runs" / run_id

    track_a_process = _run(
        repo,
        str(builder),
        "tracks",
        "--workspace",
        str(workspace),
        "--run-id",
        run_id,
    )
    assert track_a_process.returncode == 0, track_a_process.stderr
    track_a = json.loads(track_a_process.stdout)
    assert Path(track_a["track_a"]).is_file()

    submitted_a = _run(
        repo,
        "-m",
        "evidence_review",
        "review-question",
        "submit-track-a",
        "--workspace",
        str(workspace),
        "--run-id",
        run_id,
        "--track-a-output",
        str(run_directory / "acceptance-track-a.json"),
    )
    assert submitted_a.returncode == 0, submitted_a.stderr

    track_b_process = _run(
        repo,
        str(builder),
        "tracks",
        "--workspace",
        str(workspace),
        "--run-id",
        run_id,
        "--write-track-b",
    )
    assert track_b_process.returncode == 0, track_b_process.stderr
    assert (run_directory / "track-b-output.json").is_file()

    submitted_b = _run(
        repo,
        "-m",
        "evidence_review",
        "review-question",
        "submit-track-b",
        "--workspace",
        str(workspace),
        "--run-id",
        run_id,
        "--track-b-output",
        str(run_directory / "track-b-output.json"),
        "--publish",
    )
    assert submitted_b.returncode == 0, submitted_b.stderr
    result = json.loads(submitted_b.stdout)
    assert result["status"] == "READY_FOR_HUMAN_REVIEW"
    assert Path(result["review_html"]).is_file()

    request = json.loads(
        (run_directory / "review-request.json").read_text(encoding="utf-8")
    )
    evidence_query = json.loads(
        (run_directory / "evidence-query.json").read_text(encoding="utf-8")
    )
    assert request["inputs"]["snapshot_hash"] == evidence_query["snapshot_hash"]
    assert {item["citation"]["page_number"] for item in request["evidence"]} == {1, 2}
    assert all(
        item["citation"]["source_hash"] == "9" * 64
        for item in request["evidence"]
    )
