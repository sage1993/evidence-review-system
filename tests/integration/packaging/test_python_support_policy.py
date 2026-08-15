from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_python_support_policy_is_313_only() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert data["project"]["version"] == "0.2.0"
    assert data["project"]["requires-python"] == ">=3.13,<3.14"
    assert data["tool"]["ruff"]["target-version"] == "py313"
    assert data["tool"]["mypy"]["python_version"] == "3.13"


def test_current_user_docs_do_not_require_python_311() -> None:
    current_docs = (
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        ROOT / "docs" / "CODEX_WORKFLOW.md",
        ROOT / "docs" / "OFFLINE_EXECUTION.md",
    )
    prohibited = ("py -3.11", "python3.11", "Python 3.11/3.13")

    for path in current_docs:
        text = path.read_text(encoding="utf-8")
        for token in prohibited:
            assert token not in text, f"{path.relative_to(ROOT)} still contains {token!r}"
