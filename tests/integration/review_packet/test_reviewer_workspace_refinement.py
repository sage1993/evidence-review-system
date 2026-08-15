import re
from pathlib import Path

from evidence_review.review_packet.html_renderer import render_review_html

from .test_html_renderer import _decision_form_html, _model, _write_page_assets


def _reviewer_model() -> dict[str, object]:
    model = _model()
    model["answer_summary"] = "질문에 대한 실제 검토 결론입니다."
    claims = model["claims"]
    assert isinstance(claims, list) and isinstance(claims[0], dict)
    citations = claims[0]["citations"]
    assert isinstance(citations, list) and isinstance(citations[0], dict)
    citations[0]["document_name"] = "서울특별시 도시계획조례"
    citations[0]["title"] = "제51조 제1항 제1호"
    return model


def test_summary_separates_answer_from_workflow_status(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_reviewer_model(), tmp_path / "pages")

    status = html.index("검토 준비 완료")
    question = html.index("&lt;검토 질문&gt;")
    answer = html.index("질문에 대한 실제 검토 결론입니다.")

    assert question < answer
    assert "근거</dt><dd>1 건" in html
    assert "최종 검토가 가능한 상태입니다." not in html
    assert html.index('id="review-summary"') < status


def test_missing_answer_uses_neutral_fallback_not_status_explanation(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    model = _reviewer_model()
    model.pop("answer_summary")

    html = render_review_html(model, tmp_path / "pages")

    assert "질문에 대한 결론이 제공되지 않았습니다." in html
    assert "최종 검토가 가능한 상태" not in html


def test_evidence_contract_preserves_geometry_and_hides_technical_surface(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_reviewer_model(), tmp_path / "pages")
    citation = re.search(r'<article class="citation.*?</article>', html, re.DOTALL)

    assert citation is not None
    card = citation.group(0)
    assert "정확한 &lt;인용문&gt;" in card
    assert 'data-bbox="10.0,20.0,110.0,40.0"' in card
    assert '<rect x="10.0" y="160.0" width="100.0" height="20.0">' in html
    assert '<details class="citation-audit">' in card
    assert "citation_id" in card
    assert ".visually-hidden" in html
    assert "서울특별시 도시계획조례" in html
    assert "제51조 제1항 제1호" in html


def test_desktop_and_responsive_workspace_contract_is_applied(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_reviewer_model(), tmp_path / "pages")

    assert "grid-template-columns: minmax(280px, 360px) minmax(0, 1fr) minmax(320px, 360px)" in html
    assert '"items viewer decision"' in html
    assert '"detail"' in html
    assert "position: sticky" in html
    assert "@media (max-width: 1100px)" in html
    assert "max-height: min(60vh, 640px)" in html
    assert "position: static" in html


def test_section_numbering_and_viewer_labels_are_rewritten_for_reviewers(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_reviewer_model(), tmp_path / "pages")

    assert 'original: "원문"' in html
    assert 'evidence: "근거 강조"' in html
    assert 'compare: "원문 + 강조"' in html
    assert "applyReviewerLayout" not in html


def test_decision_labels_notes_policy_and_accessibility_contract(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_reviewer_model(), tmp_path / "pages")
    form = _decision_form_html(html)

    for label in (
        "검토 결과에 동의",
        "검토 결과에 오류 있음",
        "조건 충족 시 동의",
        "추가 자료 검토 필요",
    ):
        assert label in form
    assert 'id="review-notes"' in form
    assert 'aria-describedby="decision-notes-error notes-help notes-error"' in form
    assert 'id="notes-error"' in form
    assert "notesRequired" in html
    assert (
        'setAttribute("aria-invalid", required && !notes.value.trim() ? "true" : "false")' in html
    )
    assert "#evidence-zoom" in html
    assert "min-height: 44px" in html


def test_protected_and_archive_guidance_are_separate(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    form = _decision_form_html(render_review_html(_reviewer_model(), tmp_path / "pages"))

    assert "검토 결과를 선택하고 필요한 의견을 입력하십시오." in form
    assert "data-protected-only" in form
    assert "data-archive-only" in form
    assert "append-only" not in form
