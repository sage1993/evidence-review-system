from evidence_review.review_packet.render_case_visual_lazy import render_case_visual_review


def test_lazy_visual_renderer_keeps_non_visual_review_empty() -> None:
    assert render_case_visual_review({"claims": []}) == ""
