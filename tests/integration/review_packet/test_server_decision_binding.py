from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Thread

import pytest

from evidence_review.review_packet.local_server import create_review_server
from tests.integration.review_packet.test_local_server import (
    REVIEWER_ID,
    RUN_ID,
    TOKEN,
    _artifacts,
    _request,
)


@pytest.fixture
def running(tmp_path: Path):
    run, packet = _artifacts(tmp_path)
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN},
                                  reviewer_ids={RUN_ID: REVIEWER_ID})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, run, packet, f"/runs/{RUN_ID}/{TOKEN}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _intent() -> dict[str, str]:
    return {"reviewer_id": REVIEWER_ID, "decision": "SATISFIED", "notes": "test"}


def test_server_binds_exact_packet_without_client_hash_and_detects_stale(running) -> None:
    server, run, packet, base = running
    code, _ = _request(server, "POST", base + "/decision", body=_intent())
    assert code == 201
    records = list((run / "human-decisions").glob("*.json"))
    assert len(records) == 1
    saved = json.loads(records[0].read_bytes())
    assert saved["packet_hash"] == hashlib.sha256(packet).hexdigest()
    _, status = _request(server, "GET", base + "/decision/status")
    assert status["decision_binding_status"] == "VALID"
    packet_path = run / "final-review-packet.json"
    packet_path.write_bytes(packet + b" ")
    _, status = _request(server, "GET", base + "/decision/status")
    assert status["decision_binding_status"] == "STALE"
    assert status["decision_record"] is None
    assert status["display_status"] != "REVIEW_COMPLETED"


def test_client_packet_hash_is_rejected_even_if_correct(running) -> None:
    server, run, packet, base = running
    code, _ = _request(server, "POST", base + "/decision", body={
        **_intent(), "packet_hash": hashlib.sha256(packet).hexdigest(),
    })
    assert code == 400
    assert not (run / "human-decisions").exists()


def test_changed_packet_cannot_receive_decision_from_existing_session(running) -> None:
    server, run, packet, base = running
    (run / "final-review-packet.json").write_bytes(packet + b" ")
    code, result = _request(server, "POST", base + "/decision", body=_intent())
    assert code == 409
    assert result["error"] == "STALE_PACKET"
    assert not (run / "human-decisions").exists()


def test_same_packet_decision_survives_server_restart(tmp_path: Path) -> None:
    run, packet = _artifacts(tmp_path)
    for phase in ("write", "restart"):
        server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"/runs/{RUN_ID}/{TOKEN}"
            if phase == "write":
                assert _request(server, "POST", base + "/decision", body=_intent())[0] == 201
            _, status = _request(server, "GET", base + "/decision/status")
            assert status["decision_binding_status"] == "VALID"
            assert status["packet_hash"] == hashlib.sha256(packet).hexdigest()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    assert len(list((run / "human-decisions").glob("*.json"))) == 1


def test_mismatched_presentation_cannot_bind_a_decision_on_restart(tmp_path: Path) -> None:
    run, packet = _artifacts(tmp_path)
    model = {"metadata": {"packet_sha256": hashlib.sha256(packet).hexdigest()}}
    (run / "review.html").write_text(
        '<script id="review-model" type="application/json">'
        + json.dumps(model) + '</script>', encoding="utf-8",
    )
    (run / "final-review-packet.json").write_bytes(packet + b" ")
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        code, result = _request(
            server, "POST", f"/runs/{RUN_ID}/{TOKEN}/decision", body=_intent(),
        )
        assert code == 409 and result["error"] == "STALE_PACKET"
        assert not (run / "human-decisions").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
