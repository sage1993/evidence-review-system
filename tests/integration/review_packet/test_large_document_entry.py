"""Canonical entry size and protected-server compatibility for 130 pages."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from evidence_review.review_packet.html_renderer import write_protected_review_entry
from evidence_review.review_packet.protected_projection import load_archive_review_model
from tests.integration.review_packet.test_protected_review_readiness import (
    RUN_ID,
    TOKEN,
    VALID_MINIMAL_PNG,
    _case_model,
    _get,
    _read_port,
    _start_server,
)
from tests.integration.review_packet.verified_transport_fixture import (
    install_visual_authority,
)


def test_130_page_entry_is_small_and_served_only_through_protected_route(
    tmp_path: Path,
) -> None:
    model = _case_model(hashlib.sha256(VALID_MINIMAL_PNG).hexdigest())
    visual = model["case_visual_review"]
    template = visual["pages"][0]
    pages = []
    for number in range(1, 131):
        page = copy.deepcopy(template)
        page.update(asset_key=f"ATT-UNTILED-p{number}", page=number)
        page.pop("data_uri")
        pages.append(page)
    visual["pages"] = pages
    page_directory = tmp_path / "case-page-images-hq-v1" / "ATT-UNTILED"
    page_directory.mkdir(parents=True)
    for number in range(1, 131):
        (page_directory / f"page-{number:04d}.png").write_bytes(VALID_MINIMAL_PNG)
    install_visual_authority(tmp_path, model)
    entry = tmp_path / "runs" / RUN_ID / "review.html"
    entry.unlink()
    write_protected_review_entry(model, tmp_path / "page-images", entry)
    original = entry.read_bytes()
    assert len(original) <= 10 * 1024 * 1024
    assert b"data:image/" not in original
    assert b"<img" not in original
    assert b"PROTECTED_REVIEW_REQUIRED" in original
    assert len(load_archive_review_model(original)["case_visual_review"]["pages"]) == 130

    process = _start_server(tmp_path)
    try:
        port = _read_port(process)
        status, body = _get(port, f"/runs/{RUN_ID}/{TOKEN}/review")
        assert status == 200
        assert len(body) <= 5 * 1024 * 1024
        assert b"data:image/" not in body
        assert b'data-review-shell="unified"' in body
        denied, _ = _get(port, f"/runs/{RUN_ID}/{'x' * 43}/review")
        assert denied == 403
        assert entry.read_bytes() == original
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
