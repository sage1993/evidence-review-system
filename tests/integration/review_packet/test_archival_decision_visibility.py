from pathlib import Path

from evidence_review.review_packet.html_renderer import render_review_html

from .test_html_renderer import _decision_form_html, _model, _write_page_assets


def test_archival_download_visibility_is_owned_by_mode_state(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")
    form = _decision_form_html(html)

    assert 'data-download-decision data-archive-only hidden' in form
    assert '.secondary-action:not([hidden]) { display: block; }' in html
    assert 'node.hidden = protectedMode' in html
