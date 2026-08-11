"""Repository-wide documentation integrity acceptance gate."""

from __future__ import annotations

import re
import shutil
import tomllib
from pathlib import Path

from ansim_review.documentation_integrity.contract import report_bytes
from ansim_review.documentation_integrity.validator import validate_documentation

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DEPENDENCY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*")


def _copy_documentation_scope(destination: Path) -> None:
    destination.mkdir()
    for filename in ("README.md", "AGENTS.md", "documentation-integrity.json"):
        shutil.copy2(REPOSITORY_ROOT / filename, destination / filename)
    shutil.copytree(REPOSITORY_ROOT / "docs", destination / "docs")
    shutil.copytree(REPOSITORY_ROOT / "skills", destination / "skills")


def _runtime_dependency_names() -> tuple[str, ...]:
    pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    payload = tomllib.loads(pyproject)
    requirements = payload["project"].get("dependencies", [])
    names: list[str] = []
    for requirement in requirements:
        match = _DEPENDENCY_NAME.match(requirement)
        assert match is not None, f"invalid runtime dependency: {requirement}"
        names.append(match.group(0).casefold())
    return tuple(sorted(names))


def test_repository_documentation_has_no_errors() -> None:
    report = validate_documentation(
        REPOSITORY_ROOT,
        REPOSITORY_ROOT / "documentation-integrity.json",
    )
    assert report.status == "PASS", report_bytes(report).decode("utf-8")
    assert report.error_count == 0


def test_readme_documents_each_runtime_python_dependency() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8").casefold()

    for dependency in _runtime_dependency_names():
        message = f"README does not document runtime dependency: {dependency}"
        assert dependency in readme, message
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
