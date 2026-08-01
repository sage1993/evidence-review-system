import json
import os
import sys
from pathlib import Path
from subprocess import run

from ansim_review.cli import _result_exit_code
from ansim_review.contracts.engines import CalculationResult


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[3] / "src")
    return environment


def test_math_cli_is_byte_reproducible(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    request.write_text(
        json.dumps(
            {
                "formula_id": "FRONTAGE_RATIO",
                "formula_version": "1.0.0",
                "inputs": {
                    "frontage_length_m": "30",
                    "perimeter_length_m": "320",
                    "threshold_ratio": "0.125",
                },
            }
        ),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "ansim_review",
        "math-run",
        "--request",
        str(request),
    ]
    first_result = run(
        command + ["--output", str(first)],
        env=_environment(),
        capture_output=True,
    )
    second_result = run(
        command + ["--output", str(second)],
        env=_environment(),
        capture_output=True,
    )
    assert first_result.returncode == 0
    assert second_result.returncode == 0
    assert first.read_bytes() == second.read_bytes()
    assert not first.read_bytes().endswith(b"\n")


def test_math_cli_refuses_overwrite(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    output = tmp_path / "result.json"
    request.write_text(
        (
            '{"formula_id":"FRONTAGE_RATIO","formula_version":"1.0.0",'
            '"inputs":{"frontage_length_m":"1","perimeter_length_m":"8",'
            '"threshold_ratio":"0.125"}}'
        ),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "ansim_review",
        "math-run",
        "--request",
        str(request),
        "--output",
        str(output),
    ]
    assert run(command, env=_environment(), capture_output=True).returncode == 0
    assert run(command, env=_environment(), capture_output=True).returncode != 0


def test_math_cli_uses_declared_error_exit_codes(tmp_path: Path) -> None:
    invalid_request = tmp_path / "invalid.json"
    invalid_output = tmp_path / "invalid-result.json"
    invalid_request.write_text(
        (
            '{"formula_id":"FRONTAGE_RATIO","formula_version":"1.0.0",'
            '"inputs":{"frontage_length_m":30.0}}'
        ),
        encoding="utf-8",
    )
    result = run(
        [
            sys.executable,
            "-m",
            "ansim_review",
            "math-run",
            "--request",
            str(invalid_request),
            "--output",
            str(invalid_output),
        ],
        env=_environment(),
        capture_output=True,
    )
    assert result.returncode == 2
    assert not invalid_output.exists()
    engine_error = CalculationResult(
        calculation_result_id="CALC-ERROR",
        status="ENGINE_ERROR",
        formula_id="FAIL",
        formula_version="1.0.0",
    )
    assert _result_exit_code(engine_error) == 3
