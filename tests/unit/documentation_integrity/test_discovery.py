"""Repository documentation discovery tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from evidence_review.contracts.formats import DOCUMENTATION_INTEGRITY_CONFIG_FORMAT
from evidence_review.documentation_integrity.contract import DocumentationIntegrityConfig
from evidence_review.documentation_integrity.discovery import (
    DocumentDiscoveryError,
    discover_repository_documents,
)


def make_config() -> DocumentationIntegrityConfig:
    return DocumentationIntegrityConfig(
        format=DOCUMENTATION_INTEGRITY_CONFIG_FORMAT,
        version=1,
        current_roots=("README.md", "AGENTS.md", "docs", "skills"),
        historical_roots=("docs/acceptance",),
        current_overrides=(),
        historical_overrides=(),
        generated_documents=(),
    )


def write(path: Path, text: str = "# Document\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_discovery_includes_only_approved_scope_and_sorts_bytewise(
    tmp_path: Path,
) -> None:
    write(tmp_path / "README.md")
    write(tmp_path / "AGENTS.md")
    write(tmp_path / "docs" / "guide.md")
    write(tmp_path / "docs" / "zeta" / "nested.md")
    write(tmp_path / "docs" / "acceptance" / "old.md")
    write(tmp_path / "skills" / "alpha" / "SKILL.md")
    write(tmp_path / "skills" / "beta" / "nested" / "SKILL.md")
    write(tmp_path / "skills" / "alpha" / "OTHER.md")
    write(tmp_path / "notes" / "ignored.md")
    write(tmp_path / "docs" / "ignored.txt")

    documents = discover_repository_documents(tmp_path, make_config())

    assert [document.path for document in documents] == [
        "AGENTS.md",
        "README.md",
        "docs/acceptance/old.md",
        "docs/guide.md",
        "docs/zeta/nested.md",
        "skills/alpha/SKILL.md",
        "skills/beta/nested/SKILL.md",
    ]
    assert documents[2].classification == "HISTORICAL"
    assert all(document.filesystem_path.is_absolute() for document in documents)


def test_discovery_rejects_symlink_escaping_repository(tmp_path: Path) -> None:
    write(tmp_path / "README.md")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    link = tmp_path / "docs" / "escape.md"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")

    with pytest.raises(DocumentDiscoveryError) as captured:
        discover_repository_documents(tmp_path, make_config())
    assert captured.value.code == "DOCUMENT_SYMLINK_ESCAPE"
    assert captured.value.path == "docs/escape.md"


def test_discovery_rejects_non_regular_markdown_path(tmp_path: Path) -> None:
    write(tmp_path / "README.md")
    (tmp_path / "docs" / "directory.md").mkdir(parents=True)

    with pytest.raises(DocumentDiscoveryError) as captured:
        discover_repository_documents(tmp_path, make_config())
    assert captured.value.code == "DOCUMENT_NOT_REGULAR"
