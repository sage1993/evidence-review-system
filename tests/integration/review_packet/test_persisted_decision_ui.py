from __future__ import annotations

from pathlib import Path

from evidence_review.review_packet.render_decision import render_decision_form


def _model() -> dict[str, object]:
    return {
        "decision": {
            "allowed_values": [
                "SATISFIED",
                "NOT_SATISFIED",
                "CONDITIONAL",
                "ADDITIONAL_REVIEW_REQUIRED",
            ],
            "human_decision": None,
            "packet_sha256": "a" * 64,
        }
    }


def test_decision_panel_has_readonly_persisted_state_and_explicit_append_action() -> None:
    html = render_decision_form(_model())

    assert '<section id="decision-form" aria-labelledby="decision-heading">' in html
    assert '<section id="decision-form" aria-hidden="true"' not in html
    assert 'data-persisted-decision' in html
    assert 'data-persisted-reviewer' in html
    assert 'data-persisted-reviewed-at' in html
    assert 'data-persisted-decision-value' in html
    assert 'data-persisted-notes' in html
    assert 'data-add-decision' in html
    assert "추가 결정 기록" in html
    assert 'data-decision-editor' in html


def test_drawing_decision_panel_can_start_hidden_without_changing_default_markup() -> None:
    html = render_decision_form(_model(), initially_hidden=True)

    assert (
        '<section id="decision-form" aria-hidden="true" aria-labelledby="decision-heading">'
        in html
    )


def test_review_script_hydrates_persisted_decision_and_refreshes_conflict() -> None:
    repository_root = Path(__file__).parents[3]
    script = (
        repository_root / "src" / "evidence_review" / "review_packet" / "assets" / "review.js"
    ).read_text(encoding="utf-8")

    assert "renderPersistedDecision" in script
    assert "payload.decision_record" in script
    assert "response.status === 409" in script
    assert "await refreshDisplayStatus()" in script


def test_decision_form_collects_explicit_reviewer_id_without_browser_prompt() -> None:
    html = render_decision_form(_model())
    script = (
        Path(__file__).parents[3]
        / "src"
        / "evidence_review"
        / "review_packet"
        / "assets"
        / "review.js"
    ).read_text(encoding="utf-8")

    assert 'id="decision-reviewer-id"' in html
    assert 'name="reviewer_id"' in html
    assert 'pattern="[A-Za-z0-9][A-Za-z0-9._-]{0,127}"' in html
    assert '"#decision-reviewer-id"' in script
    assert "window.prompt" not in script
