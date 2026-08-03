"""Classification precedence tests for documentation integrity."""

from __future__ import annotations

import pytest

from ansim_review.contracts.formats import DOCUMENTATION_INTEGRITY_CONFIG_FORMAT
from ansim_review.documentation_integrity.classification import (
    DocumentClassificationError,
    classify_document,
)
from ansim_review.documentation_integrity.contract import DocumentationIntegrityConfig


def make_config(
    *,
    current_roots: tuple[str, ...] = (),
    historical_roots: tuple[str, ...] = (),
    current_overrides: tuple[str, ...] = (),
    historical_overrides: tuple[str, ...] = (),
) -> DocumentationIntegrityConfig:
    return DocumentationIntegrityConfig(
        format=DOCUMENTATION_INTEGRITY_CONFIG_FORMAT,
        version=1,
        current_roots=current_roots,
        historical_roots=historical_roots,
        current_overrides=current_overrides,
        historical_overrides=historical_overrides,
        generated_documents=(),
    )


def test_more_specific_historical_root_wins() -> None:
    config = make_config(
        current_roots=("docs",),
        historical_roots=("docs/acceptance",),
    )
    assert classify_document("docs/guide.md", config) == "CURRENT"
    assert (
        classify_document("docs/acceptance/issue-48/README.md", config)
        == "HISTORICAL"
    )


def test_current_override_wins_over_historical_default() -> None:
    config = make_config(
        current_roots=("docs",),
        historical_roots=("docs/superpowers/specs",),
        current_overrides=("docs/superpowers/specs/current.md",),
    )
    assert classify_document("docs/superpowers/specs/current.md", config) == "CURRENT"


def test_most_specific_override_wins() -> None:
    config = make_config(
        current_roots=("docs",),
        historical_overrides=("docs/archive",),
        current_overrides=("docs/archive/live",),
    )
    assert classify_document("docs/archive/live/README.md", config) == "CURRENT"


def test_equal_specificity_conflict_fails_closed() -> None:
    config = make_config(
        current_roots=("docs",),
        historical_roots=("docs",),
    )
    with pytest.raises(DocumentClassificationError) as captured:
        classify_document("docs/guide.md", config)
    assert captured.value.code == "CONFIG_CLASSIFICATION_CONFLICT"
    assert captured.value.path == "docs/guide.md"


def test_missing_classification_fails_closed() -> None:
    config = make_config(current_roots=("docs",))
    with pytest.raises(DocumentClassificationError) as captured:
        classify_document("README.md", config)
    assert captured.value.code == "DOCUMENT_CLASSIFICATION_MISSING"


def test_component_boundaries_do_not_match_prefixes() -> None:
    config = make_config(current_roots=("docs",))
    with pytest.raises(DocumentClassificationError):
        classify_document("docs-old/guide.md", config)
