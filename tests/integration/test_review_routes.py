from __future__ import annotations

import hashlib
import json
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pytest

from web_runtime.review_server import create_review_server

TOKEN = "a" * 32


def _review_artifacts(root: Path, *, html: bytes = b"<html>final</html>") -> tuple[Path, bytes]:
    run_dir = root / "runs" / "RUN-001"
    run_dir.mkdir(parents=True)
    packet = b'{"human_decision":null,"run_id":"RUN-001"}'
    (run_dir / "final-review-packet.json").write_bytes(packet)
    (run_dir / "review.html").write_bytes(html)
    return run_dir, packet


@contextmanager
def _server(root: Path, *, max_body_bytes: int = 65536) -> Iterator[tuple[object, str]]:
    server = create_review_server(
        root,
        run_tokens={"RUN-001": TOKEN},
        max_body_bytes=max_body_bytes,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        yield server, base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> bytes:
    request = Request(url, data=body, headers=headers or {}, method=method)
    with urlopen(request, timeout=5) as response:
        return response.read()


def _raw_request(base: str, request: bytes) -> bytes:
    parsed = urlsplit(base)
    assert parsed.hostname is not None
    assert parsed.port is not None
    with socket.create_connection((parsed.hostname, parsed.port), timeout=5) as connection:
        connection.sendall(request)
        response = bytearray()
        while chunk := connection.recv(8192):
            response.extend(chunk)
    return bytes(response)


def _decision(packet: bytes, **changes: object) -> bytes:
    payload: dict[str, object] = {
        "reviewer_id": "kim.sh",
        "packet_hash": hashlib.sha256(packet).hexdigest(),
        "decision": "SATISFIED",
        "notes": "reviewed locally",
    }
    payload.update(changes)
    return json.dumps(payload).encode("utf-8")


def test_confirmation_route_requires_run_token_and_is_not_final_review_route(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "RUN-001"
    (run_dir / "machine").mkdir(parents=True)
    (run_dir / "machine" / "drawing-confirmation.json").write_text(
        json.dumps({"run_id": "RUN-001", "workflow_state": "INPUT_CONFIRMATION_REQUIRED"}),
        encoding="utf-8",
    )
    server = create_review_server(tmp_path, run_tokens={"RUN-001": TOKEN})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(
            f"{base}/runs/RUN-001/{TOKEN}/confirmation", timeout=5
        ) as response:
            assert response.status == 200
            assert b"INPUT_CONFIRMATION_REQUIRED" in response.read()
        with pytest.raises(HTTPError) as error:
            urlopen(f"{base}/runs/RUN-001/confirmation", timeout=5)
        assert error.value.code == 404
        with pytest.raises(HTTPError) as error:
            urlopen(f"{base}/runs/RUN-001/{'b' * 32}/confirmation", timeout=5)
        assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            urlopen(f"{base}/runs/RUN-001/review", timeout=5)
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_server_binds_loopback_and_serves_protected_read_only_artifacts(
    tmp_path: Path,
) -> None:
    _, packet = _review_artifacts(tmp_path)
    with _server(tmp_path) as (server, base):
        assert server.server_address[0] == "127.0.0.1"
        review = _request(f"{base}/runs/RUN-001/{TOKEN}/review")
        assert review == b"<html>final</html>"
        assert _request(f"{base}/runs/RUN-001/{TOKEN}/packet") == packet
        assert json.loads(_request(f"{base}/runs/RUN-001/{TOKEN}/packet/hash")) == {
            "packet_hash": hashlib.sha256(packet).hexdigest()
        }
        with urlopen(f"{base}/runs/RUN-001/{TOKEN}/review", timeout=5) as response:
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["Referrer-Policy"] == "no-referrer"
            assert "Content-Security-Policy" in response.headers
            assert "Access-Control-Allow-Origin" not in response.headers


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("/runs/RUN-001/review", 404),
        ("/runs/RUN-001/" + "b" * 32 + "/review", 403),
        ("/runs/RUN-001/%2e%2e/review", 404),
        ("/runs/RUN-001/" + TOKEN + "/review?ignored=1", 404),
        ("/runs/RUN-001/" + TOKEN + "/review%2fpacket", 404),
    ],
)
def test_protected_routes_reject_missing_wrong_or_unsafe_paths(
    tmp_path: Path, path: str, status: int
) -> None:
    _review_artifacts(tmp_path)
    with _server(tmp_path) as (_, base):
        with pytest.raises(HTTPError) as error:
            _request(f"{base}{path}")
        assert error.value.code == status


