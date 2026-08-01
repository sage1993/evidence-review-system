import sys
from subprocess import run


def test_module_help() -> None:
    result = run(
        [sys.executable, "-m", "ansim_review", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "evidence-first regulatory review" in result.stdout.lower()
