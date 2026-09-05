from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Thread

from evidence_review.review_packet.local_server import create_review_server
from tests.integration.review_packet.test_protected_image_delivery import _get


def _write_scoped_reference_run(
    root: Path,
    *,
    run_id: str,
    revision_id: str,
    page_number: int,
    source_hash: str,
    image_bytes: bytes,
) -> None:
    page_dir = root / "page-images" / revision_id
    page_dir.mkdir(parents=True, exist_ok=True)
    stem = f"page-{page_number:04d}"
    (page_dir / f"{stem}.png").write_bytes(image_bytes)
    (page_dir / f"{stem}.json").write_text(
        json.dumps(
            {
                "format": "evidence-review/page-image",
                "version": 1,
                "revision_id": revision_id,
                "page_number": page_number,
                "source_hash": source_hash,
                "pdf_width": 100.0,
                "pdf_height": 200.0,
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    model = {
        "claims": [
            {
                "citations": [
                    {
                        "revision_id": revision_id,
                        "page_number": page_number,
                        "source_hash": source_hash,
                        "page_width": 100.0,
                        "page_height": 200.0,
                    }
                ]
            }
        ]
    }
    run = root / "runs" / run_id
    run.mkdir(parents=True, exist_ok=True)
    (run / "final-review-packet.json").write_bytes(b"{}")
    (run / "review.html").write_text(
        '<div class="app-shell"></div>'
        '<script id="review-model" type="application/json">'
        + json.dumps(model, sort_keys=True, separators=(",", ":"))
        + "</script>",
        encoding="utf-8",
    )


def test_run_token_cannot_read_another_runs_verified_reference_asset(tmp_path: Path) -> None:
    run_a = "RUN-AAAAAAAAAAAAAAAAAAAA"
    run_b = "RUN-BBBBBBBBBBBBBBBBBBBB"
    token_a = "d" * 43
    token_b = "e" * 43
    hash_a = "1" * 64
    hash_b = "2" * 64
    image_a = b"\x89PNG\r\n\x1a\nrun-a"
    image_b = b"\x89PNG\r\n\x1a\nrun-b"
    _write_scoped_reference_run(
        tmp_path,
        run_id=run_a,
        revision_id="REV-A",
        page_number=1,
        source_hash=hash_a,
        image_bytes=image_a,
    )
    _write_scoped_reference_run(
        tmp_path,
        run_id=run_b,
        revision_id="REV-B",
        page_number=2,
        source_hash=hash_b,
        image_bytes=image_b,
    )

    server = create_review_server(
        tmp_path,
        run_tokens={run_a: token_a, run_b: token_b},
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = _get(
            server,
            f"/runs/{run_a}/{token_a}/page-images/REV-B/2/{hash_b}",
        )
        assert status == 404
        assert image_b not in body

        status, _, delivered = _get(
            server,
            f"/runs/{run_b}/{token_b}/page-images/REV-B/2/{hash_b}",
        )
        assert status == 200
        assert delivered == image_b
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