def test_protected_routes_require_exact_host_and_reject_foreign_origin(tmp_path: Path) -> None:
    _review_artifacts(tmp_path)
    with _server(tmp_path) as (_, base):
        url = f"{base}/runs/RUN-001/{TOKEN}/review"
        with pytest.raises(HTTPError) as error:
            _request(url, headers={"Host": "localhost:1"})
        assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            _request(url, headers={"Origin": "http://attacker.invalid"})
        assert error.value.code == 403


def test_protected_routes_reject_duplicate_host_even_when_the_first_value_is_valid(
    tmp_path: Path,
) -> None:
    _review_artifacts(tmp_path)
    with _server(tmp_path) as (_, base):
        host = base.removeprefix("http://")
        response = _raw_request(
            base,
            (
                f"GET /runs/RUN-001/{TOKEN}/review HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Host: attacker.invalid\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii"),
        )
    assert response.startswith(b"HTTP/1.0 403")


def test_decision_rejects_duplicate_origin_even_when_the_first_value_is_valid(
    tmp_path: Path,
) -> None:
    run_dir, packet = _review_artifacts(tmp_path)
    with _server(tmp_path) as (_, base):
        host = base.removeprefix("http://")
        body = _decision(packet)
        response = _raw_request(
            base,
            (
                f"POST /runs/RUN-001/{TOKEN}/decision HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                f"Origin: {base}\r\n"
                "Origin: http://attacker.invalid\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            + body,
        )
    assert response.startswith(b"HTTP/1.0 403")
    assert not (run_dir / "human-decisions").exists()


def test_review_route_requires_both_final_packet_and_html(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "RUN-001"
    run_dir.mkdir(parents=True)
    (run_dir / "final-review-packet.json").write_text("{}", encoding="utf-8")
    with _server(tmp_path) as (_, base):
        with pytest.raises(HTTPError) as error:
            _request(f"{base}/runs/RUN-001/{TOKEN}/review")
        assert error.value.code == 404


def test_review_server_rejects_symlinked_workspace_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "workspace-link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")
    with pytest.raises(ValueError, match="workspace_root"):
        create_review_server(link, run_tokens={})


def test_review_server_rejects_reparse_workspace_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_lstat = Path.lstat

    def reparse_lstat(path: Path) -> SimpleNamespace:
        status = original_lstat(path)
        if path == tmp_path:
            return SimpleNamespace(
                st_mode=status.st_mode,
                st_file_attributes=0x400,
            )
        return SimpleNamespace(
            st_mode=status.st_mode,
            st_file_attributes=getattr(status, "st_file_attributes", 0),
        )

    monkeypatch.setattr(Path, "lstat", reparse_lstat)
    with pytest.raises(ValueError, match="workspace_root"):
        create_review_server(tmp_path, run_tokens={})


@pytest.mark.parametrize(
    "body",
    [
        b"[",
        b'{"reviewer_id":"kim","reviewer_id":"lee"}',
        b'{"reviewer_id":"kim","unexpected":true}',
    ],
)
def test_decision_rejects_duplicate_or_unknown_json_without_writing(
    tmp_path: Path, body: bytes
) -> None:
    run_dir, _ = _review_artifacts(tmp_path)
    with _server(tmp_path) as (_, base):
        with pytest.raises(HTTPError) as error:
            _request(
                f"{base}/runs/RUN-001/{TOKEN}/decision",
                method="POST",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Origin": base,
                },
            )
        assert error.value.code == 400
    assert not (run_dir / "human-decisions").exists()


def test_decision_rejects_client_controlled_timestamp(tmp_path: Path) -> None:
    run_dir, packet = _review_artifacts(tmp_path)
    with _server(tmp_path) as (_, base):
        with pytest.raises(HTTPError) as error:
            _request(
                f"{base}/runs/RUN-001/{TOKEN}/decision",
                method="POST",
                body=_decision(packet, reviewed_at="2026-08-01T15:30:00+09:00"),
                headers={"Content-Type": "application/json", "Origin": base},
            )
        assert error.value.code == 400
    assert not (run_dir / "human-decisions").exists()


