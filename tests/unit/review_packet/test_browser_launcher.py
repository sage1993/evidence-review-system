from __future__ import annotations

import hashlib
from types import SimpleNamespace

from evidence_review.review_packet import browser_launcher


def test_windows_server_process_identity_uses_command_line(monkeypatch) -> None:
    token = "server-token"
    command_line = (
        "C:\\Python\\python.exe -m evidence_review.review_packet.server_process "
        "--workspace C:\\workspace --run-id RUN-123 --token server-token"
    )
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=command_line)

    monkeypatch.setattr(browser_launcher.os, "name", "nt")
    monkeypatch.setattr(browser_launcher.subprocess, "run", fake_run)

    assert browser_launcher._matches_server_process(
        123,
        "RUN-123",
        hashlib.sha256(token.encode("ascii")).hexdigest(),
    )
    assert calls[0][0][0][0:3] == ["powershell.exe", "-NoProfile", "-NonInteractive"]
    assert "ProcessId=123" in calls[0][0][0][4]


def test_server_status_retries_transient_windows_identity_query(
    monkeypatch, tmp_path
) -> None:
    token = "server-token"
    state_path = tmp_path / "runs" / "RUN-123" / "review-server.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        browser_launcher.json.dumps(
            {
                "pid": 123,
                "port": 8123,
                "run_id": "RUN-123",
                "token_sha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    identity_results = iter((False, False, True))
    monkeypatch.setattr(browser_launcher.os, "name", "nt")
    monkeypatch.setattr(browser_launcher, "_process_is_alive", lambda _pid: True)
    monkeypatch.setattr(
        browser_launcher,
        "_matches_server_process",
        lambda _pid, _run_id, _token_hash: next(identity_results),
    )

    assert browser_launcher.review_server_status(tmp_path, "RUN-123")["running"] is True
    assert state_path.is_file()



def test_http_readiness_and_browser_dispatch_are_tracked_separately(
    monkeypatch, tmp_path
) -> None:
    run_id = "RUN-READINESS-0001"
    run = tmp_path / "runs" / run_id
    run.mkdir(parents=True)
    fake_server = SimpleNamespace(
        url="http://127.0.0.1:8123/runs/RUN-READINESS-0001/token/review",
        _readiness_status="DISPATCHED",
        _browser_dispatched=False,
        close=lambda: None,
    )
    monkeypatch.setattr(
        browser_launcher,
        "review_server_status",
        lambda *_args, **_kwargs: {"running": False, "run_id": run_id},
    )
    monkeypatch.setattr(
        browser_launcher,
        "_start_review_server",
        lambda *_args, **_kwargs: fake_server,
    )
    monkeypatch.setattr(
        browser_launcher,
        "_wait_for_protected_http_ready",
        lambda _url: "HTTP_READY",
    )
    monkeypatch.setattr(browser_launcher, "append_stage", lambda *_args, **_kwargs: None)

    url = browser_launcher.open_protected_review_workspace(
        tmp_path,
        run_id,
        browser=lambda _url: True,
    )
    try:
        assert url == fake_server.url
        assert fake_server._readiness_status == "HTTP_READY"
        assert fake_server._browser_dispatched is True
        assert "VISUAL_READY" in browser_launcher.ReviewOpenStatus.__args__
    finally:
        browser_launcher.close_open_review_servers()
