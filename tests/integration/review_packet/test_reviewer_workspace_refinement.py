import re
from pathlib import Path

from ansim_review.review_packet.html_renderer import render_review_html

from .test_html_renderer import _decision_form_html, _model, _packet_global_review_html, _write_page_assets


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
    assert "근거 1건 · 추가 확인 0건" in html
    assert "근거 1건이 연결되어 최종 검토가 가능한 상태입니다." not in html
    assert status < html.index('id="review-summary"')


def test_missing_answer_uses_neutral_fallback_not_status_explanation(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    model = _reviewer_model()
    model.pop("answer_summary")

    html = render_review_html(model, tmp_path / "pages")

    assert "질문에 대한 결론이 제공되지 않았습니다." in html
    assert "최종 검토가 가능한 상태" not in html


def test_evidence_card_shows_document_clause_page_quote_and_hides_raw_bbox(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_reviewer_model(), tmp_path / "pages")
    citation = re.search(r'<article class="citation.*?</article>', html, re.DOTALL)

    assert citation is not None
    card = citation.group(0)
    assert "서울특별시 도시계획조례" in card
    assert "제51조 제1항 제1호 · p.3" in card
    assert "정확한 &lt;인용문&gt;" in card
    assert "인용 좌표" not in card
    assert 'data-bbox="10.0,20.0,110.0,40.0"' in card
    assert "10.0, 20.0, 110.0, 40.0" not in re.sub(
        r'<[^>]+(?:hidden)[^>]*>.*?</[^>]+>', "", card, flags=re.DOTALL
    )
    assert '<rect x="10.0" y="160.0" width="100.0" height="20.0">' in html

    audit = _packet_global_review_html(html)
    for value in ("CIT-E1", "E1", "REV1", "10.0", "a" * 64):
        assert value in audit


def test_desktop_evidence_workspace_groups_list_viewer_and_decision(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_reviewer_model(), tmp_path / "pages")

    workspace = re.search(r'<section id="evidence-workspace".*?</section>\s*</section>', html, re.DOTALL)
    assert workspace is not None
    evidence_html = workspace.group(0)
    assert 'id="detail-tabs"' in evidence_html
    assert 'id="evidence-viewer"' in evidence_html
    assert evidence_html.index('id="detail-tabs"') < evidence_html.index('id="evidence-viewer"')
    assert "evidence-review-grid" in evidence_html
    assert "grid-template-columns: minmax(320px, 360px) minmax(0, 1fr)" in html
    assert "max-height: min(60vh, 640px)" in html
    assert "position: sticky" in html


def test_section_numbering_and_viewer_labels_follow_reviewer_contract(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_reviewer_model(), tmp_path / "pages")

    for value in ("1. 검토 결과", "2. 판단 근거", "3. 추가 확인", "4. 검토자 의견"):
        assert value not in html
    for value in (">원문</button>", ">근거 강조</button>", ">원문 + 강조</button>"):
        assert value in html


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
    assert 'aria-describedby="notes-help notes-error"' in form
    assert 'id="notes-error"' in form
    assert "notesRequired" in html
    assert "aria-invalid" in html
    assert "#evidence-zoom" in html and "min-height: 44px" in html


def test_protected_and_archive_guidance_are_separate(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    form = _decision_form_html(render_review_html(_reviewer_model(), tmp_path / "pages"))

    assert "검토 결과를 선택하고 필요한 의견을 입력하십시오." in form
    assert "data-protected-only" in form
    assert "data-archive-only" in form
    assert "append-only" not in form
