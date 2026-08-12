"""Launch protected loopback review workspaces for finalized review runs."""

from __future__ import annotations

import os
import queue
import secrets
import stat
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, Thread
from typing import TextIO

from ansim_review.contracts.identifiers import validate_identifier

_REPARSE_POINT_ATTRIBUTE = 0x400
_ACTIVE_SERVERS: dict[tuple[Path, str], ReviewWorkspaceServer] = {}
_ACTIVE_SERVERS_LOCK = Lock()
_READY_TIMEOUT_SECONDS = 2.0


def _readline_with_timeout(stream: TextIO) -> str:
    """Read child readiness without allowing a broken child to hang the CLI."""
    result: queue.Queue[str] = queue.Queue(maxsize=1)

    def read() -> None:
        try:
            result.put(stream.readline())
        except Exception:
            result.put("")

    Thread(target=read, daemon=True).start()
    try:
        return result.get(timeout=_READY_TIMEOUT_SECONDS)
    except queue.Empty:
        return ""


def _is_regular_file(path: Path) -> bool:
    try:
        status = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(status.st_mode)
        and not stat.S_ISLNK(status.st_mode)
        and not bool(getattr(status, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE)
    )


def _required_artifacts(workspace_root: Path, run_id: str) -> None:
    for name in ("final-review-packet.json", "review.html"):
        artifact = workspace_root / "runs" / run_id / name
        if not _is_regular_file(artifact):
            raise FileNotFoundError(artifact)
        artifact.read_bytes()


def _server_key(workspace_root: Path, run_id: str) -> tuple[Path, str]:
    return (workspace_root.resolve(strict=True), validate_identifier(run_id, "run_id"))


@dataclass(slots=True)
class ReviewWorkspaceServer:
    """A running protected review server that must be closed by its owner."""

    _process: subprocess.Popen[str]
    _run_id: str
    _token: str
    _url: str
    _closed: bool = False
    _close_lock: Lock = field(default_factory=Lock)

    @property
    def url(self) -> str:
        return self._url

    def close(self) -> None:
        """Stop the serving thread and release the loopback port exactly once."""
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        self._process.terminate()
        self._process.wait(timeout=5)

    def wait(self) -> None:
        """Wait until the server session is closed."""
        self._process.wait()


def _start_review_server(workspace_root: Path, run_id: str) -> ReviewWorkspaceServer:
    validated_run_id = validate_identifier(run_id, "run_id")
    _required_artifacts(workspace_root, validated_run_id)
    token = secrets.token_urlsafe(32)
    command = (
        sys.executable,
        "-m",
        "ansim_review.review_packet.server_process",
        "--workspace",
        str(workspace_root.resolve(strict=True)),
        "--run-id",
        validated_run_id,
        "--token",
        token,
    )
    child_python_path = str(Path(__file__).parents[2]) + os.pathsep + os.environ.get(
        "PYTHONPATH", ""
    )
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
        env={
            **os.environ,
            "PYTHONPATH": child_python_path,
        },
    )
    try:
        assert process.stdout is not None
        port = int(_readline_with_timeout(process.stdout).strip())
    except (OSError, ValueError, AssertionError):
        process.terminate()
        process.wait(timeout=2)
        raise OSError("protected review server did not start") from None
    url = f"http://127.0.0.1:{port}/runs/{validated_run_id}/{token}/review"
    return ReviewWorkspaceServer(process, validated_run_id, token, url)


def close_open_review_servers() -> None:
    """Close all retained browser-session servers during orderly shutdown."""
    with _ACTIVE_SERVERS_LOCK:
        active_servers = tuple(_ACTIVE_SERVERS.values())
        _ACTIVE_SERVERS.clear()
    for active_server in active_servers:
        active_server.close()


def wait_for_open_review_server(workspace_root: Path, run_id: str) -> None:
    """Keep one retained browser-session server alive until it is closed."""
    with _ACTIVE_SERVERS_LOCK:
        active_server = _ACTIVE_SERVERS.get(_server_key(workspace_root, run_id))
    if active_server is None:
        raise RuntimeError("protected review server is not running")
    active_server.wait()


def close_open_review_server(workspace_root: Path, run_id: str) -> None:
    """Close one retained browser-session server without affecting other runs."""
    with _ACTIVE_SERVERS_LOCK:
        active_server = _ACTIVE_SERVERS.pop(_server_key(workspace_root, run_id), None)
    if active_server is not None:
        active_server.close()


def open_protected_review_workspace(
    workspace_root: Path,
    run_id: str,
    *,
    browser: Callable[[str], bool],
) -> str:
    """Open one finalized run through a retained, tokenized loopback server."""
    server = _start_review_server(workspace_root, run_id)
    try:
        if not browser(server.url):
            raise OSError("browser did not open protected review URL")
    except Exception as error:
        server.close()
        if isinstance(error, OSError):
            raise
        raise OSError("browser failed to open protected review URL") from error

    key = _server_key(workspace_root, run_id)
    with _ACTIVE_SERVERS_LOCK:
        previous = _ACTIVE_SERVERS.get(key)
        _ACTIVE_SERVERS[key] = server
    if previous is not None:
        previous.close()
    return server.url


__all__ = [
    "ReviewWorkspaceServer",
    "close_open_review_server",
    "close_open_review_servers",
    "open_protected_review_workspace",
    "wait_for_open_review_server",
]
