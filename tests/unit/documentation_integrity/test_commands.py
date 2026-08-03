"""Static validation tests for documented command blocks."""

from __future__ import annotations

from pathlib import Path

import pytest

from ansim_review.documentation_integrity.commands import (
    CommandLine,
    normalize_command_block,
    validate_cli_tokens,
    validate_command_lines,
)
from ansim_review.documentation_integrity.discovery import DiscoveredDocument
from ansim_review.documentation_integrity.markdown import CommandBlock


def _document(
    root: Path,
    classification: str = "CURRENT",
) -> DiscoveredDocument:
    path = root / "docs" / "guide.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Guide\n", encoding="utf-8")
    return DiscoveredDocument(
        path="docs/guide.md",
        filesystem_path=path.absolute(),
        classification=classification,  # type: ignore[arg-type]
    )


def _validate_text_command(
    command: str,
    tmp_path: Path,
    *,
    language: str = "text",
    classification: str = "CURRENT",
) -> tuple[object, ...]:
    lines = normalize_command_block(
        CommandBlock(language=language, text=command, start_line=1)
    )
    return validate_command_lines(lines, tmp_path, _document(tmp_path, classification))


def _codes(findings: tuple[object, ...]) -> list[str]:
    return [finding.code for finding in findings]  # type: ignore[attr-defined]


def test_normalizes_powershell_continuations_prompts_and_comments() -> None:
    block = CommandBlock(
        language="powershell",
        start_line=10,
        text=(
            "PS C:\\repo> evidence-review source-batch prepare `\n"
            ">> --root \"<path>\" `\n"
            ">> --manifest <path>\n"
            "# ignored\n"
            "$ pytest -q tests\n"
        ),
    )

    assert normalize_command_block(block) == (
        CommandLine(
            tokens=(
                "evidence-review",
                "source-batch",
                "prepare",
                "--root",
                "<path>",
                "--manifest",
                "<path>",
            ),
            line=10,
            raw=(
                "evidence-review source-batch prepare --root \"<path>\" "
                "--manifest <path>"
            ),
        ),
        CommandLine(tokens=("pytest", "-q", "tests"), line=14, raw="pytest -q tests"),
    )


def test_normalizes_posix_continuation_and_multiple_commands() -> None:
    block = CommandBlock(
        language="bash",
        start_line=3,
        text=(
            "$ ruff check src \\\n"
            "  --no-cache && mypy --strict src; python -m compileall -q src\n"
        ),
    )
    assert [line.tokens for line in normalize_command_block(block)] == [
        ("ruff", "check", "src", "--no-cache"),
        ("mypy", "--strict", "src"),
        ("python", "-m", "compileall", "-q", "src"),
    ]


def test_text_blocks_ignore_unrecognized_executables() -> None:
    block = CommandBlock(
        language="text",
        start_line=1,
        text="Status: PASS\necho not-validated\npytest -q tests\n",
    )
    assert [line.tokens for line in normalize_command_block(block)] == [
        ("pytest", "-q", "tests")
    ]


@pytest.mark.parametrize(
    "tokens",
    [
        (
            "evidence-review",
            "source-batch",
            "prepare",
            "--root",
            "<path>",
            "--manifest",
            "<path>",
        ),
        (
            "python",
            "-m",
            "ansim_review",
            "rules",
            "select",
            "--repository-root",
            ".",
            "--manifest",
            "<path>",
            "--context",
            "<path>",
        ),
        ("python", "-m", "evidence_review", "--help"),
        ("evidence-review", "rules", "--help"),
        (
            "evidence-review",
            "documentation",
            "validate",
            "--repository-root",
            ".",
            "--config",
            "documentation-integrity.json",
            "--output",
            "build/report.json",
        ),
    ],
)
def test_valid_project_commands_are_accepted(tokens: tuple[str, ...]) -> None:
    assert validate_cli_tokens(tokens) is None


def test_unknown_subcommand_is_error() -> None:
    error = validate_cli_tokens(
        ("evidence-review", "source-batch", "explode", "--root", ".")
    )
    assert error is not None


@pytest.mark.parametrize(
    "command",
    [
        "pytest -v -k contract --maxfail=1 tests",
        "python -m pytest -q --tb short tests",
        "ruff check --no-cache --select E,F src",
        "python -m ruff check --output-format concise src",
        "mypy --strict --python-version 3.11 src",
        "python -m mypy --show-error-codes src",
        "python -m compileall -q -j 2 src",
    ],
)
def test_bounded_tool_options_are_accepted(command: str, tmp_path: Path) -> None:
    assert _validate_text_command(command, tmp_path) == ()


def test_unknown_tool_option_is_error(tmp_path: Path) -> None:
    findings = _validate_text_command("pytest --unknown-option tests", tmp_path)
    assert _codes(findings) == ["COMMAND_TOOL_OPTION_INVALID"]


def test_recognized_placeholders_are_inert_and_unknown_placeholder_warns(
    tmp_path: Path,
) -> None:
    valid = _validate_text_command(
        "evidence-review source-batch prepare --root ${WORKSPACE} --manifest <path>",
        tmp_path,
    )
    assert valid == ()
    warning = _validate_text_command(
        "evidence-review source-batch prepare --root <workspace> --manifest <path>",
        tmp_path,
    )
    assert _codes(warning) == ["COMMAND_PLACEHOLDER_AMBIGUOUS"]
    assert warning[0].severity == "WARNING"  # type: ignore[attr-defined]


def test_current_missing_script_is_error_but_historical_is_preserved(
    tmp_path: Path,
) -> None:
    current = _validate_text_command("python scripts/missing.py", tmp_path)
    assert _codes(current) == ["COMMAND_SCRIPT_MISSING"]
    historical = _validate_text_command(
        "python scripts/missing.py",
        tmp_path,
        classification="HISTORICAL",
    )
    assert historical == ()


def test_existing_supported_script_invocations_are_accepted(tmp_path: Path) -> None:
    for relative in (
        "scripts/check.py",
        "scripts/check.sh",
        "scripts/check.ps1",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    commands = (
        "python ./scripts/check.py",
        "bash scripts/check.sh",
        "pwsh scripts/check.ps1",
        "powershell -File scripts/check.ps1",
    )
    for command in commands:
        assert _validate_text_command(command, tmp_path) == ()
