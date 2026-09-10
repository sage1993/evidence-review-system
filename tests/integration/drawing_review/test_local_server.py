from __future__ import annotations

import hashlib
import http.client
import json
import socket
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from evidence_review.contracts.drawing import DrawingCandidate, Geometry
from evidence_review.drawing_review.local_server import (
    _verified_bytes,
    serve_annotation_workspace,
)
from evidence_review.drawing_review.view_model import DrawingPage
from evidence_review.parsing.drawing_candidates import persist_candidate
from evidence_review.parsing.drawing_case import CaseManifestEntry

SOURCE_HASH = "a" * 64
TOKEN = "T" * 32


def _page() -> DrawingPage:
    return DrawingPage(
        source_sha256=SOURCE_HASH,
        page=1,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        width=1000.0,
        height=800.0,
    )


def _candidate() -> DrawingCandidate:
    return DrawingCandidate(
        candidate_id="CAND-EXISTING",
        source_sha256=SOURCE_HASH,
        page=1,
        candidate_type="DIMENSION_TEXT",
        origin="EXTRACTOR",
        status="UNCONFIRMED",
        geometry=Geometry(
            type="BBOX",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=(100.0, 120.0, 300.0, 180.0),
        ),
        raw_value="8M",
        normalized_candidate="8 m",
        extractor="fixture",
        extractor_version="1",
        annotation_id=None,
    )


def _action_payload() -> dict[str, object]:
    return {
        "action": "ACCEPTED",
        "candidate_id": "CAND-EXISTING",
        "reviewer": "kim-sh",
        "confirmed_at": "2026-08-03T22:10:00+09:00",
        "confirmed_value": None,
        "unit": None,
        "geometry": None,
    }


def _post(server_url: str, origin: str, payload: bytes) -> tuple[int, bytes]:
    request = Request(
        server_url + "/actions",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Origin": origin,
        },
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def _raw_request_headers(
    server: object,
    path: str,
    content_length: int,
    *,
    duplicate_header: tuple[str, str] | None = None,
) -> bytes:
    host = f"{server.host}:{server.port}"  # type: ignore[attr-defined]
    headers = [
        f"POST {path} HTTP/1.1",
        f"Host: {host}",
        f"Origin: http://{host}",
        "Content-Type: application/json",
        f"Content-Length: {content_length}",
        "Connection: close",
    ]
    if duplicate_header is not None:
        headers.append(f"{duplicate_header[0]}: {duplicate_header[1]}")
    return ("\r\n".join(headers) + "\r\n\r\n").encode("ascii")


def _read_http_response(
    connection: socket.socket, *, deadline_seconds: float = 2.0
) -> tuple[bytes, bytes]:
    deadline = time.monotonic() + deadline_seconds
    response = bytearray()
    while b"\r\n\r\n" not in response:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError("timed out waiting for HTTP response headers")
        connection.settimeout(remaining)
        chunk = connection.recv(8192)
        if not chunk:
            raise AssertionError("connection closed before HTTP response headers")
        response.extend(chunk)
    header_bytes, body = bytes(response).split(b"\r\n\r\n", 1)
    headers: dict[bytes, bytes] = {}
    for line in header_bytes.split(b"\r\n")[1:]:
        name, value = line.split(b":", 1)
        headers[name.lower()] = value.strip()
    content_length = int(headers[b"content-length"])
    while len(body) < content_length:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError("timed out waiting for HTTP response body")
        connection.settimeout(remaining)
        chunk = connection.recv(8192)
        if not chunk:
            raise AssertionError("connection closed before HTTP response body")
        body += chunk
    return header_bytes, body[:content_length]


@pytest.mark.parametrize(
    ("path_template", "duplicate_header"),
    [
        ("/annotation/{token}/actions", ("Host", "attacker.invalid")),
        ("/annotation/{token}/actions", ("Origin", "http://attacker.invalid")),
        ("/calibration/{token}", ("Host", "attacker.invalid")),
        ("/calibration/{token}", ("Origin", "http://attacker.invalid")),
    ],
)
def test_mutation_routes_reject_duplicate_security_headers(
    tmp_path: Path,
    path_template: str,
    duplicate_header: tuple[str, str],
) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        with socket.create_connection((server.host, server.port), timeout=5) as connection:
            connection.sendall(
                _raw_request_headers(
                    server,
                    path_template.format(token=TOKEN),
                    2,
                    duplicate_header=duplicate_header,
                )
                + b"{}"
            )
            response_headers, response_body = _read_http_response(connection)

    assert response_headers.startswith(b"HTTP/1.0 403 ")
    assert response_body == b'{"error":"FORBIDDEN"}'


