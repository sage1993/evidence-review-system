from evidence_review.review_packet.quote_presentation import quote_preview, render_quote
from evidence_review.review_packet.render_case_visual import (
    _reference_anchor_content,
    render_case_visual_review,
)
from tests.unit.review_packet.test_case_visual_renderer import _model, _typed_reference_model


def test_visual_viewer_exposes_direct_page_navigation_and_selection_legend():
    html = render_case_visual_review(_model())
    assert 'aria-label="페이지 번호"' in html
    assert 'data-case-page-jump' in html
    assert '빨간 강조: 선택한 관찰 위치' in html


def test_reference_has_keyboard_operable_large_viewer():
    html = render_case_visual_review(_typed_reference_model())
    assert 'data-reference-expand' in html
    assert '원문 크게 보기' in html


def test_table_quote_uses_the_highlighted_original_instead_of_parser_coordinates():
    anchor = {
        "type": "TABLE", "document_name": "기준", "page": 1,
        "quote": "행 1 열 1: 항목 | 행 1 열 3: 기준 | 행 2 열 1: 면적 | 행 2 열 3: 20㎡",
    }
    html, _ = _reference_anchor_content(anchor, {})
    assert '<table' not in html
    assert '행 1 열 1:' not in html
    assert '원문에서 강조된 표 위치를 확인하세요.' in html


def test_table_quote_preview_does_not_expose_parser_coordinates():
    quote = "행 1 열 1: 항목 | 행 1 열 3: 기준 | 행 2 열 1: 면적 | 행 2 열 3: 20㎡"
    assert quote_preview(quote) == "원문 표의 강조 위치를 확인하세요."


def test_table_presentation_does_not_expose_untrusted_parser_cells():
    quote = '행 1 열 1: <img src=x onerror=alert(1)> | 행 2 열 1: 20㎡'
    html = render_quote(quote)
    assert '<img' not in html
    assert 'onerror' not in html
    assert '행 1 열 1:' not in html


def test_partial_cell_syntax_uses_the_original_highlight_instead_of_parser_text():
    quote = '행 1 열 1: 항목 | 설명은 표 좌표가 아닙니다'
    html = render_quote(quote)
    assert '<table' not in html
    assert quote not in html
    assert '원문에서 강조된 표 위치를 확인하세요.' in html


def test_recorded_decision_cannot_hide_visual_abstention_notice():
    model = _model()
    model.update(status="ABSTAIN", display_status="REVIEW_COMPLETED")
    html = render_case_visual_review(model)
    assert 'class="visual-abstain"' in html
