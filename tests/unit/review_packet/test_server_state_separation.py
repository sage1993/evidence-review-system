from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evidence_review.review_packet import browser_launcher, server_process
from evidence_review.review_packet.server_runtime import review_runtime_directory


@pytest.mark.parametrize("status", ["OK", "BYPASS_DETECTED", "SOURCE_MISMATCH"])
def test_installed_detached_environment_never_injects_source(
    monkeypatch: pytest.MonkeyPatch, status: str,
) -> None:
    import evidence_review.diagnostics as diagnostics

    monkeypatch.delenv("PYTHONPATH", raising=False)
    monkeypatch.setattr(diagnostics, "collect_runtime_diagnostics", lambda: (
        SimpleNamespace(runtime_mode="installed", status=status)
    ))
    if status == "OK":
        assert "PYTHONPATH" not in browser_launcher._server_environment()
    else:
        with pytest.raises(OSError, match=status):
            browser_launcher._server_environment()

RUN_ID = "RUN-0123456789ABCDEF0123"


def test_server_state_never_writes_to_immutable_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "runs" / RUN_ID
    run.mkdir(parents=True)
    packet = run / "final-review-packet.json"
    packet.write_bytes(b'{"human_decision":null}')
    original_open = Path.open

    def reject_run_writes(path: Path, mode: str = "r", *args, **kwargs):
        if path.is_relative_to(run) and any(flag in mode for flag in "wax+"):
            raise PermissionError("immutable RUN")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_run_writes)
    monkeypatch.setattr(server_process, "create_review_server", lambda *a, **k: SimpleNamespace(
        server_address=("127.0.0.1", 8123), server_close=lambda: None,
    ))
    monkeypatch.setattr(server_process, "configure_case_visual_server", lambda _: None)
    monkeypatch.setattr(server_process.signal, "signal", lambda *a: None)
    state_path = tmp_path / ".review-runtime" / RUN_ID / "review-server.json"

    def inspect_state(_server: object) -> None:
        document = json.loads(state_path.read_text(encoding="utf-8"))
        assert document["run_id"] == RUN_ID
        assert document["port"] == 8123

    monkeypatch.setattr(server_process, "serve_with_idle_timeout", inspect_state)
    assert server_process.main([
        "--workspace", str(tmp_path), "--run-id", RUN_ID, "--token", "test-token",
    ]) == 0
    assert not state_path.exists()
    assert packet.read_bytes() == b'{"human_decision":null}'
    assert sorted(path.name for path in run.iterdir()) == ["final-review-packet.json"]


def test_browser_operational_metrics_are_outside_immutable_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "runs" / RUN_ID
    run.mkdir(parents=True)
    fake_server = SimpleNamespace(
        url=f"http://127.0.0.1:8123/runs/{RUN_ID}/token/review",
        _readiness_status="DISPATCHED", _browser_dispatched=False, close=lambda: None,
    )
    monkeypatch.setattr(browser_launcher, "review_server_status", lambda *a: {"running": False})
    monkeypatch.setattr(browser_launcher, "_start_review_server", lambda *a, **k: fake_server)
    monkeypatch.setattr(browser_launcher, "_wait_for_protected_http_ready", lambda _: "HTTP_READY")
    monkeypatch.setattr(browser_launcher, "_ACTIVE_SERVERS", {})
    destinations = []
    monkeypatch.setattr(
        browser_launcher, "append_stage", lambda path, stage: destinations.append(path)
    )
    browser_launcher.open_protected_review_workspace(tmp_path, RUN_ID, browser=lambda _: True)
    assert destinations
    assert all(path == tmp_path / ".review-runtime" / RUN_ID for path in destinations)


def test_stale_runtime_state_cannot_hide_live_legacy_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "runs" / RUN_ID
    runtime = tmp_path / ".review-runtime" / RUN_ID
    for directory, pid in ((run, 111), (runtime, 222)):
        directory.mkdir(parents=True)
        (directory / "review-server.json").write_text(json.dumps({
            "pid": pid, "port": 8123, "run_id": RUN_ID, "token_sha256": "a" * 64,
        }), encoding="utf-8")
    monkeypatch.setattr(
        browser_launcher, "_verified_process_is_alive", lambda pid, *args: pid == 111
    )
    status = browser_launcher.review_server_status(tmp_path, RUN_ID)
    assert status["running"] is True
    assert status["pid"] == 111
    assert (run / "review-server.json").is_file()
    assert not (runtime / "review-server.json").exists()


@pytest.mark.parametrize("level", ["root", "run"])
def test_runtime_state_rejects_linked_directories(
    tmp_path: Path, level: str,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    link = tmp_path / ".review-runtime"
    if level == "run":
        link.mkdir()
        link = link / RUN_ID
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink creation unavailable: {error}")
    with pytest.raises(ValueError, match="symlink|reparse"):
        review_runtime_directory(tmp_path, RUN_ID, create=True)
    assert list(external.iterdir()) == []


def test_server_start_rejects_unverifiable_existing_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(browser_launcher, "review_server_status", lambda *a: {
        "running": False, "run_id": RUN_ID, "reason_code": "PERMISSION_DENIED",
    })
    monkeypatch.setattr(browser_launcher, "_start_review_server", lambda *a, **k: (
        SimpleNamespace(url="unexpected new server")
    ))
    with pytest.raises(OSError, match="PERMISSION_DENIED"):
        browser_launcher.serve_review_server(tmp_path, RUN_ID)


def test_linked_runtime_cannot_mask_legacy_state_as_safely_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "runs" / RUN_ID
    run.mkdir(parents=True)
    legacy = run / "review-server.json"
    legacy.write_text(json.dumps({
        "pid": 111, "run_id": RUN_ID, "port": 8123, "token_sha256": "a" * 64,
    }), encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    try:
        (tmp_path / ".review-runtime").symlink_to(external, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink creation unavailable: {error}")
    monkeypatch.setattr(browser_launcher, "_verified_process_is_alive", lambda *a: True)
    monkeypatch.setattr(browser_launcher, "_start_review_server", lambda *a, **k: (
        SimpleNamespace(url="unexpected new server")
    ))
    assert browser_launcher.review_server_status(tmp_path, RUN_ID).get("reason_code") == (
        "SOURCE_MISMATCH"
    )
    with pytest.raises(OSError, match="SOURCE_MISMATCH"):
        browser_launcher.serve_review_server(tmp_path, RUN_ID)
    assert legacy.is_file()
    assert list(external.iterdir()) == []