@pytest.mark.parametrize("path_template", ["/annotation/{token}/actions", "/calibration/{token}"])
def test_oversized_header_only_mutation_request_returns_413_promptly(
    tmp_path: Path, path_template: str
) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
        max_body_bytes=8,
    ) as server:
        started = time.monotonic()
        with socket.create_connection((server.host, server.port), timeout=5) as connection:
            connection.sendall(
                _raw_request_headers(server, path_template.format(token=TOKEN), 1024)
            )
            response_headers, response_body = _read_http_response(
                connection, deadline_seconds=0.75
            )
        elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert response_headers.startswith(b"HTTP/1.0 413 ")
    assert response_body == b'{"error":"BODY_TOO_LARGE"}'


@pytest.mark.parametrize("path_template", ["/annotation/{token}/actions", "/calibration/{token}"])
def test_oversized_mutation_request_drains_full_body_before_clean_close(
    tmp_path: Path, path_template: str
) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)
    payload = b"x" * (256 * 1024)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
        max_body_bytes=8,
    ) as server:
        with socket.create_connection((server.host, server.port), timeout=5) as connection:
            prefix_length = 16 * 1024
            connection.sendall(
                _raw_request_headers(
                    server, path_template.format(token=TOKEN), len(payload)
                )
                + payload[:prefix_length]
            )
            release_sender = threading.Event()
            send_errors: list[BaseException] = []

            def send_remainder() -> None:
                if not release_sender.wait(timeout=5):
                    send_errors.append(AssertionError("body sender was not released"))
                    return
                try:
                    for offset in range(prefix_length, len(payload), 8192):
                        connection.sendall(payload[offset : offset + 8192])
                except BaseException as error:
                    send_errors.append(error)

            sender = threading.Thread(target=send_remainder, daemon=True)
            sender.start()
            response_headers, response_body = _read_http_response(connection)
            release_sender.set()
            sender.join(timeout=5)
            assert not sender.is_alive()
            assert send_errors == []
            connection.shutdown(socket.SHUT_WR)
            connection.settimeout(5)
            try:
                while connection.recv(8192):
                    pass
            except (ConnectionAbortedError, ConnectionResetError) as error:
                raise AssertionError("connection did not reach EOF cleanly") from error

    assert response_headers.startswith(b"HTTP/1.0 413 ")
    assert response_body == b'{"error":"BODY_TOO_LARGE"}'


@pytest.mark.parametrize("path_template", ["/annotation/{token}/actions", "/calibration/{token}"])
def test_oversized_mutation_request_slow_sender_has_bounded_completion(
    tmp_path: Path, path_template: str
) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
        max_body_bytes=8,
    ) as server:
        with socket.create_connection((server.host, server.port), timeout=5) as connection:
            connection.sendall(
                _raw_request_headers(server, path_template.format(token=TOKEN), 1024) + b"x"
            )
            response_headers, response_body = _read_http_response(connection)
            send_errors: list[BaseException] = []

            def send_slowly() -> None:
                try:
                    for _ in range(20):
                        time.sleep(0.1)
                        connection.sendall(b"x")
                except BaseException as error:
                    send_errors.append(error)

            sender = threading.Thread(target=send_slowly, daemon=True)
            started = time.monotonic()
            sender.start()
            sender.join(timeout=1)
            elapsed = time.monotonic() - started
            assert not sender.is_alive()
            assert send_errors
            assert elapsed < 1

    assert response_headers.startswith(b"HTTP/1.0 413 ")
    assert response_body == b'{"error":"BODY_TOO_LARGE"}'


def test_oversized_mutation_transport_windows_stress_full_body_500_iterations(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)
    paths = ("/annotation/{token}/actions", "/calibration/{token}")
    payload = b"x" * 1024

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
        max_body_bytes=8,
    ) as server:
        for iteration in range(500):
            with socket.create_connection((server.host, server.port), timeout=5) as connection:
                connection.sendall(
                    _raw_request_headers(
                        server,
                        paths[iteration % len(paths)].format(token=TOKEN),
                        len(payload),
                    )
                    + payload
                )
                response_headers, response_body = _read_http_response(connection)
            assert response_headers.startswith(b"HTTP/1.0 413 ")
            assert response_body == b'{"error":"BODY_TOO_LARGE"}'


