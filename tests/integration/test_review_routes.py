from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from web_runtime.review_server import create_review_server


def test_confirmation_route_is_not_final_review_route(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "RUN-001"
    (run_dir / "machine").mkdir(parents=True)
    (run_dir / "machine" / "drawing-confirmation.json").write_text(
        json.dumps({"run_id": "RUN-001", "workflow_state": "INPUT_CONFIRMATION_REQUIRED"}),
        encoding="utf-8",
    )
    server = create_review_server(tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base}/runs/RUN-001/confirmation", timeout=5) as response:
            assert response.status == 200
            assert b"INPUT_CONFIRMATION_REQUIRED" in response.read()
        with pytest.raises(HTTPError) as error:
            urlopen(f"{base}/runs/RUN-001/review", timeout=5)
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_review_route_requires_final_packet(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "RUN-001"
    run_dir.mkdir(parents=True)
    (run_dir / "final-review-packet.json").write_text("{}", encoding="utf-8")
    (run_dir / "review.html").write_text("<html>final</html>", encoding="utf-8")
    server = create_review_server(tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/runs/RUN-001/review",
            timeout=5,
        ) as response:
            assert response.status == 200
            assert response.read() == b"<html>final</html>"
    finally:
        server.shutdown()
        server.server_close()
