"""Repository-wide documentation integrity acceptance gate."""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

from evidence_review.documentation_integrity.contract import report_bytes
from evidence_review.documentation_integrity.validator import validate_documentation

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _copy_documentation_scope(destination: Path) -> None:
    destination.mkdir()
    for filename in ("README.md", "AGENTS.md", "documentation-integrity.json"):
        shutil.copy2(REPOSITORY_ROOT / filename, destination / filename)
    shutil.copytree(REPOSITORY_ROOT / "docs", destination / "docs")
    shutil.copytree(REPOSITORY_ROOT / "skills", destination / "skills")


def _runtime_dependencies() -> tuple[str, ...]:
    pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    payload = tomllib.loads(pyproject)
    requirements = payload["project"].get("dependencies", [])
    assert isinstance(requirements, list)
    normalized: list[str] = []
    for requirement in requirements:
        assert isinstance(requirement, str)
        normalized.append(requirement.casefold())
    return tuple(sorted(normalized))


def test_repository_documentation_has_no_errors() -> None:
    report = validate_documentation(
        REPOSITORY_ROOT,
        REPOSITORY_ROOT / "documentation-integrity.json",
    )
    assert report.status == "PASS", report_bytes(report).decode("utf-8")
    assert report.error_count == 0


def test_readme_matches_runtime_python_dependency_contract() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8").casefold()

    for requirement in _runtime_dependencies():
        message = f"README does not document runtime dependency: {requirement}"
        assert requirement in readme, message
    assert "외부 python 의존성이 없다" not in readme


def test_repository_report_is_byte_reproducible(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    _copy_documentation_scope(first_root)
    _copy_documentation_scope(second_root)

    first = validate_documentation(
        first_root,
        first_root / "documentation-integrity.json",
    )
    second = validate_documentation(
        second_root,
        second_root / "documentation-integrity.json",
    )

    assert report_bytes(first) == report_bytes(second)
