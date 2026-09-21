"""Reference presence is independent of direct-comparison authority."""
from evidence_review.review_packet.render_case_visual import render_case_visual_review
from tests.unit.review_packet.test_case_visual_renderer import _typed_reference_model


def test_related_only_reference_stays_in_left_comparison_pane():
    model = _typed_reference_model()
    finding = model['case_visual_review']['findings'][0]
    finding['direct_reference_anchors'] = []
    html = render_case_visual_review(model)
    assert 'class="reference-viewer"' in html
    assert 'related-reference-fallback' not in html
    assert 'data-reference-width="50"' in html
    assert 'data-case-divider' in html
    assert '관련 자료 — 적용 기준 연결 전' in html
    assert '도면 관찰 항목' in html
    assert '쟁점 탐색' not in html
    assert 'data-findings-toggle' in html
    assert 'data-view-sync' in html
    assert '<dt>기준 연결</dt><dd>아직 연결되지 않음' in html
    assert '<dt>기준</dt>' not in html


def test_no_reference_retains_explicit_left_pane_empty_state():
    model = _typed_reference_model()
    finding = model['case_visual_review']['findings'][0]
    finding.update(direct_reference_anchors=[], related_reference_anchors=[],
                   direct_claim_ids=[], related_claim_ids=[])
    html = render_case_visual_review(model)
    assert 'class="reference-viewer"' in html
    assert '기준 연결 전' in html
    assert '기준 비교 창을 숨겼습니다' not in html
