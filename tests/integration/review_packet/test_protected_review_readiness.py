from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

from tests.integration.review_packet.test_review_workspace_performance import (
    VALID_MINIMAL_PNG,
)
from tests.integration.review_packet.verified_transport_fixture import (
    install_visual_authority,
)

RUN_ID = "RUN-0123456789ABCDEF0123"
TOKEN = "r" * 43
UNTILED_ATTACHMENT = "ATT-UNTILED"
TILED_ATTACHMENT = "ATT-TILED"


def _data_uri(image_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")


def _case_model(untiled_sha256: str, tiled_sha256: str | None = None) -> dict[str, object]:
    tiled_sha256 = tiled_sha256 or untiled_sha256
    return {
        "run_id": RUN_ID,
        "status": "READY_FOR_HUMAN_REVIEW",
        "display_status": "READY_FOR_HUMAN_REVIEW",
        "question": "protected readiness",
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
                    "asset_key": f"{UNTILED_ATTACHMENT}-p1",
                    "attachment_id": UNTILED_ATTACHMENT,
                    "page": 1,
                    "width": 1.0,
                    "height": 1.0,
                    "document_name": "untiled.png",
                    "image_sha256": untiled_sha256,
                    "data_uri": _data_uri(VALID_MINIMAL_PNG),
                    "tiles": [],
                    "candidates": [],
                },
                {
                    "asset_key": f"{TILED_ATTACHMENT}-p2",
                    "attachment_id": TILED_ATTACHMENT,
                    "page": 2,
                    "width": 4100.0,
                    "height": 4100.0,
                    "document_name": "tiled.png",
                    "image_sha256": tiled_sha256,
                    "data_uri": _data_uri(VALID_MINIMAL_PNG),
                    "tiles": [
                        {
                            "x": 0,
                            "y": 0,
                            "width": 1,
                            "height": 1,
                            "image_sha256": tiled_sha256,
                            "data_uri": _data_uri(VALID_MINIMAL_PNG),
                        }
                    ],
                    "candidates": [],
                },
            ],
            "reference_pages": [],
            "findings": [],
            "related_references": [],
        },
    }


def _write_workspace(root: Path) -> set[str]:
    untiled_sha256 = hashlib.sha256(VALID_MINIMAL_PNG).hexdigest()
    output = BytesIO()
    Image.new("RGB", (4100, 4100), "white").save(output, format="PNG")
    tiled_bytes = output.getvalue()
    tiled_sha256 = hashlib.sha256(tiled_bytes).hexdigest()
    model = _case_model(untiled_sha256, tiled_sha256)

    for attachment_id, page_number, image_bytes in (
        (UNTILED_ATTACHMENT, 1, VALID_MINIMAL_PNG),
        (TILED_ATTACHMENT, 2, tiled_bytes),
    ):
        page_dir = root / "case-page-images-hq-v1" / attachment_id
        page_dir.mkdir(parents=True)
        (page_dir / f"page-{page_number:04d}.png").write_bytes(image_bytes)
    install_visual_authority(root, model)
    return {untiled_sha256, tiled_sha256}


def _start_server(workspace: Path) -> subprocess.Popen[str]:
    environment = os.environ.copy()
    source_root = str(Path(__file__).parents[3] / "src")
    environment["PYTHONPATH"] = source_root + os.pathsep + environment.get(
        "PYTHONPATH", ""
    )
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "evidence_review.review_packet.server_process",
            "--workspace",
            str(workspace),
            "--run-id",
            RUN_ID,
            "--token",
            TOKEN,
            "--idle-timeout-seconds",
            "1.0",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )


def _read_port(process: subprocess.Popen[str]) -> int:
    assert process.stdout is not None
    line = process.stdout.readline().strip()
    assert line, process.stderr.read() if process.stderr is not None else ""
    return int(line)


def _get(port: int, path: str) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
    response = connection.getresponse()
    body = response.read()
    status = response.status
    connection.close()
    return status, body


def _review_model(body: bytes) -> dict[str, object]:
    html = body.decode("utf-8")
    marker = '<script id="review-model" type="application/json">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    value = json.loads(html[start:end])
    assert isinstance(value, dict)
    return value


def _asset_requests(model: dict[str, object]) -> list[tuple[str, str]]:
    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    pages = visual["pages"]
    assert isinstance(pages, list)
    result: list[tuple[str, str]] = []
    for page in pages:
        assert isinstance(page, dict)
        page_asset = page["protected_asset"]
        assert isinstance(page_asset, dict)
        result.append((str(page_asset["route_key"]), str(page["image_sha256"])))
        tiles = page["tiles"]
        assert isinstance(tiles, list)
        for tile in tiles:
            assert isinstance(tile, dict)
            tile_asset = tile["protected_asset"]
            assert isinstance(tile_asset, dict)
            result.append((str(tile_asset["route_key"]), str(tile["image_sha256"])))
    return result


def _http_path(route_key: str) -> str:
    if route_key.startswith("case-page/"):
        suffix = route_key.removeprefix("case-page/")
        return f"/runs/{RUN_ID}/{TOKEN}/case-pages/{suffix}"
    if route_key.startswith("case-tile/"):
        suffix = route_key.removeprefix("case-tile/")
        return f"/runs/{RUN_ID}/{TOKEN}/case-tiles/{suffix}"
    raise AssertionError(f"unexpected protected route: {route_key}")


def _wait_for_exit(process: subprocess.Popen[str], timeout: float = 6.0) -> int:
    deadline = time.monotonic() + timeout
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert process.poll() is not None, "protected server did not exit after idle timeout"
    return process.returncode


def test_real_server_protected_readiness_decodes_and_hashes_tiled_and_untiled_case(
    tmp_path: Path,
) -> None:
    expected_sha256es = _write_workspace(tmp_path)
    process = _start_server(tmp_path)
    try:
        port = _read_port(process)
        review_path = f"/runs/{RUN_ID}/{TOKEN}/review"
        status, body = _get(port, review_path)
        assert status == 200
        assert b"data:image/png;base64," not in body

        model = _review_model(body)
        serialized_model = json.dumps(model, sort_keys=True)
        assert "data_uri" not in serialized_model

        asset_requests = _asset_requests(model)
        assert len(asset_requests) == 11
        assert any(route.startswith("case-page/ATT-UNTILED/") for route, _ in asset_requests)
        assert any(route.startswith("case-tile/ATT-TILED/") for route, _ in asset_requests)

        for route_key, image_sha256 in asset_requests:
            asset_status, image_bytes = _get(port, _http_path(route_key))
            assert asset_status == 200
            if route_key.startswith("case-page/"):
                assert image_sha256 in expected_sha256es
            assert hashlib.sha256(image_bytes).hexdigest() == image_sha256
            with Image.open(BytesIO(image_bytes)) as image:
                image.verify()
                assert image.format == "PNG"

        state_path = tmp_path / ".review-runtime" / RUN_ID / "review-server.json"
        assert state_path.is_file()
        assert _wait_for_exit(process) == 0
        assert not state_path.exists()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
