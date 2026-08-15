"""Deterministic current and historical document classification."""
from __future__ import annotations

from evidence_review.documentation_integrity.contract import (
    DocumentationIntegrityConfig,
    DocumentClassification,
)


class DocumentClassificationError(ValueError):
    """Raised when a document cannot be classified unambiguously."""

    def __init__(self, code: str, path: str) -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code}: {path}")


def _component_count(path: str) -> int:
    return len(path.split("/"))


def _matches(path: str, scope: str) -> bool:
    return path == scope or path.startswith(f"{scope}/")


def _best_specificity(path: str, scopes: tuple[str, ...]) -> int | None:
    matches = (
        _component_count(scope)
        for scope in scopes
        if _matches(path, scope)
    )
    return max(matches, default=None)


def _resolve_group(
    path: str,
    current_scopes: tuple[str, ...],
    historical_scopes: tuple[str, ...],
) -> DocumentClassification | None:
    current = _best_specificity(path, current_scopes)
    historical = _best_specificity(path, historical_scopes)
    if current is None and historical is None:
        return None
    if current is not None and historical is not None and current == historical:
        raise DocumentClassificationError("CONFIG_CLASSIFICATION_CONFLICT", path)
    if historical is None or (current is not None and current > historical):
        return "CURRENT"
    return "HISTORICAL"


def classify_document(
    path: str,
    config: DocumentationIntegrityConfig,
) -> DocumentClassification:
    """Classify one canonical repository or virtual document path."""
    override = _resolve_group(
        path,
        config.current_overrides,
        config.historical_overrides,
    )
    if override is not None:
        return override
    root = _resolve_group(path, config.current_roots, config.historical_roots)
    if root is None:
        raise DocumentClassificationError("DOCUMENT_CLASSIFICATION_MISSING", path)
    return root
