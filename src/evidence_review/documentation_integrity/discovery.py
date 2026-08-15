"""Deterministic discovery of repository Markdown documentation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from evidence_review.documentation_integrity.classification import classify_document
from evidence_review.documentation_integrity.contract import (
    DocumentationIntegrityConfig,
    DocumentClassification,
)


class DocumentDiscoveryError(ValueError):
    """Raised when an in-scope Markdown path is unsafe or non-regular."""

    def __init__(self, code: str, path: str) -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code}: {path}")


@dataclass(frozen=True, slots=True)
class DiscoveredDocument:
    path: str
    filesystem_path: Path
    classification: DocumentClassification


def _candidate_paths(root: Path) -> set[Path]:
    candidates: set[Path] = set()
    for name in ("README.md", "AGENTS.md"):
        candidate = root / name
        if candidate.exists() or candidate.is_symlink():
            candidates.add(candidate)
    docs = root / "docs"
    if docs.exists():
        candidates.update(docs.rglob("*.md"))
    skills = root / "skills"
    if skills.exists():
        candidates.update(skills.rglob("SKILL.md"))
    return candidates


def _validate_candidate(root: Path, candidate: Path, path: str) -> None:
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise DocumentDiscoveryError("DOCUMENT_NOT_REGULAR", path) from error
    if candidate.is_symlink() and not resolved.is_relative_to(root):
        raise DocumentDiscoveryError("DOCUMENT_SYMLINK_ESCAPE", path)
    if not resolved.is_file():
        raise DocumentDiscoveryError("DOCUMENT_NOT_REGULAR", path)


def discover_repository_documents(
    repository_root: Path,
    config: DocumentationIntegrityConfig,
) -> tuple[DiscoveredDocument, ...]:
    """Discover, validate, classify, and bytewise-sort in-scope Markdown."""
    root = repository_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository root must be a directory")
    documents: list[DiscoveredDocument] = []
    for candidate in _candidate_paths(root):
        path = candidate.relative_to(root).as_posix()
        _validate_candidate(root, candidate, path)
        documents.append(
            DiscoveredDocument(
                path=path,
                filesystem_path=candidate.absolute(),
                classification=classify_document(path, config),
            )
        )
    return tuple(
        sorted(documents, key=lambda item: item.path.encode("utf-8"))
    )