def test_oversized_mutation_transport_windows_stress_header_only_100_iterations(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)
    paths = ("/annotation/{token}/actions", "/calibration/{token}")

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
        max_body_bytes=8,
    ) as server:
        for iteration in range(100):
            with socket.create_connection((server.host, server.port), timeout=5) as connection:
                connection.sendall(
                    _raw_request_headers(
                        server,
                        paths[iteration % len(paths)].format(token=TOKEN),
                        1024,
                    )
                )
                response_headers, response_body = _read_http_response(connection)
            assert response_headers.startswith(b"HTTP/1.0 413 ")
            assert response_body == b'{"error":"BODY_TOO_LARGE"}'


def test_serves_tokenized_page_on_loopback(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<!doctype html><p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        assert server.host == "127.0.0.1"
        assert server.url.startswith("http://127.0.0.1:")
        with urlopen(server.url, timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Access-Control-Allow-Origin"] is None
            assert response.headers["Cache-Control"] == "no-store"
            assert "default-src 'none'" in response.headers["Content-Security-Policy"]
        assert "annotation" in body


def test_rejects_wrong_token(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        wrong_url = server.url.replace(TOKEN, "W" * 32)
        with pytest.raises(HTTPError) as captured:
            urlopen(wrong_url, timeout=5)
        assert captured.value.code == 403


def test_rejects_wrong_host_header(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        connection = http.client.HTTPConnection(server.host, server.port, timeout=5)
        connection.putrequest("GET", f"/annotation/{TOKEN}", skip_host=True)
        connection.putheader("Host", "evil.example")
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        connection.close()


def test_rejects_missing_or_wrong_origin_on_post(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        body = json.dumps(_action_payload()).encode("utf-8")
        status, _ = _post(server.url, "http://evil.example", body)
        assert status == 403

        request = Request(
            server.url + "/actions",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(HTTPError) as captured:
            urlopen(request, timeout=5)
        assert captured.value.code == 403


def test_valid_post_records_append_only_confirmation(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    candidate = _candidate()
    entry = persist_candidate(case_dir, candidate)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={candidate.candidate_id: entry},
        token=TOKEN,
    ) as server:
        status, body = _post(
            server.url,
            server.origin,
            json.dumps(_action_payload()).encode("utf-8"),
        )

        assert status == 201
        response = json.loads(body)
        confirmation = response["confirmation"]
        assert confirmation["artifact_id"].startswith("CONF-")
        assert confirmation["sha256"]
        assert len(server.results) == 1
        assert (case_dir / confirmation["relative_path"]).is_file()


def test_rejects_large_or_malformed_json_body(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
        max_body_bytes=128,
    ) as server:
        large_status, _ = _post(server.url, server.origin, b"{" + b"x" * 256)
        assert large_status == 413

        malformed_status, malformed_body = _post(
            server.url,
            server.origin,
            b"{not-json}",
        )
        assert malformed_status == 400
        assert str(tmp_path).encode("utf-8") not in malformed_body


def test_rejects_non_json_content_type(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        request = Request(
            server.url + "/actions",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "text/plain",
                "Origin": server.origin,
            },
        )
        with pytest.raises(HTTPError) as captured:
            urlopen(request, timeout=5)
        assert captured.value.code == 415


def test_rejects_symlink_case_root(tmp_path: Path) -> None:
    target = tmp_path / "actual-case"
    target.mkdir()
    linked = tmp_path / "CASE-001"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")

    with pytest.raises(ValueError, match="case_dir"):
        serve_annotation_workspace(
            html="<p>annotation</p>",
            case_dir=linked,
            page=_page(),
            candidate_entries={},
            token=TOKEN,
        )


def test_rejects_linked_case_artifact_before_hash_consumption(tmp_path: Path) -> None:
    case_dir = tmp_path / "CASE-001"
    artifact_path = case_dir / "candidates" / "candidate.json"
    artifact_path.parent.mkdir(parents=True)
    external = case_dir / "trusted-candidate.json"
    payload = b"external candidate"
    external.write_bytes(payload)
    try:
        artifact_path.symlink_to(external)
    except OSError as error:
        pytest.skip(f"file symlink creation unavailable: {error}")

    entry = CaseManifestEntry(
        artifact_id="CAND-EXTERNAL",
        relative_path="candidates/candidate.json",
        sha256=hashlib.sha256(payload).hexdigest(),
    )

    with pytest.raises(ValueError, match="symlink|reparse"):
        _verified_bytes(case_dir, entry)
