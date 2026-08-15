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

    assert 'data-persisted-decision' in html
    assert 'data-persisted-reviewer' in html
    assert 'data-persisted-reviewed-at' in html
    assert 'data-persisted-decision-value' in html
    assert 'data-persisted-notes' in html
    assert 'data-add-decision' in html
    assert "추가 결정 기록" in html
    assert 'data-decision-editor' in html


def test_review_script_hydrates_persisted_decision_and_refreshes_conflict() -> None:
    repository_root = Path(__file__).parents[3]
    script = (
        repository_root / "src" / "evidence_review" / "review_packet" / "assets" / "review.js"
    ).read_text(encoding="utf-8")

    assert "renderPersistedDecision" in script
    assert "payload.decision_record" in script
    assert "response.status === 409" in script
    assert "await refreshDisplayStatus()" in script
