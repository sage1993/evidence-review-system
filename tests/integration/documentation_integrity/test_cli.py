"""Create-only documentation integrity CLI integration tests."""

from __future__ import annotations

import json
from pathlib import Path

from ansim_review.documentation_integrity.cli import run_documentation_validation


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _prepare(root: Path, *, broken: bool = False) -> Path:
    target = "missing.md" if broken else "guide.md#guide"
    _write(root / "README.md", f"# Project\n\n[Guide](docs/{target})\n")
    _write(root / "docs" / "guide.md", "# Guide\n")
    _write(
        root / "docs" / "acceptance" / "old.md",
        "> Document status: HISTORICAL RECORD\n\n# Old\n",
    )
    config = root / "documentation-integrity.json"
    config.write_text(
        json.dumps(
            {
                "format": "evidence-review/documentation-integrity-config",
                "version": 1,
                "current_roots": ["README.md", "docs"],
                "historical_roots": ["docs/acceptance"],
                "current_overrides": [],
                "historical_overrides": [],
                "generated_documents": [],
            }
        ),
        encoding="utf-8",
    )
    return config


def test_cli_writes_pass_report_and_stable_summary(
    tmp_path: Path,
    capsys: object,
) -> None:
    config = _prepare(tmp_path)
    output = tmp_path / "build" / "documentation-integrity-report.json"

    exit_code = run_documentation_validation(tmp_path, config, output)

    assert exit_code == 0
    assert output.is_file()
    stdout = capsys.readouterr().out  # type: ignore[attr-defined]
    assert stdout == (
        "Documentation integrity: PASS\n"
        "Documents: 3 current=2 historical=1 generated=0\n"
        "Findings: errors=0 warnings=0\n"
        "Report: build/documentation-integrity-report.json\n"
    )


def test_cli_writes_fail_report_and_returns_one(tmp_path: Path) -> None:
    config = _prepare(tmp_path, broken=True)
    output = tmp_path / "build" / "report.json"

    assert run_documentation_validation(tmp_path, config, output) == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "FAIL"
    assert payload["error_count"] == 1


def test_cli_rejects_existing_output_without_overwrite(tmp_path: Path) -> None:
    config = _prepare(tmp_path)
    output = tmp_path / "report.json"
    output.write_text("preserve", encoding="utf-8")

    assert run_documentation_validation(tmp_path, config, output) == 2
    assert output.read_text(encoding="utf-8") == "preserve"


def test_cli_missing_authority_config_returns_two_without_report(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "README.md", "# Project\n")
    output = tmp_path / "build" / "report.json"

    assert (
        run_documentation_validation(
            tmp_path,
            tmp_path / "missing-config.json",
            output,
        )
        == 2
    )
    assert not output.exists()
