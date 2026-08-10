"""Launch protected loopback review workspaces for finalized review runs."""

from __future__ import annotations

import secrets
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import cast

from ansim_review.contracts.identifiers import validate_identifier
from ansim_review.review_packet.local_server import create_review_server

_REPARSE_POINT_ATTRIBUTE = 0x400
_ACTIVE_SERVERS: dict[tuple[Path, str], ReviewWorkspaceServer] = {}
_ACTIVE_SERVERS_LOCK = Lock()


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

    _server: ThreadingHTTPServer
    _thread: Thread
    _run_id: str
    _token: str
    _closed: bool = False
    _close_lock: Lock = field(default_factory=Lock)

    @property
    def url(self) -> str:
        host, port = cast(tuple[str, int], self._server.server_address)
        return f"http://{host}:{port}/runs/{self._run_id}/{self._token}/review"

    def close(self) -> None:
        """Stop the serving thread and release the loopback port exactly once."""
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise RuntimeError("protected review server did not stop")

    def wait(self) -> None:
        """Wait until the server session is closed."""
        self._thread.join()


def _start_review_server(workspace_root: Path, run_id: str) -> ReviewWorkspaceServer:
    validated_run_id = validate_identifier(run_id, "run_id")
    _required_artifacts(workspace_root, validated_run_id)
    token = secrets.token_urlsafe(32)
    server = create_review_server(workspace_root, run_tokens={validated_run_id: token})
    thread = Thread(
        target=server.serve_forever,
        name="protected-review-server",
    )
    try:
        thread.start()
    except BaseException:
        server.server_close()
        raise
    return ReviewWorkspaceServer(server, thread, validated_run_id, token)


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
