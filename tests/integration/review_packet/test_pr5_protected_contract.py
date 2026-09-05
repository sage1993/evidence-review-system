from __future__ import annotations

import json
from pathlib import Path
from threading import Thread

import pytest

from evidence_review.review_packet import browser_launcher
from evidence_review.review_packet.local_server import create_review_server
from tests.integration.review_packet.test_protected_image_delivery import (
    CASE_ATTACHMENT_ID,
    REFERENCE_SOURCE_HASH,
    RUN_ID,
    TOKEN,
    VALID_MINIMAL_PNG,
    _case_page,
    _get,
    _reference_page,
    _review_model_from_html,
    _run,
)


def _case_only_review(run: Path, image_sha256: str) -> None:
    model = {
        "run_id": RUN_ID,
        "claims": [],
        "case_visual_review": {
            "pages": [
                {
                    "asset_key": f"{CASE_ATTACHMENT_ID}-p1",
                    "attachment_id": CASE_ATTACHMENT_ID,
                    "page": 1,
                    "image_sha256": image_sha256,
                    "data_uri": "data:image/png;base64,AAAA",
                    "tiles": [],
                }
            ]
        },
    }
    (run / "review.html").write_text(
        '<div class="app-shell"></div>'
        f'<figure class="case-visual-page" data-case-page="{CASE_ATTACHMENT_ID}-p1">'
        '<image data-case-page-image data-case-page-src="data:image/png;base64,AAAA"/>'
        "</figure>"
        '<script id="review-model" type="application/json">'
        + json.dumps(model, sort_keys=True, separators=(",", ":"))
        + "</script>",
        encoding="utf-8",
    )


def test_create_review_server_builds_payload_free_untiled_case_projection(
    tmp_path: Path,
) -> None:
    image_sha256 = _case_page(tmp_path, VALID_MINIMAL_PNG)
    run = tmp_path / "runs" / RUN_ID
    run.mkdir(parents=True)
    (run / "final-review-packet.json").write_bytes(b"{}")
    _case_only_review(run, image_sha256)

    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"/runs/{RUN_ID}/{TOKEN}"
        status, _, body = _get(server, base + "/review")
        assert status == 200
        assert b"data:image/png;base64," not in body
        model = _review_model_from_html(body)
        assert "data_uri" not in model["case_visual_review"]["pages"][0]

        status, _, delivered = _get(
            server,
            base + f"/case-pages/{CASE_ATTACHMENT_ID}/1/{image_sha256}",
        )
        assert status == 200
        assert delivered == VALID_MINIMAL_PNG
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_run_token_rejects_workspace_page_not_referenced_by_that_run(tmp_path: Path) -> None:
    _run(tmp_path, VALID_MINIMAL_PNG)
    unreferenced = b"\x89PNG\r\n\x1a\nunreferenced"
    _reference_page(tmp_path, unreferenced)

    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = _get(
            server,
            f"/runs/{RUN_ID}/{TOKEN}/page-images/REV-REF/12/{REFERENCE_SOURCE_HASH}",
        )
        assert status == 404
        assert unreferenced not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_browser_dispatch_does_not_count_as_http_ready(monkeypatch, tmp_path: Path) -> None:
    run = tmp_path / "runs" / RUN_ID
    run.mkdir(parents=True)

    class FakeServer:
        url = f"http://127.0.0.1:1/runs/{RUN_ID}/{TOKEN}/review"

        def close(self) -> None:
            pass

    monkeypatch.setattr(browser_launcher, "_start_review_server", lambda *args, **kwargs: FakeServer())
    monkeypatch.setattr(browser_launcher, "append_stage", lambda *args, **kwargs: None)

    try:
        with pytest.raises(OSError, match="HTTP ready"):
            browser_launcher.open_protected_review_workspace(
                tmp_path,
                RUN_ID,
                browser=lambda _url: True,
            )
    finally:
        browser_launcher.close_open_review_servers()
