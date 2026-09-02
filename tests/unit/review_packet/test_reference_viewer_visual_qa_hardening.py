from evidence_review.review_packet.render_summary import render_additional_review
from tests.unit.review_packet.test_case_visual_renderer import _model


def test_visual_review_scales_controls_and_findings_for_large_desktop() -> None:
    html = render_additional_review(_model())

    assert "@media(min-width:2560px)" in html
    assert "minmax(380px,420px)" in html
    assert ".viewer-controls button{width:36px;height:36px}" in html
    assert ".finding-card h3{font-size:15px}" in html
    assert ".comparison-grid dd{font-size:12.5px}" in html


def test_visual_review_adds_true_4k_scale_tier() -> None:
    html = render_additional_review(_model())

    assert "@media(min-width:3200px)" in html
    assert "minmax(600px,660px)" in html
    assert ".viewer-controls button{width:48px;height:48px}" in html
    assert ".finding-card h3{font-size:18px}" in html
    assert ".comparison-grid dd{font-size:15px}" in html
    assert ".reference-empty strong{font-size:17px}" in html
    assert ".reference-empty p{max-width:440px" in html
    assert ".decision-open{height:48px" in html


def test_visual_review_decision_drawer_open_state_is_atomic_and_visible() -> None:
    html = render_additional_review(_model())

    assert "transition:none" in html
    assert 'body[data-visual-decision-open="true"]:has(#case-visual-review) #decision-form' in html
    assert "transform:translate(0,-50%)!important" in html
    assert "pointer-events:auto!important" in html
    assert "visibility:visible!important" in html
    assert "opacity:1!important" in html
