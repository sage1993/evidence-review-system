from __future__ import annotations

import hashlib
import http.client
import json
import sqlite3
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


def _get_html(server: object, path: str) -> tuple[int, bytes]:
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=5)
    connection.request("GET", path, headers={"Host": f"{host}:{port}"})
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, body


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
    stale_code, stale = _request(server, "GET", base + "/decision/status")
    assert stale_code == 409
    assert stale["error"] == "STALE_PACKET"


def test_client_packet_hash_is_rejected_even_if_correct(running) -> None:
    server, run, packet, base = running
    code, _ = _request(server, "POST", base + "/decision", body={
        **_intent(), "packet_hash": hashlib.sha256(packet).hexdigest(),
    })
    assert code == 400
    assert not (run / "human-decisions").exists()


@pytest.mark.parametrize("artifact", ("run-manifest.json", "track-a-bundle.json"))
def test_changed_authority_rejects_review_assets_and_decision(running, artifact: str) -> None:
    server, run, _, base = running
    (run / artifact).write_bytes(b"{}")
    paths = (
        "/review", "/packet", "/packet/hash", "/decision/status",
        "/page-images/REV1/1/" + "a" * 64,
        "/case-pages/ATT-1/1/" + "b" * 64,
        "/case-tiles/ATT-1/1/0/0/" + "b" * 64,
    )
    for path in paths:
        code, body = _get_html(server, base + path)
        assert code == 409, (path, code)
        assert json.loads(body)["error"] == "STALE_PACKET"
    assert _request(server, "POST", base + "/decision", body=_intent())[0] == 409
    assert not (run / "human-decisions").exists()


def test_invalid_finalizer_at_startup_has_no_protected_authority(tmp_path: Path) -> None:
    run, _ = _artifacts(tmp_path)
    (run / "run-manifest.json").write_bytes(b"{}")
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"/runs/{RUN_ID}/{TOKEN}"
        assert _get_html(server, base + "/review")[0] == 404
        assert _request(server, "POST", base + "/decision", body=_intent())[0] == 404
        assert not (run / "human-decisions").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_authority_changed_while_decision_body_is_processed_is_rejected(running, monkeypatch):
    from evidence_review.review_packet.local_server import _ReviewHandler

    server, run, _, base = running
    original = _ReviewHandler._decision_payload

    def mutate_after_validation(self, body, run_id):
        payload = original(self, body, run_id)
        (run / "run-manifest.json").write_bytes(b"{}")
        return payload

    monkeypatch.setattr(_ReviewHandler, "_decision_payload", mutate_after_validation)
    code, result = _request(server, "POST", base + "/decision", body=_intent())
    assert code == 409 and result["error"] == "STALE_PACKET"
    assert not (run / "human-decisions").exists()


def test_evidence_bytes_changed_after_startup_reject_the_cached_view(running) -> None:
    server, run, _, base = running
    evidence = run.parent.parent / "evidence" / "evidence.sqlite"
    evidence.write_bytes(evidence.read_bytes() + b"changed")
    assert _get_html(server, base + "/review")[0] == 409
    assert _request(server, "POST", base + "/decision", body=_intent())[0] == 409
    assert not (run / "human-decisions").exists()


def test_authority_changed_during_model_construction_is_not_published(tmp_path, monkeypatch):
    from evidence_review.review_packet import local_server

    run, _ = _artifacts(tmp_path)
    original = local_server.build_review_view_model

    def change_after_build(*args, **kwargs):
        model = original(*args, **kwargs)
        (run / "run-manifest.json").write_bytes(b"{}")
        return model

    monkeypatch.setattr(local_server, "build_review_view_model", change_after_build)
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    try:
        assert RUN_ID not in server.verified_presentations
        assert RUN_ID not in server.run_asset_allowlists
    finally:
        server.server_close()


def test_rewritten_request_cannot_rebind_same_logical_database(tmp_path: Path) -> None:
    from evidence_review.evidence.snapshot import finalized_evidence_provenance

    run, _ = _artifacts(tmp_path)
    evidence = tmp_path / "evidence" / "evidence.sqlite"
    before = finalized_evidence_provenance(evidence)
    with sqlite3.connect(evidence) as connection:
        connection.execute("PRAGMA user_version = 123")
    after = finalized_evidence_provenance(evidence)
    assert before["evidence_snapshot_hash"] == after["evidence_snapshot_hash"]
    assert before["evidence_db_sha256"] != after["evidence_db_sha256"]
    request_path = run / "review-request.json"
    request = json.loads(request_path.read_bytes())
    request["inputs"]["evidence_snapshot_provenance"] = after
    request_path.write_text(json.dumps(request), encoding="utf-8")
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    try:
        assert RUN_ID not in server.verified_presentations
    finally:
        server.server_close()


