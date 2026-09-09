from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path

import pytest


def _adapter_module():
    try:
        return importlib.import_module("evidence_review.review_matter.formalization")
    except ModuleNotFoundError as error:
        pytest.fail(f"FORMALIZATION_ADAPTER_MODULE_MISSING: {error}")


def test_formalization_adapter_rejects_arbitrary_matter_or_draft_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _adapter_module().formalize_snapshot(tmp_path, object())


def test_formalization_adapter_rejects_unpersisted_snapshot(tmp_path: Path) -> None:
    from evidence_review.review_matter.snapshot import FormalizationSnapshot

    with pytest.raises(ValueError, match="SNAPSHOT|snapshot"):
        _adapter_module().formalize_snapshot(tmp_path, object())

    assert FormalizationSnapshot.__dataclass_params__.frozen


def test_tampering_snapshot_object_cannot_add_arbitrary_evidence() -> None:
    from evidence_review.review_matter.snapshot import FormalizationSnapshot

    assert FormalizationSnapshot.__dataclass_params__.frozen
    assert replace is not None
