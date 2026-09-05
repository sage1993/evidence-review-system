from __future__ import annotations

import hashlib
import http.client
import json
import re
from pathlib import Path
from threading import Thread

from evidence_review.review_packet.case_visual_asset_server import (
    configure_case_visual_server,
)
from evidence_review.review_packet.html_renderer import render_review_html
from evidence_review.review_packet.local_server import create_review_server
from tests.integration.review_packet.test_review_workspace_performance import (
    VALID_MINIMAL_PNG,
)

RUN_ID = "RUN-0123456789ABCDEF0123"
TOKEN = "b" * 43
SOURCE_HASH = "a" * 64
REFERENCE_SOURCE_HASH = "c" * 64
CASE_ATTACHMENT_ID = "ATT-1"


def _model() -> dict[str, object]:
    return {
        "run_id": RUN_ID,
        "status": "READY_FOR_HUMAN_REVIEW",
        "display_status": "READY_FOR_HUMAN_REVIEW",
        "question": "protected image delivery",
        "claims": [
            {
                "claim_id": "C1",
                "text": "근거 주장",
                "citations": [
                    {
                        "citation_id": "CIT-E1",
                        "evidence_id": "E1",
                        "document_id": "DOC1",
                        "document_name": "source.pdf",
                        "revision_id": "REV1",
                        "page_number": 3,
                        "source_hash": SOURCE_HASH,
                        "title": "제3조",
                        "quote": "근거 문장",
                        "evidence_type": "clause",
                        "bbox": [10.0, 20.0, 50.0, 40.0],
                        "page_width": 100.0,
                        "page_height": 200.0,
                    }
                ],
            }
        ],
        "review_items": [
            {"item_id": "ITEM-C1", "claim_id": "C1", "status": "INDETERMINATE"}
        ],
        "calculations": [],
        "rules": [],
        "exceptions": [],
        "conflicts": [],
        "abstention_reasons": [],
        "decision": {
            "allowed_values": [
                "SATISFIED",
                "NOT_SATISFIED",
                "CONDITIONAL",
                "ADDITIONAL_REVIEW_REQUIRED",
            ],
            "packet_sha256": "c" * 64,
            "human_decision": None,
        },
        "metadata": {"run_id": RUN_ID},
        "summary": {},
        "audit": {},
    }


