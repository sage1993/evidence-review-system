"""Contracts for the presentation-only boundary between review surfaces."""

from __future__ import annotations

import re
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


def test_formal_review_print_typography_overrides_shared_screen_font_size() -> None:
    formal = render_review_html(_formal_model(), page_image_root=Path("."))

    shared_projection = formal.index("/* shared presentation tokens */")
    print_override = formal.index("@media print {", shared_projection)

    assert print_override > shared_projection
    assert "body {\n    font-size: 11pt;" in formal[print_override:]


def test_formal_review_narrow_status_header_wraps_controls_without_vertical_text() -> None:
    formal = render_review_html(_formal_model(), page_image_root=Path("."))
    match = re.search(
        r"@media \(max-width: 700px\) \{(?P<body>.*?)\n\}",
        formal,
        flags=re.DOTALL,
    )

    assert match is not None
    assert ".header-actions {\n    flex-wrap: wrap;\n    min-width: 0;\n  }" in match.group("body")


def test_formal_review_narrow_result_summary_resets_fact_grid_span() -> None:
    formal = render_review_html(_formal_model(), page_image_root=Path("."))
    match = re.search(
        r"@media \(max-width: 700px\) \{(?P<body>.*?)\n\}",
        formal,
        flags=re.DOTALL,
    )

    assert match is not None
    assert ".result-facts {\n    grid-column: auto;\n  }" in match.group("body")


def test_formal_review_print_hides_the_rendered_viewer_toolbar() -> None:
    formal = render_review_html(_formal_model(), page_image_root=Path("."))
    match = re.search(
        r"@media print \{(?P<body>.*?)\n\}",
        formal,
        flags=re.DOTALL,
    )

    assert match is not None
    assert ".viewer-toolbar" in match.group("body")
