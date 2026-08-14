from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ansim_review.review_packet.html_renderer import render_review_html

from .test_html_renderer import _decision_form_html, _model, _write_page_assets


def _inline_controller(html: str) -> str:
    scripts = re.findall(r"<script(?: [^>]*)?>(.*?)</script>", html, re.DOTALL)
    assert scripts
    return scripts[-1]


def test_image_matched_workspace_contract_has_three_columns_and_reference_hierarchy(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert "정식 근거 검토" in html
    assert "결론" in html
    assert "판단 근거" in html
    assert 'id="evidence-viewer"' in html
    assert 'id="decision-form"' in html
    assert "grid-template-columns: minmax(280px, 360px) minmax(0, 1fr) minmax(320px, 360px)" in html
    assert "items viewer decision" in html
    assert '"additional additional additional"' in html
    assert "max-height: min(60vh, 640px)" in html

def test_reference_layout_has_evidence_column_above_pdf_and_decision_column(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert 'id="review-items"' in html
    assert 'class="evidence-card' in html
    assert 'class="result-question-block"' in html
    assert 'class="result-conclusion-block"' in html
    assert '"additional additional additional"' in html
    assert '"items viewer decision"' in html
    assert "items viewer decision" in html


def test_reference_pdf_viewer_has_toolbar_thumbnail_rail_and_page_controls(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert 'class="thumbnail-rail"' in html
    assert 'data-page-select' in html
    assert 'data-page-prev' in html
    assert 'data-page-next' in html
    assert "PDF" in html


def test_reference_decision_panel_has_image_matched_notes_counter(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert 'class="decision-note-footer"' in html
    assert 'data-notes-count' in html
    assert "1,000" in html


def test_evidence_cards_show_document_name_clause_page_quote_and_keep_audit_collapsed(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    model = _model()
    model["claims"][0]["citations"][0]["document_name"] = "서울특별시 도시계획조례"
    html = render_review_html(model, tmp_path / "pages")

    assert "서울특별시 도시계획조례" in html
    assert "제3조" in html
    assert "페이지 3" in html
    assert "정확한 &lt;인용문&gt;" in html
    assert 'class="citation-audit"' in html
    assert 'data-bbox="10.0,20.0,110.0,40.0"' in html


def test_decision_notes_are_optional_only_for_satisfied_and_have_aria_error_contract(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    form = _decision_form_html(render_review_html(_model(), tmp_path / "pages"))

    assert 'data-notes-required-for="NOT_SATISFIED CONDITIONAL ADDITIONAL_REVIEW_REQUIRED"' in form
    assert 'aria-describedby="decision-notes-error notes-help notes-error"' in form
    assert 'id="decision-notes-error"' in form
    assert 'aria-invalid="false"' in form
    assert 'name="notes"' in form


def test_browser_controller_contains_keyboard_evidence_and_notes_validation(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    controller = _inline_controller(render_review_html(_model(), tmp_path / "pages"))

    assert "focusEvidence" in controller
    assert 'event.key !== "Enter"' in controller
    assert 'event.key !== " "' in controller
    assert "aria-invalid" in controller
    assert "decision-notes-error" in controller

    completed = subprocess.run(
        ["node", "-e", "new Function(process.argv[1])", controller],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

def test_p0_frame_and_grid_match_reference_geometry_contract(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert "width: calc(100% - 16px)" in html
    assert "max-width: 1520px" in html
    assert "margin: 8px auto" in html
    assert "grid-template-columns: 392px minmax(0, 1fr) 342px" in html
    assert "column-gap: 14px" in html
    assert "row-gap: 16px" in html


def test_p0_audit_and_footer_use_reference_labels(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert "감사 정보" in html
    assert "Evidence Review System" in html
    assert "v1.0.0" in html
    assert 'data-packet-hash' in html
    assert 'data-created-at' in html


def test_p0_decision_options_render_one_radio_control_each(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")
    form = _decision_form_html(html)

    assert 'class="radio-mark"' not in form
    assert form.count('type="radio"') == 4


def test_reference_pdf_thumbnails_render_verified_page_images(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert 'class="page-thumb-image"' in html
    assert html.count('class="page-thumb-image"') == 1
    assert 'aria-label="' in html


def test_reference_icons_are_inline_svg_assets_not_text_glyphs(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert 'class="icon icon-printer"' in html
    assert 'class="icon icon-file-text"' in html
    assert 'class="icon icon-info"' in html
    assert 'class="icon icon-lock"' in html
    assert 'class="icon icon-check"' in html
    assert 'class="icon icon-search"' in html
    assert '<span class="evidence-doc-icon" aria-hidden="true">?</span>' not in html
    assert '<button type="button" data-print>?' not in html


def test_evidence_list_scrolls_inside_fixed_reference_panel(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert ".review-item-list {" in html
    assert "overflow-y: auto" in html
    assert "min-height: 0" in html


def test_evidence_card_focuses_its_pdf_page_in_browser_controller(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    controller = _inline_controller(render_review_html(_model(), tmp_path / "pages"))

    assert 'focusEvidence(item.dataset.itemId)' in controller
    focus_start = controller.index('function focusEvidence')
    focus_end = controller.index('function setActivePage')
    assert 'setActivePage(assetKey);' in controller[focus_start:focus_end]
    assert 'data-asset-key=' in render_review_html(_model(), tmp_path / "pages")
