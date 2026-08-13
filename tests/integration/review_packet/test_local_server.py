from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
from threading import Thread

import pytest

from ansim_review.review_packet.local_server import create_review_server

RUN_ID = "RUN-0123456789ABCDEF0123"
TOKEN = "a" * 43
REVIEWER_ID = "reviewer-01"


def _artifacts(root: Path) -> tuple[Path, bytes]:
    run_directory = root / "runs" / RUN_ID
    run_directory.mkdir(parents=True)
    packet = b'{"human_decision":null,"run_id":"RUN-0123456789ABCDEF0123"}'
    (run_directory / "final-review-packet.json").write_bytes(packet)
    (run_directory / "review.html").write_text(
        "<html><body>protected review</body></html>", encoding="utf-8"
    )
    return run_directory, packet


def _request(
    server: object,
    method: str,
    path: str,
    *,
    body: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    address = server.server_address
    host, port = address[0], address[1]
    connection = http.client.HTTPConnection(host, port, timeout=5)
    headers = {"Host": f"{host}:{port}"}
    payload: bytes | None = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers.update(
            {
                "Origin": f"http://{host}:{port}",
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
            }
        )
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    document = json.loads(response.read().decode("utf-8"))
    connection.close()
    return response.status, document


def test_server_supplies_reviewer_hash_and_server_controlled_timestamp(tmp_path: Path) -> None:
    run_directory, packet = _artifacts(tmp_path)
    server = create_review_server(
        tmp_path,
        run_tokens={RUN_ID: TOKEN},
        reviewer_ids={RUN_ID: REVIEWER_ID},
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"/runs/{RUN_ID}/{TOKEN}"
        status_code, status = _request(server, "GET", base + "/decision/status")
        packet_hash = hashlib.sha256(packet).hexdigest()
        assert status_code == 200
        assert status["reviewer_id"] == REVIEWER_ID
        assert status["packet_hash"] == packet_hash

        post_code, result = _request(
            server,
            "POST",
            base + "/decision",
            body={
                "reviewer_id": REVIEWER_ID,
                "packet_hash": packet_hash,
                "decision": "SATISFIED",
                "notes": "근거 확인 완료",
            },
        )
        assert post_code == 201
        assert result["display_status"] == "REVIEW_COMPLETED"
        reviewed_at = result["reviewed_at"]
        assert isinstance(reviewed_at, str)
        assert reviewed_at.endswith("+00:00")
        decisions = tuple((run_directory / "human-decisions").glob("*.json"))
        assert len(decisions) == 1
        saved = json.loads(decisions[0].read_text(encoding="utf-8"))
        assert saved["reviewed_at"] == reviewed_at
        assert saved["packet_hash"] == packet_hash
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_server_rejects_client_timestamp_extra_field_and_packet_mismatch(tmp_path: Path) -> None:
    _, packet = _artifacts(tmp_path)
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"/runs/{RUN_ID}/{TOKEN}/decision"
        valid = {
            "reviewer_id": REVIEWER_ID,
            "packet_hash": hashlib.sha256(packet).hexdigest(),
            "decision": "SATISFIED",
            "notes": "확인",
        }
        invalid_extra = {**valid, "reviewed_at": "2026-08-13T12:00:00+09:00"}
        code, document = _request(server, "POST", base, body=invalid_extra)
        assert code == 400 and document["error"] == "INVALID_DECISION"

        code, document = _request(
            server,
            "POST",
            base,
            body={**valid, "packet_hash": "0" * 64},
        )
        assert code == 400 and document["error"] == "PACKET_HASH_MISMATCH"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_configured_reviewer_id_is_readonly_for_post(tmp_path: Path) -> None:
    _, packet = _artifacts(tmp_path)
    server = create_review_server(
        tmp_path,
        run_tokens={RUN_ID: TOKEN},
        reviewer_ids={RUN_ID: REVIEWER_ID},
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        code, document = _request(
            server,
            "POST",
            f"/runs/{RUN_ID}/{TOKEN}/decision",
            body={
                "reviewer_id": "different-reviewer",
                "packet_hash": hashlib.sha256(packet).hexdigest(),
                "decision": "SATISFIED",
                "notes": "확인",
            },
        )
        assert code == 400
        assert document["error"] == "INVALID_DECISION"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_server_rejects_unknown_reviewer_run_binding(tmp_path: Path) -> None:
    _artifacts(tmp_path)
    with pytest.raises(ValueError, match="unknown run"):
        create_review_server(
            tmp_path,
            run_tokens={RUN_ID: TOKEN},
            reviewer_ids={"RUN-AAAAAAAAAAAAAAAAAAAA": REVIEWER_ID},
        )
