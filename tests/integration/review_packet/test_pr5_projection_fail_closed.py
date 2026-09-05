from __future__ import annotations

from pathlib import Path
from threading import Thread

from evidence_review.review_packet.local_server import create_review_server
from tests.integration.review_packet.test_protected_image_delivery import (
    RUN_ID,
    TOKEN,
    _get,
)


def test_review_route_fails_closed_when_protected_projection_cannot_be_built(
    tmp_path: Path,
) -> None:
    run = tmp_path / "runs" / RUN_ID
    run.mkdir(parents=True)
    (run / "final-review-packet.json").write_bytes(b"{}")
    (run / "review.html").write_text(
        '<div class="app-shell"></div>'
        '<img src="data:image/png;base64,AAAA">',
        encoding="utf-8",
    )

    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = _get(
            server,
            f"/runs/{RUN_ID}/{TOKEN}/review",
        )
        assert status == 404
        assert b"data:image/png;base64," not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
