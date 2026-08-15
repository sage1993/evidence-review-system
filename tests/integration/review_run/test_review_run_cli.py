from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from evidence_review import cli
from evidence_review.cli_parser import build_parser
from evidence_review.review_packet.server_runtime import idle_timeout_argument


def test_review_run_prepare_cli_routes_and_outputs_status(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    request = tmp_path / "request.json"
    run_directory = workspace / "runs" / "RUN-0123456789ABCDEF0123"

    def fake_prepare(workspace_root: Path, request_path: Path):
        assert workspace_root == workspace
        assert request_path == request
        return SimpleNamespace(
            run_id="RUN-0123456789ABCDEF0123",
            run_directory=run_directory,
            track_a_bundle=run_directory / "track-a-bundle.json",
            confidence_input=run_directory / "confidence-input.json",
        )

    monkeypatch.setattr(cli, "prepare_review_run", fake_prepare, raising=False)

    exit_code = cli.main(
        [
            "review-run",
            "prepare",
            "--workspace",
            str(workspace),
            "--request",
            str(request),
        ]
    )

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert document == {
        "format": "evidence-review/review-run-cli-status",
        "version": 1,
        "stage": "prepare",
        "status": "AWAITING_TRACK_OUTPUTS",
        "run_id": "RUN-0123456789ABCDEF0123",
        "run_directory": str(run_directory),
        "track_a_bundle": str(run_directory / "track-a-bundle.json"),
        "confidence_input": str(run_directory / "confidence-input.json"),
    }


def test_review_run_finalize_cli_routes_publish_and_outputs_status(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    track_a = tmp_path / "track-a.json"
    track_b = tmp_path / "track-b.json"
    run_id = "RUN-0123456789ABCDEF0123"
    run_directory = workspace / "runs" / run_id
    packet_path = run_directory / "final-review-packet.json"
    html_path = run_directory / "review.html"
    published_path = workspace / "runs" / "final-review-packet.json"

    def fake_finalize(
        workspace_root: Path,
        supplied_run_id: str,
        track_a_output: Path,
        track_b_output: Path,
        *,
        publish: bool,
    ):
        assert workspace_root == workspace
        assert supplied_run_id == run_id
        assert track_a_output == track_a
        assert track_b_output == track_b
        assert publish is True
        return SimpleNamespace(
            run_id=run_id,
            run_directory=run_directory,
            packet=SimpleNamespace(status="READY_FOR_HUMAN_REVIEW"),
            packet_path=packet_path,
            review_html=html_path,
            published_packet=published_path,
        )

    monkeypatch.setattr(cli, "finalize_review_run", fake_finalize, raising=False)

    exit_code = cli.main(
        [
            "review-run",
            "finalize",
            "--workspace",
            str(workspace),
            "--run-id",
            run_id,
            "--track-a-output",
            str(track_a),
            "--track-b-output",
            str(track_b),
            "--publish",
        ]
    )

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert document == {
        "format": "evidence-review/review-run-cli-status",
        "version": 1,
        "stage": "finalize",
        "status": "READY_FOR_HUMAN_REVIEW",
        "run_id": run_id,
        "run_directory": str(run_directory),
        "packet": str(packet_path),
        "review_html": str(html_path),
        "published_packet": str(published_path),
    }


def test_review_run_finalize_open_returns_url_without_waiting(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    run_id = "RUN-0123456789ABCDEF0123"
    result = SimpleNamespace(
        run_id=run_id,
        run_directory=tmp_path / "workspace" / "runs" / run_id,
        packet=SimpleNamespace(status="READY_FOR_HUMAN_REVIEW"),
        packet_path=tmp_path / "packet.json",
        review_html=tmp_path / "review.html",
        published_packet=None,
    )
    monkeypatch.setattr(cli, "finalize_review_run", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(cli, "open_review_run", lambda *_args, **_kwargs: "http://127.0.0.1/review")

    assert cli.main([
        "review-run", "finalize", "--workspace", str(tmp_path / "workspace"),
        "--run-id", run_id, "--track-a-output", str(tmp_path / "a.json"),
        "--track-b-output", str(tmp_path / "b.json"), "--open",
    ]) == 0

    assert json.loads(capsys.readouterr().out)["url"] == "http://127.0.0.1/review"


def test_review_run_cli_uses_declared_error_exit_codes(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    def existing(*args, **kwargs):
        raise FileExistsError("already exists")

    monkeypatch.setattr(cli, "prepare_review_run", existing, raising=False)
    assert (
        cli.main(
            [
                "review-run",
                "prepare",
                "--workspace",
                str(tmp_path / "workspace"),
                "--request",
                str(tmp_path / "request.json"),
            ]
        )
        == 1
    )
    assert "already exists" in capsys.readouterr().err

    def invalid(*args, **kwargs):
        raise ValueError("invalid request")

    monkeypatch.setattr(cli, "prepare_review_run", invalid, raising=False)
    assert (
        cli.main(
            [
                "review-run",
                "prepare",
                "--workspace",
                str(tmp_path / "workspace-2"),
                "--request",
                str(tmp_path / "request-2.json"),
            ]
        )
        == 2
    )
    assert "invalid request" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("arguments", "expected"),
    (
        (("review-run", "--help"), "prepare"),
        (("review-run", "prepare", "--help"), "--workspace"),
        (("review-run", "finalize", "--help"), "--track-a-output"),
    ),
)
def test_review_run_help_commands(
    arguments: tuple[str, ...],
    expected: str,
) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "evidence_review", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    assert expected in completed.stdout


def test_review_run_serve_cli_returns_detached_url_and_timeout(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    run_id = "RUN-0123456789ABCDEF0123"
    calls: dict[str, object] = {}

    def fake_serve(workspace_root, supplied_run_id, *, reviewer_id, idle_timeout_seconds):
        calls.update(
            {
                "workspace": workspace_root,
                "run_id": supplied_run_id,
                "reviewer_id": reviewer_id,
                "idle_timeout_seconds": idle_timeout_seconds,
            }
        )
        return f"http://127.0.0.1:8123/runs/{run_id}/token/review"

    monkeypatch.setattr(cli, "serve_review_run", fake_serve)

    assert cli.main(
        [
            "review-run",
            "serve",
            "--workspace",
            str(tmp_path),
            "--run-id",
            run_id,
            "--reviewer-id",
            "reviewer-01",
            "--detach",
            "--idle-timeout-seconds",
            "5",
        ]
    ) == 0

    document = json.loads(capsys.readouterr().out)
    assert document["url"].startswith("http://127.0.0.1:")
    assert document["detached"] is True
    assert document["idle_timeout_seconds"] == 5.0
    assert calls == {
        "workspace": tmp_path,
        "run_id": run_id,
        "reviewer_id": "reviewer-01",
        "idle_timeout_seconds": 5.0,
    }


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "not-a-number"])
def test_idle_timeout_argument_rejects_non_positive_or_non_finite_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        idle_timeout_argument(value)


def test_review_run_serve_parser_uses_thirty_minute_default() -> None:
    args = build_parser().parse_args(
        [
            "review-run",
            "serve",
            "--workspace",
            "workspace",
            "--run-id",
            "RUN-0123456789ABCDEF0123",
            "--detach",
        ]
    )
    assert args.idle_timeout_seconds == 1800.0
