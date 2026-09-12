from __future__ import annotations

import re
import tomllib
from pathlib import Path

from packaging.version import Version

from ansim_review import __version__

ROOT = Path(__file__).resolve().parents[3]


def test_python_support_policy_is_313_only() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert data["project"]["version"] == "0.2.0rc1"
    assert __version__ == data["project"]["version"]
    assert Version(data["project"]["version"]).is_prerelease
    assert data["project"]["requires-python"] == ">=3.13,<3.14"
    assert data["tool"]["ruff"]["target-version"] == "py313"
    assert data["tool"]["mypy"]["python_version"] == "3.13"


def test_pypdf_security_floor_is_617_or_newer_within_major_6() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]

    assert "pypdf>=6.17,<7" in dependencies


def test_pillow_security_floor_is_123_or_newer_within_major_12() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]

    assert "Pillow>=12.3,<13" in dependencies


def test_current_user_docs_do_not_require_python_311_or_browser_zoom() -> None:
    current_docs = (
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "docs" / "CODEX_WORKFLOW.md",
        ROOT / "docs" / "OFFLINE_EXECUTION.md",
        ROOT / "docs" / "MANUAL_ACCEPTANCE_POLICY.md",
        ROOT / "docs" / "REVIEWER_WORKFLOW.md",
        ROOT / "skills" / "ers-pdf" / "SKILL.md",
        ROOT / "skills" / "ers-review" / "SKILL.md",
    )
    prohibited = (
        "py -3.11",
        "python3.11",
        "Python 3.11/3.13",
        "Python 3.11 and Python 3.13",
        "200% zoom",
        "browser zoom 200%",
    )

    for path in current_docs:
        text = path.read_text(encoding="utf-8")
        for token in prohibited:
            assert token not in text, f"{path.relative_to(ROOT)} still contains {token!r}"


def test_pep639_apache_license_metadata_is_declared_and_present() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert data["build-system"]["requires"] == ["setuptools>=77.0.3"]
    assert data["project"]["license"] == "Apache-2.0"
    assert data["project"]["license-files"] == ["LICENSE"]
    assert not any(
        classifier.startswith("License ::")
        for classifier in data["project"]["classifiers"]
    )

    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in license_text
    assert "Version 2.0" in license_text


def test_release_state_documents_match_source_version() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    release_policy = (ROOT / "docs" / "RELEASE_VERSION_POLICY.md").read_text(
        encoding="utf-8"
    )
    docs_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "0.2.0rc1" in changelog
    assert not re.search(r"^## \[0\.2\.0\] - ", changelog, re.MULTILINE)
    assert "Current source metadata version: `0.2.0rc1`" in readme
    assert "unpublished release candidate" in readme.lower()
    assert "0.2.0rc1" in security
    assert "latest official release" in security.lower()
    assert "Unreleased PEP 440 release candidate; not an official release." in pyproject
    assert "pyproject.toml" in release_policy
    assert "GitHub Release" in release_policy
    assert "exact validated commit" in release_policy
    assert "RELEASE_VERSION_POLICY.md" in docs_index
