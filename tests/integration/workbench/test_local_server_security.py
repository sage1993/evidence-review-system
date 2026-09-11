from __future__ import annotations

import http.client
import json
import socket
import time
from pathlib import Path
from threading import Thread

from evidence_review.review_matter.service import ReviewMatterService
from evidence_review.workbench.local_server import (
    create_workbench_server,
    serve_workbench,
    stop_workbench_server,
    workbench_server_status,
)

MATTER_ID = "MATTER-001"
TOKEN = "a" * 43
REVIEWER_ID = "reviewer-01"


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ReviewMatterService.open(workspace).create(
        matter_id=MATTER_ID,
        title="Workbench security tests",
    )
    return workspace


def _workspace_with_reachable_view_states(tmp_path: Path) -> tuple[Path, object]:
    from evidence_review.review_matter.formal_run_binding import bind_formal_run
    from tests.integration.review_matter.test_multi_run_history import (
        _finalized_formal_run,
        _matter_with_first_snapshot,
    )

    workspace, store, snapshot = _matter_with_first_snapshot(tmp_path)
    run_id, packet_sha256 = _finalized_formal_run(workspace, snapshot)
    binding = bind_formal_run(
        store,
        snapshot.matter_id,
        snapshot.snapshot_id,
        run_id,
        packet_sha256,
        workspace_root=workspace,
    )
    ReviewMatterService.open(workspace).add_issue(
        matter_id=snapshot.matter_id,
        expected_revision=2,
        issue_id="ISSUE-DRAFT-001",
        question="Confirm the exact source before formal review.",
        work_state="DRAFT",
    )
    return workspace, binding


def _start(
    workspace: Path,
    *,
    matter_id: str = MATTER_ID,
    max_body_bytes: int = 65536,
) -> tuple[object, Thread]:
    server = create_workbench_server(
        workspace,
        matter_id=matter_id,
        token=TOKEN,
        reviewer_id=REVIEWER_ID,
        max_body_bytes=max_body_bytes,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _request(
    server: object,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    origin: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object], dict[str, str]]:
    host, port = server.server_address
    request_headers = {"Host": f"{host}:{port}"}
    if body is not None:
        request_headers.update(
            {
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "Origin": origin or f"http://{host}:{port}",
            }
        )
    if headers:
        request_headers.update(headers)
    connection = http.client.HTTPConnection(host, port, timeout=2)
    connection.request(method, path, body=body, headers=request_headers)
    response = connection.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    response_headers = dict(response.getheaders())
    connection.close()
    return response.status, payload, response_headers


def _html_request(
    server: object, path: str
) -> tuple[int, str, dict[str, str]]:
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=2)
    connection.request("GET", path, headers={"Host": f"{host}:{port}"})
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    headers = dict(response.getheaders())
    connection.close()
    return response.status, body, headers


