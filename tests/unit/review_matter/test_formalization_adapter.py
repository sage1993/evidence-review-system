from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

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


def test_formalization_confidence_initialization_matches_review_question_pending_states() -> None:
    from evidence_review.review_matter.formalization import _request_document
    from evidence_review.review_question import build_review_run_request

    scope = {
        "format": "evidence-review/review-scope",
        "version": 1,
        "question": "주차장 설치 기준",
        "facts": [],
        "assumptions": [],
        "issues": [
            {
                "id": "I1",
                "question": "주차장 설치 기준은 무엇인가",
                "depends_on": [],
                "required_evidence_roles": ["rule"],
            }
        ],
        "legal_anchors": [],
        "search_requests": [
            {
                "id": "S1",
                "issue_ids": ["I1"],
                "text": "주차장 설치 기준",
                "kind": "phrase",
                "source": "user",
                "role": "rule",
            }
        ],
        "origin": "EXPLICIT_USER",
        "question_plan_sha256": None,
    }
    snapshot = SimpleNamespace(
        evidence_snapshot_hash="a" * 64,
        snapshot_id="SNAP-1",
        matter_id="MATTER-1",
        matter_revision=1,
        selected_evidence=(),
    )

    formal_factors = _request_document(snapshot, {}, scope)["confidence_input"]["factors"]
    question_factors = build_review_run_request(
        {
            "snapshot_hash": "a" * 64,
            "query": {"primary": "주차장 설치 기준"},
            "hits": [],
        }
    )["confidence_input"]["factors"]

    names = (
        "calculation validity",
        "Track B agreement",
        "source freshness",
        "human review status",
    )
    assert {name: formal_factors[name] for name in names} == {
        name: question_factors[name] for name in names
    }
