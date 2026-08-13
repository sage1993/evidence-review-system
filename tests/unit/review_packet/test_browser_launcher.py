from __future__ import annotations

import hashlib
from types import SimpleNamespace

from ansim_review.review_packet import browser_launcher


def test_windows_server_process_identity_uses_command_line(monkeypatch) -> None:
    token = "server-token"
    command_line = (
        "C:\\Python\\python.exe -m ansim_review.review_packet.server_process "
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