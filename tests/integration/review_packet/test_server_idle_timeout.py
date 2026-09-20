from __future__ import annotations

import hashlib
import http.client
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from evidence_review.review_packet.browser_launcher import review_server_status

RUN_ID = "RUN-0123456789ABCDEF0123"
TOKEN = "a" * 43


def _workspace(tmp_path: Path) -> Path:
    run_directory = tmp_path / "runs" / RUN_ID
    run_directory.mkdir(parents=True)
    (run_directory / "final-review-packet.json").write_text(
        '{"human_decision":null}', encoding="utf-8"
    )
    model = {
        "run_id": RUN_ID,
        "status": "READY_FOR_HUMAN_REVIEW",
        "display_status": "READY_FOR_HUMAN_REVIEW",
        "question": "idle-timeout protected review",
        "claims": [],
        "review_items": [],
        "calculations": [],
        "rules": [],
        "exceptions": [],
        "conflicts": [],
        "abstention_reasons": [],
        "summary": {},
        "audit": {},
    }
    (run_directory / "review.html").write_text(
        '<div class="app-shell"></div>'
        '<script id="review-model" type="application/json">'
        + json.dumps(model, sort_keys=True, separators=(",", ":"))
        + "</script>",
        encoding="utf-8",
    )
    return tmp_path


def _start_server(workspace: Path, timeout_seconds: float) -> subprocess.Popen[str]:
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
            str(timeout_seconds),
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


def _get(port: int, run_id: str, token: str) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.request(
        "GET",
        f"/runs/{run_id}/{token}/review",
        headers={"Host": f"127.0.0.1:{port}"},
    )
    response = connection.getresponse()
    response.read()
    status = response.status
    connection.close()
    return status


def _post_decision(port: int, packet: bytes) -> int:
    payload = json.dumps(
        {
            "reviewer_id": "reviewer-01",
            "decision": "SATISFIED",
            "notes": "reviewed",
        }
    ).encode("utf-8")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.request(
        "POST",
        f"/runs/{RUN_ID}/{TOKEN}/decision",
        body=payload,
        headers={
            "Host": f"127.0.0.1:{port}",
            "Origin": f"http://127.0.0.1:{port}",
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
        },
    )
    response = connection.getresponse()
    response.read()
    status = response.status
    connection.close()
    return status


def _wait_for_exit(process: subprocess.Popen[str], timeout: float = 6.0) -> int:
    deadline = time.monotonic() + timeout
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert process.poll() is not None, "detached server did not exit before timeout"
    return process.returncode


def test_detached_server_exits_after_idle_timeout_and_cleans_state(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    process = _start_server(workspace, 1.0)
    try:
        port = _read_port(process)
        assert _get(port, RUN_ID, TOKEN) == 200
        state_path = workspace / "runs" / RUN_ID / "review-server.json"
        assert state_path.is_file()

        assert _wait_for_exit(process) == 0
        assert not state_path.exists()
        assert review_server_status(workspace, RUN_ID) == {
            "running": False,
            "run_id": RUN_ID,
        }

        with pytest.raises(OSError):
            _get(port, RUN_ID, TOKEN)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_valid_activity_extends_idle_deadline(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    process = _start_server(workspace, 1.5)
    try:
        port = _read_port(process)
        time.sleep(0.9)
        assert _get(port, RUN_ID, TOKEN) == 200
        time.sleep(0.9)
        assert process.poll() is None
        assert _wait_for_exit(process) == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_invalid_token_does_not_extend_idle_deadline(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    process = _start_server(workspace, 1.0)
    try:
        port = _read_port(process)
        assert _get(port, RUN_ID, "b" * 43) == 403
        assert _wait_for_exit(process) == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_idle_timeout_state_records_configured_value(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    process = _start_server(workspace, 2.5)
    try:
        _read_port(process)
        state_path = workspace / "runs" / RUN_ID / "review-server.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["idle_timeout_seconds"] == 2.5
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_successful_decision_post_extends_idle_deadline(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    packet = (workspace / "runs" / RUN_ID / "final-review-packet.json").read_bytes()
    process = _start_server(workspace, 1.5)
    try:
        port = _read_port(process)
        time.sleep(0.9)
        assert _post_decision(port, packet) == 201
        time.sleep(0.9)
        assert process.poll() is None
        assert _wait_for_exit(process) == 0
        assert len(tuple((workspace / "runs" / RUN_ID / "human-decisions").glob("*.json"))) == 1
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_explicit_stop_terminates_verified_server_and_cleans_state(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    process = _start_server(workspace, 30.0)
    try:
        _read_port(process)
        state_path = workspace / "runs" / RUN_ID / "review-server.json"
        assert state_path.is_file()
        from evidence_review.review_packet.browser_launcher import stop_review_server

        stop_review_server(workspace, RUN_ID)
        assert _wait_for_exit(process) is not None
        assert not state_path.exists()
        assert review_server_status(workspace, RUN_ID)["running"] is False
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_unrelated_live_pid_state_is_removed_without_signaling_process(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    state_path = workspace / "runs" / RUN_ID / "review-server.json"
    state_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "port": 12345,
                "run_id": RUN_ID,
                "token_sha256": hashlib.sha256(TOKEN.encode("ascii")).hexdigest(),
            }
        ),
        encoding="utf-8",
    )

    assert review_server_status(workspace, RUN_ID) == {
        "running": False,
        "run_id": RUN_ID,
    }
    assert not state_path.exists()