def test_request_only_provenance_cannot_supply_missing_verified_binding(tmp_path: Path):
    _artifacts(tmp_path, inputs={"evidence_snapshot_provenance": None})
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    try:
        assert RUN_ID not in server.verified_presentations
    finally:
        server.server_close()


def test_verified_bundle_does_not_require_unbound_request_file(tmp_path: Path):
    run, _ = _artifacts(tmp_path)
    (run / "review-request.json").unlink()
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    try:
        assert RUN_ID in server.verified_presentations
    finally:
        server.server_close()


def test_missing_review_entry_does_not_publish_a_final_route(tmp_path: Path):
    run, _ = _artifacts(tmp_path)
    (run / "review.html").unlink()
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    try:
        assert RUN_ID not in server.verified_presentations
    finally:
        server.server_close()


def test_changed_manifest_bound_inputs_cannot_reuse_unchanged_packet_session(running):
    server, run, packet, base = running
    bundle_path = run / "track-a-bundle.json"
    bundle = json.loads(bundle_path.read_bytes())
    bundle["inputs"]["reviewer_note"] = "changed control input"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    manifest_path = run / "run-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["artifacts"]["track-a-bundle.json"] = hashlib.sha256(
        bundle_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert (run / "final-review-packet.json").read_bytes() == packet
    assert _get_html(server, base + "/review")[0] == 409
    assert _request(server, "POST", base + "/decision", body=_intent())[0] == 409
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


def test_stale_archive_is_replaced_by_current_verified_packet_on_restart(tmp_path: Path) -> None:
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
        view_code, rendered = _get_html(server, f"/runs/{RUN_ID}/{TOKEN}/review")
        assert view_code == 200
        assert "접면 비율은 9.375%이다.".encode() in rendered
        code, result = _request(
            server, "POST", f"/runs/{RUN_ID}/{TOKEN}/decision", body=_intent(),
        )
        assert code == 201
        records = list((run / "human-decisions").glob("*.json"))
        assert len(records) == 1
        assert json.loads(records[0].read_bytes())["packet_hash"] == hashlib.sha256(
            packet + b" "
        ).hexdigest()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("include_packet_hash", (False, True))
def test_forged_archive_cannot_become_the_presented_review(
    tmp_path: Path,
    include_packet_hash: bool,
) -> None:
    """A server-owned packet digest must not authenticate archive-supplied claims."""
    run, packet = _artifacts(tmp_path)
    metadata = (
        {"packet_sha256": hashlib.sha256(packet).hexdigest()}
        if include_packet_hash
        else {}
    )
    forged_model = {
        "run_id": RUN_ID,
        "status": "READY_FOR_HUMAN_REVIEW",
        "display_status": "READY_FOR_HUMAN_REVIEW",
        "question": "FORGED QUESTION",
        "claims": [{"claim_id": "FORGED", "text": "FORGED CLAIM", "citations": []}],
        "review_items": [],
        "calculations": [],
        "rules": [],
        "exceptions": [],
        "conflicts": [],
        "abstention_reasons": [],
        "summary": {},
        "audit": {},
        "metadata": metadata,
    }
    (run / "review.html").write_text(
        '<div class="app-shell"></div>'
        '<script id="review-model" type="application/json">'
        + json.dumps(forged_model)
        + "</script>",
        encoding="utf-8",
    )
    archived_bytes = (run / "review.html").read_bytes()
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"/runs/{RUN_ID}/{TOKEN}"
        code, rendered = _get_html(server, base + "/review")
        assert code == 200
        assert b"FORGED CLAIM" not in rendered
        assert "접면 비율은 9.375%이다.".encode() in rendered
        code, result = _request(server, "POST", base + "/decision", body=_intent())
        assert code == 201
        assert result["display_status"] == "REVIEW_COMPLETED"
        assert len(list((run / "human-decisions").glob("*.json"))) == 1
        assert (run / "review.html").read_bytes() == archived_bytes
        assert (run / "final-review-packet.json").read_bytes() == packet
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
