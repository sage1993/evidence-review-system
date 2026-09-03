from __future__ import annotations

from copy import deepcopy

from evidence_review.review_packet.render_case_visual import render_case_visual_review
from evidence_review.review_packet.render_case_visual_lazy import (
    render_case_visual_review as render_lazy_case_visual_review,
)
from tests.unit.review_packet.test_case_visual_renderer import _typed_reference_model

_MACHINE_AUTHORITY_FIELDS = (
    "status",
    "display_status",
    "finalizer_status",
    "human_decision",
    "claims",
    "calculations",
    "rules",
    "confidence",
    "exceptions",
    "conflicts",
    "abstention_reasons",
    "issue_results",
    "missing_inputs",
    "metadata",
    "decision",
    "format",
    "version",
    "case_id",
    "snapshot_sha256",
    "rule_manifest_sha256",
    "formula_manifest_sha256",
    "evidence",
    "drawing_evidence",
    "confirmed_inputs",
    "rule_evaluations",
)


def _authority_snapshot(model: dict[str, object]) -> dict[str, object]:
    return {
        field: deepcopy(model[field])
        for field in _MACHINE_AUTHORITY_FIELDS
        if field in model
    }


def _machine_authority_model() -> dict[str, object]:
    model = _typed_reference_model()
    model.update(
        {
            "status": "READY_FOR_HUMAN_REVIEW",
            "display_status": "READY_FOR_HUMAN_REVIEW",
            "finalizer_status": "READY_FOR_HUMAN_REVIEW",
            "human_decision": None,
            "decision": {
                "allowed_values": [
                    "SATISFIED",
                    "NOT_SATISFIED",
                    "CONDITIONAL",
                    "ADDITIONAL_REVIEW_REQUIRED",
                ],
                "human_decision": None,
                "packet_sha256": "a" * 64,
            },
            "metadata": {"packet_sha256": "a" * 64},
        }
    )
    return model


def test_reference_presentation_pipeline_preserves_machine_authority() -> None:
    model = _machine_authority_model()
    authority_before = _authority_snapshot(model)

    embedded = render_case_visual_review(model)

    assert embedded
    assert _authority_snapshot(model) == authority_before
    assert model["human_decision"] is None

    decision = model["decision"]
    assert isinstance(decision, dict)
    assert decision["human_decision"] is None
    assert decision["packet_sha256"] == "a" * 64

    lazy_model = _machine_authority_model()
    lazy_authority_before = _authority_snapshot(lazy_model)
    lazy = render_lazy_case_visual_review(lazy_model)

    assert lazy
    assert _authority_snapshot(lazy_model) == lazy_authority_before
    assert lazy_model["human_decision"] is None

    for reference_type in ("TEXT", "TABLE", "PDF_PAGE", "IMAGE", "DIAGRAM", "DRAWING"):
        assert f'data-reference-type="{reference_type}"' in embedded
    assert 'data-reference-role="direct"' in embedded
    assert 'data-reference-role="related"' in embedded
    assert "function focusSubjectFinding" in embedded
    assert "function focusReferenceFinding" in embedded
    assert 'data-reference-page-src="./page-images/' in lazy
    assert 'data-reference-page-image' in lazy
    assert 'href="./page-images/' not in lazy
    assert "data:image/png;base64," not in lazy