"""Launch protected loopback review workspaces for finalized review runs."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import queue
import re
import secrets
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, Thread
from typing import Literal, TextIO, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.observability.run_metrics import append_stage, finish_stage, start_stage
from evidence_review.review_packet.protected_projection import load_archive_review_model
from evidence_review.review_packet.server_runtime import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    review_runtime_directory,
    validate_idle_timeout,
)

_ACTIVE_SERVERS: dict[tuple[Path, str], ReviewWorkspaceServer] = {}
_ACTIVE_SERVERS_LOCK = Lock()
_READY_TIMEOUT_SECONDS = 2.0
# Startup includes interpreter launch and full packet/evidence verification before
# the child can publish its port; it is not the subsequent HTTP readiness probe.
_SERVER_START_TIMEOUT_SECONDS = 15.0
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_COMMAND_LINE_INFORMATION = 60
_STATUS_INFO_LENGTH_MISMATCH = -1073741820
_SERVER_IDENTITY_ATTEMPTS = 3
_WINDOWS_IDENTITY_QUERY_TIMEOUT_SECONDS = 3.0
_SERVER_IDENTITY_POLL_SECONDS = 0.05
_STILL_ACTIVE = 259
ReviewOpenStatus = Literal["DISPATCHED", "HTTP_READY", "VISUAL_READY", "FAILED"]


def _process_is_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
        open_process = kernel32.OpenProcess
        open_process.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
        open_process.restype = ctypes.c_void_p
        handle = open_process(_PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            get_exit_code = kernel32.GetExitCodeProcess
            get_exit_code.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            get_exit_code.restype = ctypes.c_int
            return bool(get_exit_code(handle, ctypes.byref(exit_code))) and (
                exit_code.value == _STILL_ACTIVE
            )
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError):
        return False

def _verified_process_is_alive(
    pid: int, run_id: str, token_hash: object
) -> bool:
    for attempt in range(_SERVER_IDENTITY_ATTEMPTS):
        if not _process_is_alive(pid):
            return False
        if _matches_server_process(pid, run_id, token_hash):
            return True
        if attempt + 1 < _SERVER_IDENTITY_ATTEMPTS:
            time.sleep(_SERVER_IDENTITY_POLL_SECONDS)
    return False


class _UnicodeString(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.USHORT),
        ("maximum_length", wintypes.USHORT),
        ("buffer", ctypes.c_void_p),
    ]


def _query_windows_command_line_native(pid: int) -> str | None:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
        ntdll = ctypes.WinDLL("ntdll")  # type: ignore[attr-defined,unused-ignore]
        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        handle = open_process(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            query = ntdll.NtQueryInformationProcess
            query.argtypes = [
                wintypes.HANDLE,
                wintypes.ULONG,
                wintypes.LPVOID,
                wintypes.ULONG,
                ctypes.POINTER(wintypes.ULONG),
            ]
            query.restype = wintypes.LONG
            length = wintypes.ULONG()
            status = query(
                handle,
                _PROCESS_COMMAND_LINE_INFORMATION,
                None,
                0,
                ctypes.byref(length),
            )
            if status not in (0, _STATUS_INFO_LENGTH_MISMATCH) or length.value < ctypes.sizeof(
                _UnicodeString
            ):
                return None
            buffer = ctypes.create_string_buffer(length.value)
            status = query(
                handle,
                _PROCESS_COMMAND_LINE_INFORMATION,
                buffer,
                length.value,
                ctypes.byref(length),
            )
            if status != 0:
                return None
            value = _UnicodeString.from_buffer(buffer)
            if not value.buffer or value.length == 0:
                return None
            return ctypes.wstring_at(value.buffer, value.length // ctypes.sizeof(ctypes.c_wchar))
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, ValueError):
        return None



def _readline_with_timeout(stream: TextIO) -> str:
    result: queue.Queue[str] = queue.Queue(maxsize=1)

    def read() -> None:
        try:
            result.put(stream.readline())
        except Exception:
            result.put("")

    Thread(target=read, daemon=True).start()
    try:
        return result.get(timeout=_SERVER_START_TIMEOUT_SECONDS)
    except queue.Empty:
        return ""


def _required_artifacts(workspace_root: Path, run_id: str) -> Path:
    workspace = verified_regular_directory(workspace_root, field="workspace root")
    runs_root = verified_regular_directory(workspace / "runs", field="runs root")
    run_directory = verified_regular_directory(
        runs_root / run_id,
        field="run directory",
    )
    for name in ("final-review-packet.json", "review.html"):
        artifact = verified_regular_file_below(
            run_directory,
            (name,),
            field=f"review artifact {name}",
        )
        artifact.read_bytes()
    return workspace


def _server_state_path(workspace_root: Path, run_id: str) -> Path | None:
    try:
        runtime = review_runtime_directory(workspace_root, run_id)
        return verified_regular_file_below(
            runtime, ("review-server.json",), field="review server state",
        )
    except FileNotFoundError:
        return _legacy_server_state_path(workspace_root, run_id)


def _legacy_server_state_path(workspace_root: Path, run_id: str) -> Path | None:
    # Observe a live pre-migration server, but never rewrite its immutable RUN.
    try:
        workspace = verified_regular_directory(workspace_root, field="workspace root")
        runs_root = verified_regular_directory(workspace / "runs", field="runs root")
        run_directory = verified_regular_directory(
            runs_root / run_id,
            field="run directory",
        )
        return verified_regular_file_below(
            run_directory,
            ("review-server.json",),
            field="review server state",
        )
    except FileNotFoundError:
        return None


def _remove_mutable_server_state(path: Path, workspace_root: Path, run_id: str) -> None:
    if path.parent == workspace_root.resolve() / ".review-runtime" / run_id:
        path.unlink(missing_ok=True)


def _server_key(workspace_root: Path, run_id: str) -> tuple[Path, str]:
    return (
        verified_regular_directory(workspace_root, field="workspace root"),
        validate_identifier(run_id, "run_id"),
    )


@dataclass(slots=True)
class ReviewWorkspaceServer:
    _process: subprocess.Popen[str]
    _run_id: str
    _token: str
    _url: str
    _readiness_status: ReviewOpenStatus = "DISPATCHED"
    _browser_dispatched: bool = False
    _closed: bool = False
    _close_lock: Lock = field(default_factory=Lock)

    @property
    def url(self) -> str:
        return self._url

    @property
    def readiness_status(self) -> ReviewOpenStatus:
        return self._readiness_status

    @property
    def browser_dispatched(self) -> bool:
        return self._browser_dispatched

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        self._process.terminate()
        self._process.wait(timeout=5)

    def wait(self) -> None:
        self._process.wait()


def _probe_protected_http_ready(url: str) -> ReviewOpenStatus:
    try:
        request = Request(
            url,
            headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
        )
        with urlopen(request, timeout=0.5) as response:
            if response.status != 200:
                return "FAILED"
            body = response.read()
    except (HTTPError, URLError, TimeoutError, OSError):
        return "FAILED"
    if b'data-protected-presentation="true"' not in body or b"data:image/" in body:
        return "FAILED"
    try:
        load_archive_review_model(body)
    except ValueError:
        return "FAILED"
    return "HTTP_READY"


def _wait_for_protected_http_ready(
    url: str,
    *,
    timeout_seconds: float = _READY_TIMEOUT_SECONDS,
) -> ReviewOpenStatus:
    deadline = time.monotonic() + timeout_seconds
    while True:
        status = _probe_protected_http_ready(url)
        if status == "HTTP_READY":
            return status
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "FAILED"
        time.sleep(min(0.05, remaining))


def _server_environment() -> dict[str, str]:
    from evidence_review.diagnostics import collect_runtime_diagnostics

    runtime = collect_runtime_diagnostics()
    if runtime.status not in {"OK", "NOT_A_CHECKOUT"}:
        raise OSError(f"protected review runtime is unverifiable: {runtime.status}")
    environment = dict(os.environ)
    if runtime.runtime_mode == "development":
        environment["PYTHONPATH"] = (
            str(Path(__file__).parents[2]) + os.pathsep + environment.get("PYTHONPATH", "")
        )
    return environment


def _start_review_server(
    workspace_root: Path,
    run_id: str,
    *,
    reviewer_id: str | None = None,
    idle_timeout_seconds: float = DEFAULT_IDLE_TIMEOUT_SECONDS,
) -> ReviewWorkspaceServer:
    validated_run_id = validate_identifier(run_id, "run_id")
    validated_idle_timeout = validate_idle_timeout(idle_timeout_seconds)
    validated_reviewer_id = (
        None
        if reviewer_id is None
        else validate_identifier(reviewer_id, "reviewer_id")
    )
    trusted_workspace = _required_artifacts(workspace_root, validated_run_id)
    token = secrets.token_urlsafe(32)
    command: tuple[str, ...] = (
        sys.executable,
        "-m",
        "evidence_review.review_packet.server_process",
        "--workspace",
        str(trusted_workspace),
        "--run-id",
        validated_run_id,
        "--token",
        token,
        "--idle-timeout-seconds",
        str(validated_idle_timeout),
    )
    if validated_reviewer_id is not None:
        command += ("--reviewer-id", validated_reviewer_id)
    child_environment = _server_environment()
    creationflags = (
        getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        if os.name == "nt"
        else 0
    )
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
        creationflags=creationflags,
        env=child_environment,
    )
    try:
        assert process.stdout is not None
        stdout = cast(TextIO, process.stdout)
        port = int(_readline_with_timeout(stdout).strip())
    except (OSError, ValueError, AssertionError):
        process.terminate()
        process.wait(timeout=2)
        raise OSError("protected review server did not start") from None
    url = f"http://127.0.0.1:{port}/runs/{validated_run_id}/{token}/review"
    return ReviewWorkspaceServer(process, validated_run_id, token, url)


def close_open_review_servers() -> None:
    with _ACTIVE_SERVERS_LOCK:
        active_servers = tuple(_ACTIVE_SERVERS.values())
        _ACTIVE_SERVERS.clear()
    for active_server in active_servers:
        active_server.close()


def wait_for_open_review_server(workspace_root: Path, run_id: str) -> None:
    with _ACTIVE_SERVERS_LOCK:
        active_server = _ACTIVE_SERVERS.get(_server_key(workspace_root, run_id))
    if active_server is None:
        raise RuntimeError("protected review server is not running")
    active_server.wait()


def close_open_review_server(workspace_root: Path, run_id: str) -> None:
    with _ACTIVE_SERVERS_LOCK:
        active_server = _ACTIVE_SERVERS.pop(_server_key(workspace_root, run_id), None)
    if active_server is not None:
        active_server.close()


def review_server_status(workspace_root: Path, run_id: str) -> dict[str, object]:
    validated_run_id = validate_identifier(run_id, "run_id")
    try:
        path = _server_state_path(workspace_root, validated_run_id)
        if path is None:
            return {"running": False, "run_id": validated_run_id}
        status = _read_server_status(path, workspace_root, validated_run_id)
        if status["running"]:
            return status
        if path.parent == workspace_root.resolve() / ".review-runtime" / validated_run_id:
            legacy = _legacy_server_state_path(workspace_root, validated_run_id)
            if legacy is not None:
                return _read_server_status(legacy, workspace_root, validated_run_id)
        return status
    except PermissionError:
        return {
            "running": False,
            "run_id": validated_run_id,
            "reason_code": "PERMISSION_DENIED",
        }
    except ValueError:
        return {
            "running": False,
            "run_id": validated_run_id,
            "reason_code": "SOURCE_MISMATCH",
        }
    except OSError:
        return {
            "running": False,
            "run_id": validated_run_id,
            "reason_code": "SOURCE_MISMATCH",
        }


def _read_server_status(
    path: Path, workspace_root: Path, validated_run_id: str,
) -> dict[str, object]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"running": False, "run_id": validated_run_id}
    except (OSError, json.JSONDecodeError):
        _remove_mutable_server_state(path, workspace_root, validated_run_id)
        return {"running": False, "run_id": validated_run_id}
    pid = state.get("pid") if isinstance(state, dict) else None
    if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
        _remove_mutable_server_state(path, workspace_root, validated_run_id)
        return {"running": False, "run_id": validated_run_id}
    if not _verified_process_is_alive(pid, validated_run_id, state.get("token_sha256")):
        _remove_mutable_server_state(path, workspace_root, validated_run_id)
        return {"running": False, "run_id": validated_run_id}
    return {
        "running": True,
        "run_id": validated_run_id,
        "pid": pid,
        "port": state.get("port"),
        "reviewer_id": state.get("reviewer_id"),
    }


def _matches_server_process(pid: int, run_id: str, token_hash: object) -> bool:
    if not isinstance(token_hash, str) or len(token_hash) != 64:
        return False
    if os.name == "nt":
        try:
            command_line = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine",
                ],
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_WINDOWS_IDENTITY_QUERY_TIMEOUT_SECONDS,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            command_line = ""
        if not command_line:
            command_line = _query_windows_command_line_native(pid) or ""
        if not command_line or "evidence_review.review_packet.server_process" not in command_line:
            return False
        run_match = re.search(r"(?:^|\s)--run-id\s+([^\s\"]+)", command_line)
        token_match = re.search(r"(?:^|\s)--token\s+([^\s\"]+)", command_line)
        if run_match is None or token_match is None:
            return False
        actual_run_id = run_match.group(1)
        token = token_match.group(1)
    else:
        try:
            arguments = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            return False
        decoded = [item.decode("utf-8") for item in arguments if item]
        if "evidence_review.review_packet.server_process" not in decoded:
            return False
        try:
            token = decoded[decoded.index("--token") + 1]
            actual_run_id = decoded[decoded.index("--run-id") + 1]
        except (ValueError, IndexError):
            return False
    return (
        actual_run_id == run_id
        and hashlib.sha256(token.encode("ascii")).hexdigest() == token_hash
    )

def stop_review_server(workspace_root: Path, run_id: str) -> None:
    validated_run_id = validate_identifier(run_id, "run_id")
    try:
        state_path = _server_state_path(workspace_root, validated_run_id)
    except (OSError, ValueError):
        return
    if state_path is None:
        return
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return
    status = review_server_status(workspace_root, validated_run_id)
    if not status["running"]:
        return
    pid = status["pid"]
    assert isinstance(pid, int)
    os.kill(pid, signal.SIGTERM)
    try:
        current = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return
    if (
        isinstance(state, dict)
        and isinstance(current, dict)
        and current.get("pid") == pid
        and current.get("token_sha256") == state.get("token_sha256")
    ):
        _remove_mutable_server_state(state_path, workspace_root, validated_run_id)


def serve_review_server(
    workspace_root: Path,
    run_id: str,
    *,
    reviewer_id: str | None = None,
    idle_timeout_seconds: float = DEFAULT_IDLE_TIMEOUT_SECONDS,
) -> str:
    validated_run_id = validate_identifier(run_id, "run_id")
    stale = review_server_status(workspace_root, validated_run_id)
    if stale.get("reason_code"):
        raise OSError(f"protected review server state is unverifiable: {stale['reason_code']}")
    if stale["running"]:
        raise RuntimeError("protected review server is already running")
    server = _start_review_server(
        workspace_root,
        validated_run_id,
        reviewer_id=reviewer_id,
        idle_timeout_seconds=idle_timeout_seconds,
    )
    return server.url


def open_protected_review_workspace(
    workspace_root: Path,
    run_id: str,
    *,
    browser: Callable[[str], bool],
    reviewer_id: str | None = None,
) -> str:
    validated_run_id = validate_identifier(run_id, "run_id")
    workspace = verified_regular_directory(workspace_root, field="workspace root")
    runs_root = verified_regular_directory(workspace / "runs", field="runs root")
    verified_regular_directory(
        runs_root / validated_run_id,
        field="run directory",
    )
    runtime_directory = review_runtime_directory(workspace, validated_run_id, create=True)
    stale = review_server_status(workspace_root, validated_run_id)
    if stale.get("reason_code"):
        raise OSError(f"protected review server state is unverifiable: {stale['reason_code']}")
    if stale["running"]:
        raise RuntimeError("protected review server is already running")

    server_timer = start_stage()
    try:
        server = _start_review_server(
            workspace_root,
            validated_run_id,
            reviewer_id=reviewer_id,
        )
    except Exception as error:
        append_stage(
            runtime_directory,
            finish_stage(
                "protected-server-start",
                server_timer,
                status="FAILED",
                reason_code=type(error).__name__.upper(),
            ),
        )
        raise
    append_stage(runtime_directory, finish_stage("protected-server-start", server_timer))

    readiness_timer = start_stage()
    readiness_status = _wait_for_protected_http_ready(server.url)
    server._readiness_status = readiness_status
    if readiness_status != "HTTP_READY":
        server.close()
        append_stage(
            runtime_directory,
            finish_stage(
                "protected-http-readiness",
                readiness_timer,
                status="FAILED",
                reason_code="HTTP_NOT_READY",
            ),
        )
        raise OSError("protected review did not become HTTP ready")
    append_stage(
        runtime_directory,
        finish_stage("protected-http-readiness", readiness_timer),
    )

    browser_timer = start_stage()
    try:
        if not browser(server.url):
            raise OSError("browser did not open protected review URL")
        server._browser_dispatched = True
    except Exception as error:
        server.close()
        append_stage(
            runtime_directory,
            finish_stage(
                "browser-dispatch",
                browser_timer,
                status="FAILED",
                reason_code=type(error).__name__.upper(),
            ),
        )
        if isinstance(error, OSError):
            raise
        raise OSError("browser failed to open protected review URL") from error
    append_stage(runtime_directory, finish_stage("browser-dispatch", browser_timer))

    key = _server_key(workspace_root, validated_run_id)
    with _ACTIVE_SERVERS_LOCK:
        previous = _ACTIVE_SERVERS.get(key)
        _ACTIVE_SERVERS[key] = server
    if previous is not None:
        previous.close()
    return server.url


__all__ = [
    "ReviewOpenStatus",
    "ReviewWorkspaceServer",
    "close_open_review_server",
    "close_open_review_servers",
    "open_protected_review_workspace",
    "review_server_status",
    "serve_review_server",
    "stop_review_server",
    "wait_for_open_review_server",
]
