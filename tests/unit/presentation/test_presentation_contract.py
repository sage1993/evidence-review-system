"""Contracts for the presentation-only boundary between review surfaces."""

from __future__ import annotations

from pathlib import Path

from evidence_review.presentation.tokens import presentation_tokens
from evidence_review.review_packet.html_renderer import render_review_html
from evidence_review.workbench.html_renderer import render_workbench_html


def _formal_model() -> dict[str, object]:
    return {
        "run_id": "RUN-PRESENTATION-001",
        "status": "READY_FOR_HUMAN_REVIEW",
        "display_status": "READY_FOR_HUMAN_REVIEW",
        "human_decision": None,
        "question": "Is the rendered review authority-distinct?",
        "answer_summary": "Ready for human review.",
        "claims": [],
        "calculations": [],
        "rules": [],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "abstention_reasons": [],
        "issue_results": [],
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
        "metadata": {},
        "summary": {
            "citation_count": 0,
            "missing_input_count": 0,
            "exception_count": 0,
            "conflict_count": 0,
        },
    }


def _workbench_model() -> dict[str, object]:
    return {
        "surface": "workbench",
        "matter_id": "MATTER-PRESENTATION-001",
        "title": "Presentation boundary",
        "revision": 1,
        "issues": [],
        "evidence": [],
        "navigation": None,
        "draft_observations": [],
        "formal_run_history": [],
        "formalize": {
            "expected_revision": 1,
            "enabled": False,
            "blockers": [],
            "confirmation_label": "Formalize this Matter revision.",
        },
    }


def test_shared_visual_tokens_do_not_collapse_surface_authority() -> None:
    tokens = presentation_tokens()

    assert tokens == presentation_tokens()
    assert tokens["control_height_px"] >= 36
    assert set(tokens).isdisjoint({"matter", "packet", "route", "state"})

    formal = render_review_html(_formal_model(), page_image_root=Path("."))
    workbench = render_workbench_html(_workbench_model())

    assert f'--ers-control-height: {tokens["control_height_px"]}px;' in formal
    assert f'--ers-control-height: {tokens["control_height_px"]}px;' in workbench
    assert "button,\ninput {\n  font: inherit;\n}" in workbench
    assert 'data-surface="formal-review"' in formal
    assert 'data-surface="workbench"' in workbench
    assert "human-decision" in formal
    assert "human-decision" not in workbench