def _page(root: Path, image_bytes: bytes) -> None:
    directory = root / "page-images" / "REV1"
    directory.mkdir(parents=True)
    image = directory / "page-0003.png"
    image.write_bytes(image_bytes)
    (directory / "page-0003.json").write_text(
        json.dumps(
            {
                "format": "evidence-review/page-image",
                "version": 1,
                "revision_id": "REV1",
                "page_number": 3,
                "source_hash": SOURCE_HASH,
                "pdf_width": 100.0,
                "pdf_height": 200.0,
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


def _reference_page(root: Path, image_bytes: bytes) -> None:
    directory = root / "page-images" / "REV-REF"
    directory.mkdir(parents=True)
    image = directory / "page-0012.png"
    image.write_bytes(image_bytes)
    (directory / "page-0012.json").write_text(
        json.dumps(
            {
                "format": "evidence-review/page-image",
                "version": 1,
                "revision_id": "REV-REF",
                "page_number": 12,
                "source_hash": REFERENCE_SOURCE_HASH,
                "pdf_width": 595.0,
                "pdf_height": 842.0,
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


def _run(root: Path, image_bytes: bytes) -> tuple[Path, bytes]:
    _page(root, image_bytes)
    run = root / "runs" / RUN_ID
    run.mkdir(parents=True)
    packet = b'{"human_decision":null,"run_id":"RUN-0123456789ABCDEF0123"}'
    (run / "final-review-packet.json").write_bytes(packet)
    archive_html = render_review_html(_model(), root / "page-images")
    (run / "review.html").write_text(archive_html, encoding="utf-8")
    return run, packet


def _get(server: object, path: str) -> tuple[int, dict[str, str], bytes]:
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=5)
    connection.request("GET", path, headers={"Host": f"{host}:{port}"})
    response = connection.getresponse()
    headers = {key.lower(): value for key, value in response.getheaders()}
    body = response.read()
    status = response.status
    connection.close()
    return status, headers, body


def _case_page(root: Path, image_bytes: bytes) -> str:
    image_sha256 = hashlib.sha256(image_bytes).hexdigest()
    directory = root / "case-page-images-hq-v1" / CASE_ATTACHMENT_ID
    directory.mkdir(parents=True)
    (directory / "page-0001.png").write_bytes(image_bytes)
    return image_sha256


def _review_model_from_html(html: bytes) -> dict[str, object]:
    match = re.search(
        rb'<script id="review-model" type="application/json">(?P<model>.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    model = json.loads(match.group("model"))
    assert isinstance(model, dict)
    return model


def _embedded_raster_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.startswith("data:image/") else []
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_embedded_raster_values(item))
        return values
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_embedded_raster_values(item))
        return values
    return []


def test_archive_stays_embedded_but_protected_review_is_lazy(tmp_path: Path) -> None:
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"x" * (1024 * 1024)
    run, _ = _run(tmp_path, image_bytes)
    archive = (run / "review.html").read_bytes()
    assert b"data:image/png;base64," in archive
    assert b"data-page-src=" not in archive

    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"/runs/{RUN_ID}/{TOKEN}"
        status, headers, protected = _get(server, base + "/review")
        assert status == 200
        assert headers["cache-control"] == "no-store"
        assert len(protected) < 512_000
        assert b"data:image/png;base64," not in protected
        assert b'data-protected-presentation="true"' in protected
        assert b'data-page-src="./page-images/REV1/3/' + SOURCE_HASH.encode() + b'"' in protected

        status, headers, delivered = _get(
            server,
            base + f"/page-images/REV1/3/{SOURCE_HASH}",
        )
        assert status == 200
        assert headers["content-type"] == "image/png"
        assert headers["cache-control"] == "no-store"
        assert headers["x-content-type-options"] == "nosniff"
        assert delivered == image_bytes
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_protected_case_page_route_delivers_hash_bound_bytes(tmp_path: Path) -> None:
    image_bytes = VALID_MINIMAL_PNG
    image_sha256 = _case_page(tmp_path, image_bytes)
    run = tmp_path / "runs" / RUN_ID
    run.mkdir(parents=True)
    (run / "final-review-packet.json").write_bytes(b"{}")
    model = {
        "run_id": RUN_ID,
        "status": "READY_FOR_HUMAN_REVIEW",
        "display_status": "READY_FOR_HUMAN_REVIEW",
        "question": "protected tiled case page",
        "claims": [],
        "review_items": [],
        "calculations": [],
        "rules": [],
        "exceptions": [],
        "conflicts": [],
        "abstention_reasons": [],
        "summary": {},
        "audit": {},
        "case_visual_review": {
            "status": "VISUAL_ANALYSIS_VALIDATED",
            "pages": [
                {
                    "asset_key": f"{CASE_ATTACHMENT_ID}-p1",
                    "attachment_id": CASE_ATTACHMENT_ID,
                    "page": 1,
                    "width": 2048.0,
                    "height": 2048.0,
                    "document_name": "case.png",
                    "image_sha256": image_sha256,
                    "data_uri": "data:image/png;base64,AAAA",
                    "tiles": [
                        {
                            "x": 0,
                            "y": 0,
                            "width": 2048,
                            "height": 2048,
                            "image_sha256": "b" * 64,
                            "data_uri": "data:image/webp;base64,BBBB",
                        }
                    ],
                    "candidates": [],
                }
            ],
            "reference_pages": [],
            "findings": [],
            "related_references": [],
        },
    }
    (run / "review.html").write_text(
        '<div class="app-shell"></div>'
        f'<figure class="case-visual-page" data-case-page="{CASE_ATTACHMENT_ID}-p1">'
        '<image data-case-page-src="data:image/png;base64,AAAA">'
        "</figure>"
        '<script id="review-model" type="application/json">'
        + json.dumps(model, sort_keys=True, separators=(",", ":"))
        + "</script>",
        encoding="utf-8",
    )

    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    configure_case_visual_server(server)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"/runs/{RUN_ID}/{TOKEN}"
        status, _, protected = _get(server, base + "/review")
        assert status == 200
        assert b"data:image/png;base64," not in protected
        assert b"data:image/webp;base64," not in protected
        assert (
            b"./case-pages/"
            + CASE_ATTACHMENT_ID.encode()
            + b"/1/"
            + image_sha256.encode()
            in protected
        )
        protected_model = _review_model_from_html(protected)
        assert _embedded_raster_values(protected_model) == []

        status, headers, delivered = _get(
            server,
            base + f"/case-pages/{CASE_ATTACHMENT_ID}/1/{image_sha256}",
        )
        assert status == 200
        assert headers["content-type"] == "image/png"
        assert headers["cache-control"] == "no-store"
        assert headers["x-content-type-options"] == "nosniff"
        assert delivered == image_bytes

        status, _, body = _get(
            server,
            base + f"/case-pages/{CASE_ATTACHMENT_ID}/1/{'0' * 64}",
        )
        assert status == 404
        assert image_bytes not in body

        status, _, body = _get(
            server,
            base + f"/case-pages/{CASE_ATTACHMENT_ID}/2/{image_sha256}",
        )
        assert status == 404
        assert image_bytes not in body

        status, _, body = _get(
            server,
            f"/runs/{RUN_ID}/{'c' * 43}/case-pages/{CASE_ATTACHMENT_ID}/1/{image_sha256}",
        )
        assert status == 403
        assert image_bytes not in body

        tampered_bytes = b"tampered-case-page"
        (
            tmp_path
            / "case-page-images-hq-v1"
            / CASE_ATTACHMENT_ID
            / "page-0001.png"
        ).write_bytes(tampered_bytes)
        status, _, body = _get(
            server,
            base + f"/case-pages/{CASE_ATTACHMENT_ID}/1/{image_sha256}",
        )
        assert status == 404
        assert tampered_bytes not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_protected_page_image_route_rejects_wrong_identity_and_tampering(tmp_path: Path) -> None:
    image_bytes = b"\x89PNG\r\n\x1a\nverified"
    _run(tmp_path, image_bytes)
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"/runs/{RUN_ID}/{TOKEN}"
        status, _, _ = _get(server, base + f"/page-images/REV1/4/{SOURCE_HASH}")
        assert status == 404
        status, _, _ = _get(server, base + f"/page-images/REV1/3/{'0' * 64}")
        assert status == 404

        (tmp_path / "page-images" / "REV1" / "page-0003.png").write_bytes(b"tampered")
        status, _, body = _get(server, base + f"/page-images/REV1/3/{SOURCE_HASH}")
        assert status == 404
        assert b"tampered" not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_protected_reference_page_uses_generic_verified_page_route(tmp_path: Path) -> None:
    image_bytes = b"\x89PNG\r\n\x1a\nreference"
    _run(tmp_path, b"subject")
    _reference_page(tmp_path, image_bytes)
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"/runs/{RUN_ID}/{TOKEN}"
        status, headers, body = _get(
            server,
            base + f"/page-images/REV-REF/12/{REFERENCE_SOURCE_HASH}",
        )
        assert status == 200
        assert headers["content-type"] == "image/png"
        assert headers["cache-control"] == "no-store"
        assert headers["x-content-type-options"] == "nosniff"
        assert body == image_bytes

        status, _, _ = _get(
            server,
            base + f"/page-images/REV-REF/12/{'0' * 64}",
        )
        assert status == 404

        status, _, _ = _get(
            server,
            f"/runs/{RUN_ID}/{'x' * 43}/page-images/REV-REF/12/{REFERENCE_SOURCE_HASH}",
        )
        assert status == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_script_loads_only_active_and_adjacent_source_pages() -> None:
    repository_root = Path(__file__).parents[3]
    script = (
        repository_root / "src" / "evidence_review" / "review_packet" / "assets" / "review.js"
    ).read_text(encoding="utf-8")

    assert "ensurePageImageLoaded" in script
    assert "prefetchAdjacentPages" in script
    assert re.search(r"Math\.abs\([^)]*activeIndex[^)]*\) <= 1", script) is not None