def test_workbench_default_route_serves_protected_html_and_retains_json_state(
    tmp_path: Path,
) -> None:
    server, thread = _start(_workspace(tmp_path))
    try:
        status, html, headers = _html_request(server, server.path)

        assert status == 200
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert 'data-surface="workbench"' in html
        assert "script-src 'nonce-" in headers["Content-Security-Policy"]
        csp_directives = headers["Content-Security-Policy"].split("; ")
        assert "connect-src 'self'" in csp_directives
        assert "'unsafe-inline'" not in headers["Content-Security-Policy"]

        status, state, headers = _request(
            server,
            "GET",
            server.path.replace("/view", "/state"),
        )
        assert status == 200
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert state["surface"] == "WORKBENCH"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_protected_view_reaches_persisted_draft_history_and_bounded_navigation(
    tmp_path: Path,
) -> None:
    workspace, binding = _workspace_with_reachable_view_states(tmp_path)
    server, thread = _start(workspace, matter_id=binding.matter_id)
    try:
        status, html, _ = _html_request(server, server.path)

        assert status == 200
        assert '<form data-workbench-navigation-form' in html
        assert 'name="query"' in html
        assert 'maxlength="240"' in html
        assert 'data-workbench-navigation-results' in html
        assert "evidence/search" in html
        assert "innerHTML" not in html
        assert "ISSUE-DRAFT-001" in html
        assert "생성된 초안 작업 항목" in html
        assert "미확인" in html
        assert binding.run_id in html
        assert binding.snapshot_id in html
        assert "검증된 정식 검토 이력" in html
        assert binding.packet_sha256 not in html

        status, navigation, _ = _request(
            server,
            "GET",
            server.path.replace(
                "/view", "/evidence/search?query=Exact%20reference&limit=1"
            ),
        )
        assert status == 200
        assert navigation["hits"] == [
            {
                "evidence_id": "EVID-SNAP-1",
                "document_id": "DOC-SNAP-1",
                "revision_id": "REV-SNAP-1",
                "page_number": 1,
                "bbox": [10.0, 10.0, 500.0, 30.0],
                "source_hash": "a" * 64,
                "title": "Snapshot source",
                "text": "Exact reference text",
                "citation_id": "CIT-EVID-SNAP-1",
            }
        ]
        assert len(str(navigation["evidence_snapshot_hash"])) == 64
        assert len(str(navigation["evidence_db_sha256"])) == 64
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_workbench_rejects_duplicate_host_and_origin_headers(tmp_path: Path) -> None:
    server, thread = _start(_workspace(tmp_path))
    try:
        host, port = server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.putrequest("GET", server.path, skip_host=True)
        connection.putheader("Host", f"{host}:{port}")
        connection.putheader("Host", "localhost")
        connection.endheaders()
        assert connection.getresponse().status == 403
        connection.close()

        payload = b'{"expected_revision":1}'
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.putrequest("POST", server.path.replace("/view", "/formalize"), skip_host=True)
        connection.putheader("Host", f"{host}:{port}")
        connection.putheader("Origin", f"http://{host}:{port}")
        connection.putheader("Origin", "http://localhost")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(len(payload)))
        connection.endheaders(payload)
        assert connection.getresponse().status == 403
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_workbench_rejects_wrong_token_and_origin_and_sets_shared_security_headers(
    tmp_path: Path,
) -> None:
    server, thread = _start(_workspace(tmp_path))
    try:
        status, payload, headers = _request(
            server,
            "GET",
            server.path.replace(TOKEN, "b" * 43),
        )
        assert (status, payload) == (403, {"error": "FORBIDDEN"})
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"

        status, payload, _ = _request(
            server,
            "POST",
            server.path.replace("/view", "/formalize"),
            body=b'{"expected_revision":1}',
            origin="http://localhost",
        )
        assert (status, payload) == (403, {"error": "FORBIDDEN"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_workbench_rejects_oversized_header_only_full_and_partial_senders(tmp_path: Path) -> None:
    server, thread = _start(_workspace(tmp_path), max_body_bytes=32)
    try:
        endpoint = server.path.replace("/view", "/formalize")
        status, payload, _ = _request(
            server,
            "POST",
            endpoint,
            body=b"x" * 33,
        )
        assert (status, payload) == (413, {"error": "BODY_TOO_LARGE"})

        host, port = server.server_address
        for send_body in (False, True):
            sender = socket.create_connection((host, port), timeout=2)
            sender.settimeout(2)
            request = (
                f"POST {endpoint} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Origin: http://{host}:{port}\r\n"
                "Content-Type: application/json\r\n"
                "Content-Length: 100000\r\n\r\n"
            ).encode("ascii")
            sender.sendall(request)
            if send_body:
                sender.sendall(b"{")
            response = sender.recv(4096)
            assert b" 413 " in response
            sender.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_workbench_rejects_stale_revision_and_reviewer_override(tmp_path: Path) -> None:
    server, thread = _start(_workspace(tmp_path))
    try:
        endpoint = server.path.replace("/view", "/issues")
        request = {
            "expected_revision": 1,
            "issue_id": "ISSUE-001",
            "question": "What does the evidence say?",
            "work_state": "DRAFT",
            "depends_on": [],
        }
        status, payload, _ = _request(server, "POST", endpoint, body=json.dumps(request).encode())
        assert status == 200
        assert payload["matter"]["revision"] == 2

        request["issue_id"] = "ISSUE-002"
        status, payload, _ = _request(server, "POST", endpoint, body=json.dumps(request).encode())
        assert (status, payload) == (409, {"error": "STALE_MATTER_REVISION"})

        request["expected_revision"] = 2
        request["reviewer_id"] = "different-reviewer"
        status, payload, _ = _request(server, "POST", endpoint, body=json.dumps(request).encode())
        assert (status, payload) == (400, {"error": "REVIEWER_ID_READONLY"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_detached_workbench_lifecycle_is_token_bound_and_removes_stale_state(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    serve_workbench(
        workspace,
        MATTER_ID,
        reviewer_id=REVIEWER_ID,
        detach=True,
        idle_timeout_seconds=10,
    )
    try:
        status = workbench_server_status(workspace, MATTER_ID)
        assert status["running"] is True
        assert status["reviewer_id"] == REVIEWER_ID
        stop_workbench_server(workspace, MATTER_ID)
        deadline = time.monotonic() + 3
        while (
            workbench_server_status(workspace, MATTER_ID)["running"] and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert workbench_server_status(workspace, MATTER_ID) == {
            "running": False,
            "matter_id": MATTER_ID,
        }
    finally:
        if workbench_server_status(workspace, MATTER_ID)["running"]:
            stop_workbench_server(workspace, MATTER_ID)