def test_decision_rejects_oversized_body_and_foreign_origin_without_writing(tmp_path: Path) -> None:
    run_dir, packet = _review_artifacts(tmp_path)
    with _server(tmp_path, max_body_bytes=8) as (_, base):
        with pytest.raises(HTTPError) as error:
            _request(
                f"{base}/runs/RUN-001/{TOKEN}/decision",
                method="POST",
                body=_decision(packet),
                headers={"Content-Type": "application/json", "Origin": base},
            )
        assert error.value.code == 413
    with _server(tmp_path) as (_, base):
        with pytest.raises(HTTPError) as error:
            _request(
                f"{base}/runs/RUN-001/{TOKEN}/decision",
                method="POST",
                body=_decision(packet),
                headers={"Content-Type": "application/json", "Origin": "http://attacker.invalid"},
            )
        assert error.value.code == 403
    assert not (run_dir / "human-decisions").exists()


def test_decision_rejects_blank_notes_without_writing(tmp_path: Path) -> None:
    run_dir, packet = _review_artifacts(tmp_path)
    with _server(tmp_path) as (_, base):
        with pytest.raises(HTTPError) as error:
            _request(
                f"{base}/runs/RUN-001/{TOKEN}/decision",
                method="POST",
                body=_decision(packet, notes="  \t"),
                headers={"Content-Type": "application/json", "Origin": base},
            )
        assert error.value.code == 400
    assert not (run_dir / "human-decisions").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "PASS"},
        {"packet_hash": "a" * 64},
    ],
)
def test_decision_rejects_unsupported_values_and_hash_mismatch_without_writing(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    run_dir, packet = _review_artifacts(tmp_path)
    with _server(tmp_path) as (_, base):
        with pytest.raises(HTTPError) as error:
            _request(
                f"{base}/runs/RUN-001/{TOKEN}/decision",
                method="POST",
                body=_decision(packet, **changes),
                headers={"Content-Type": "application/json", "Origin": base},
            )
        assert error.value.code == 400
    assert not (run_dir / "human-decisions").exists()


def test_decision_appends_record_without_mutating_packet_or_html(tmp_path: Path) -> None:
    run_dir, packet = _review_artifacts(tmp_path)
    html_before = (run_dir / "review.html").read_bytes()
    with _server(tmp_path) as (_, base):
        response = _request(
            f"{base}/runs/RUN-001/{TOKEN}/decision",
            method="POST",
            body=_decision(packet),
            headers={"Content-Type": "application/json", "Origin": base},
        )
    created = json.loads(response)
    decision_path = run_dir / "human-decisions" / created["filename"]
    assert created["status"] == "RECORDED"
    assert decision_path.is_file()
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["packet_hash"] == hashlib.sha256(packet).hexdigest()
    assert decision["reviewer_id"] == "kim.sh"
    assert decision["reviewed_at"].endswith("+00:00")
    assert (run_dir / "final-review-packet.json").read_bytes() == packet
    assert (run_dir / "review.html").read_bytes() == html_before


def test_decision_projects_completed_display_status_without_mutating_machine_packet(
    tmp_path: Path,
) -> None:
    run_dir, packet = _review_artifacts(tmp_path)
    html_before = (run_dir / "review.html").read_bytes()
    packet_hash = hashlib.sha256(packet).hexdigest()
    decision_directory = run_dir / "human-decisions"
    decision_directory.mkdir()
    (decision_directory / "foreign.json").write_text(
        json.dumps(
            {
                "run_id": "RUN-001",
                "reviewer_id": "other-reviewer",
                "reviewed_at": "2026-08-01T15:30:00+09:00",
                "packet_hash": "b" * 64,
                "decision": "SATISFIED",
                "notes": "a decision for a different packet",
            }
        ),
        encoding="utf-8",
    )
    with _server(tmp_path) as (_, base):
        assert json.loads(
            _request(f"{base}/runs/RUN-001/{TOKEN}/decision/status")
        ) == {
            "display_status": "READY_FOR_HUMAN_REVIEW",
            "reviewer_id": None,
            "packet_hash": packet_hash,
        }
        response = _request(
            f"{base}/runs/RUN-001/{TOKEN}/decision",
            method="POST",
            body=_decision(packet),
            headers={"Content-Type": "application/json", "Origin": base},
        )
        assert json.loads(response)["display_status"] == "REVIEW_COMPLETED"
        assert json.loads(
            _request(f"{base}/runs/RUN-001/{TOKEN}/decision/status")
        ) == {
            "display_status": "REVIEW_COMPLETED",
            "reviewer_id": None,
            "packet_hash": packet_hash,
        }
    assert (run_dir / "final-review-packet.json").read_bytes() == packet
    assert (run_dir / "review.html").read_bytes() == html_before
