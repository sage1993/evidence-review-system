import sys
from subprocess import run

from ansim_review.cli_parser import build_parser


def test_module_help() -> None:
    result = run(
        [sys.executable, "-m", "ansim_review", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "evidence-first regulatory review" in result.stdout.lower()


def test_review_run_finalize_supports_open_flag() -> None:
    arguments = build_parser().parse_args(
        [
            "review-run",
            "finalize",
            "--workspace",
            "workspace",
            "--run-id",
            "RUN-001",
            "--track-a-output",
            "track-a.json",
            "--track-b-output",
            "track-b.json",
            "--open",
        ]
    )
    assert arguments.open is True
