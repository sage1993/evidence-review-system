from evidence_review.review_packet.render_summary import visual_shell_css


def test_visual_review_scales_controls_and_findings_for_large_desktop() -> None:
    css = visual_shell_css()

    assert "@media(min-width:2560px)" in css
    assert "minmax(380px,420px)" in css
    assert ".viewer-controls button{width:36px;height:36px}" in css
    assert ".finding-card h3{font-size:15px}" in css
    assert ".comparison-grid dd{font-size:12.5px}" in css


def test_visual_review_adds_true_4k_scale_tier() -> None:
    css = visual_shell_css()

    assert "@media(min-width:3200px)" in css
    assert "minmax(600px,660px)" in css
    assert ".viewer-controls button{width:48px;height:48px}" in css
    assert ".finding-card h3{font-size:18px;margin:10px 0 9px}" in css
    assert ".comparison-grid dd{font-size:15px;line-height:1.45}" in css
    assert ".reference-empty strong{font-size:17px}" in css
    assert ".reference-empty p{max-width:440px;line-height:1.6}" in css
    assert ".decision-open{height:48px;padding:0 16px;font-size:14px}" not in css


def test_visual_review_decision_uses_the_shared_document_flow() -> None:
    css = visual_shell_css()

    assert "transition:none" not in css
    assert (
        'body[data-visual-decision-open="true"]:has(#case-visual-review) #decision-form'
        not in css
    )
    assert "transform:translate(0,-50%)!important" not in css
    assert "pointer-events:auto!important" not in css
    assert "visibility:visible!important" not in css
    assert "opacity:1!important" not in css
