from __future__ import annotations

import re
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from evidence_review.review_packet.html_renderer import render_review_html

from .test_html_renderer import _decision_form_html, _model, _write_page_assets


def _installed_version() -> str:
    try:
        return version("evidence-review-system")
    except PackageNotFoundError:
        return "development"


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
    assert "max-height: none !important" in html


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
    assert "data-page-select" in html
    assert "data-page-prev" in html
    assert "data-page-next" in html
    assert "PDF" in html


def test_reference_decision_panel_has_image_matched_notes_counter(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert 'class="decision-note-footer"' in html
    assert "data-notes-count" in html
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


def test_issue_89_layout_has_no_late_fixed_frame_override(tmp_path: Path) -> None:
    """The reviewer workspace must remain responsive instead of using a P0 frame overlay."""
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert "/* P0 fidelity corrections for the 1536 × 1024 reference surface. */" not in html
    assert "height: 591px" not in html
    assert "height: 531px" not in html
    assert "height: 491px" not in html
    assert "grid-template-columns: minmax(280px, 360px) minmax(0, 1fr) minmax(320px, 360px)" in html
    assert '"items viewer decision"' in html
    assert "max-height: min(60vh, 640px)" in html
    assert "max-height: none !important" in html

def test_p0_audit_and_footer_use_reference_labels(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert "감사 정보" in html
    assert "Evidence Review System" in html
    assert f"v{_installed_version()}" in html
    assert "data-packet-hash" not in html
    assert "data-created-at" in html


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

    assert "focusEvidence(item.dataset.itemId, item.dataset.evidenceId)" in controller
    focus_start = controller.index("function focusEvidence")
    focus_end = controller.find("\n  function ", focus_start + 1)
    assert focus_end > focus_start
    assert "setActivePage(assetKey);" in controller[focus_start:focus_end]
    assert "data-asset-key=" in render_review_html(_model(), tmp_path / "pages")


def test_multi_citation_cards_preserve_each_identity_and_focus_target(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    model = _model()
    claims = model["claims"]
    assert isinstance(claims, list) and isinstance(claims[0], dict)
    citations = claims[0]["citations"]
    assert isinstance(citations, list) and isinstance(citations[0], dict)
    citations.append(
        {
            **citations[0],
            "citation_id": "CIT-E2",
            "evidence_id": "E2",
            "bbox": [20.0, 30.0, 100.0, 50.0],
            "evidence_type": "table",
        }
    )

    html = render_review_html(model, tmp_path / "pages")
    nav = re.search(r'<nav id="review-items".*?</nav>', html, re.DOTALL)
    assert nav is not None
    assert nav.group(0).count('class="review-item evidence-card') == 2
    assert 'data-evidence-id="E1"' in nav.group(0)
    assert 'data-evidence-id="E2"' in nav.group(0)
    assert html.count('class="citation"') == 2
    assert html.count('class="citation-overlay"') == 2

    controller = _inline_controller(html)
    assert "focusEvidence(item.dataset.itemId, item.dataset.evidenceId)" in controller


def test_evidence_type_pill_uses_canonical_value_and_hides_unknown_types(tmp_path: Path) -> None:
    known = _model()
    known["claims"][0]["citations"][0]["evidence_type"] = "clause"
    _write_page_assets(tmp_path / "known-pages")
    known_html = render_review_html(known, tmp_path / "known-pages")
    assert "조항 근거" in known_html
    assert "직접 근거" not in known_html

    unknown = _model()
    unknown["claims"][0]["citations"][0]["evidence_type"] = "unsupported"
    _write_page_assets(tmp_path / "unknown-pages")
    unknown_html = render_review_html(unknown, tmp_path / "unknown-pages")
    nav = re.search(r'<nav id="review-items".*?</nav>', unknown_html, re.DOTALL)
    assert nav is not None
    assert 'class="evidence-type-pill"' not in nav.group(0)
