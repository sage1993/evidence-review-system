"""Tokenized loopback server for mutable ReviewMatter Workbench operations."""

from __future__ import annotations

import argparse
import base64
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
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
from typing import IO, Any, cast

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.filesystem_trust import (
    verified_create_target_below,
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.local_http_transport import (
    ContentLengthError,
    loopback_request_is_authorized,
    reject_oversized_body,
    send_protected_response,
    validate_content_length,
)
from evidence_review.review_matter.contracts import review_matter_document
from evidence_review.review_matter.service import ReviewMatterService
from evidence_review.review_matter.store import MatterNotFound, MatterRevisionConflict
from evidence_review.review_packet.server_runtime import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    validate_idle_timeout,
)
from evidence_review.workbench.html_renderer import render_workbench_html
from evidence_review.workbench.routes import (
    ROUTE_CONTRACTS,
    RouteContract,
    RoutePayloadError,
    WorkbenchRoute,
    decode_payload,
    navigation_limit,
    parse_workbench_route,
    workbench_path,
)
from evidence_review.workbench.view_model import (
    build_workbench_view_model,
    draft_observations_from_matter,
    formal_run_history_from_bindings,
)

_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_READY_TIMEOUT_SECONDS = 2.0
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_CSP = "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"


def _html_csp(nonce: str) -> str:
    return (
        f"{_CSP}; connect-src 'self'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'"
    )


def _validated_token(token: object) -> str:
    if not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None:
        raise ValueError("workbench token must be a 32-128 character URL-safe string")
    return token


def _validated_matter_id(matter_id: object) -> str:
    value = validate_identifier(matter_id, "matter_id")
    if value.startswith("CASE-"):
        raise ValueError("matter_id must not use a drawing case identity")
    return value


def _state_name(matter_id: str) -> str:
    return f"workbench-server-{matter_id}.json"


def _existing_state_path(workspace: Path, matter_id: str) -> Path | None:
    try:
        root = verified_regular_directory(workspace, field="workspace root")
        return verified_regular_file_below(
            root,
            (_state_name(matter_id),),
            field="workbench server state",
        )
    except FileNotFoundError:
        return None


def _create_state_path(workspace: Path, matter_id: str) -> Path:
    root = verified_regular_directory(workspace, field="workspace root")
    return verified_create_target_below(
        root,
        (_state_name(matter_id),),
        field="workbench server state",
    )


class WorkbenchHTTPServer(ThreadingHTTPServer):
    """A loopback server bound to one mutable Matter and reviewer session."""

    daemon_threads = True

    def __init__(
        self,
        service: ReviewMatterService,
        *,
        matter_id: str,
        token: str,
        reviewer_id: str,
        max_body_bytes: int,
        idle_timeout_seconds: float | None,
    ) -> None:
        self.service = service
        self.matter_id = matter_id
        self.token = token
        self.reviewer_id = reviewer_id
        self.max_body_bytes = max_body_bytes
        self.idle_timeout_seconds = idle_timeout_seconds
        self.routes = {endpoint: contract.method for endpoint, contract in ROUTE_CONTRACTS.items()}
        self.route_contracts = dict(ROUTE_CONTRACTS)
        self._activity_lock = Lock()
        self._activity_event = Event()
        self._last_activity = time.monotonic()
        self._shutdown_started = False
        super().__init__(("127.0.0.1", 0), WorkbenchRequestHandler)
        host, port = cast(tuple[str, int], self.server_address)
        self.expected_host = f"{host}:{port}"
        self.origin = f"http://{self.expected_host}"
        self.path = workbench_path(self.matter_id, self.token)

    def mark_activity(self) -> bool:
        with self._activity_lock:
            if self._shutdown_started:
                return False
            self._last_activity = time.monotonic()
            self._activity_event.set()
            return True

    def begin_shutdown(self) -> bool:
        with self._activity_lock:
            if self._shutdown_started:
                return False
            self._shutdown_started = True
            self._activity_event.set()
            return True

    def idle_expired(self) -> bool:
        with self._activity_lock:
            return (
                self.idle_timeout_seconds is not None
                and not self._shutdown_started
                and time.monotonic() - self._last_activity >= self.idle_timeout_seconds
            )


class WorkbenchRequestHandler(BaseHTTPRequestHandler):
    """HTTP adapter that delegates every Matter operation to ReviewMatterService."""

    server_version = "evidence-review-workbench/1"
    sys_version = ""

    @property
    def state(self) -> WorkbenchHTTPServer:
        return cast(WorkbenchHTTPServer, self.server)

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _send_json(
        self,
        status: HTTPStatus,
        payload: Mapping[str, object],
        *,
        allow: str | None = None,
    ) -> None:
        send_protected_response(
            self,
            status,
            dump_bytes(dict(payload)),
            "application/json; charset=utf-8",
            content_security_policy=_CSP,
            allow=allow,
        )

    def _send_html(self, body: str, *, nonce: str) -> None:
        send_protected_response(
            self,
            HTTPStatus.OK,
            body.encode("utf-8"),
            "text/html; charset=utf-8",
            content_security_policy=_html_csp(nonce),
        )

    def _reject(
        self,
        status: HTTPStatus,
        code: str,
        *,
        allow: str | None = None,
    ) -> None:
        self._send_json(status, {"error": code}, allow=allow)

    def _route(self) -> WorkbenchRoute | None:
        route = parse_workbench_route(self.path, matter_id=self.state.matter_id)
        if route is None:
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
        return route

    def _authorized(self, route: WorkbenchRoute, *, require_origin: bool) -> bool:
        if not loopback_request_is_authorized(
            self.headers,
            expected_host=self.state.expected_host,
            expected_origin=self.state.origin,
            require_origin=require_origin,
            presented_token=route.token,
            expected_token=self.state.token,
        ):
            self._reject(HTTPStatus.FORBIDDEN, "FORBIDDEN")
            return False
        return True

    def _response(self, matter: object) -> dict[str, object]:
        return {
            "format": "evidence-review/workbench-response",
            "version": 1,
            "surface": "WORKBENCH",
            "reviewer_id": self.state.reviewer_id,
            "matter": review_matter_document(cast(Any, matter)),
        }

    def _require_method(self, route: WorkbenchRoute, method: str) -> RouteContract | None:
        contract = self.state.route_contracts[route.endpoint]
        if contract.method != method:
            self._reject(HTTPStatus.METHOD_NOT_ALLOWED, "METHOD_NOT_ALLOWED", allow=contract.method)
            return None
        return contract

    def do_GET(self) -> None:  # noqa: N802
        route = self._route()
        if route is None or not self._authorized(route, require_origin=False):
            return
        contract = self._require_method(route, "GET")
        if contract is None:
            return
        try:
            if route.endpoint == "view":
                matter = self.state.service.status(matter_id=self.state.matter_id)
                formal_runs = self.state.service.list_formal_runs(
                    matter_id=self.state.matter_id
                )
                nonce = base64.b64encode(secrets.token_bytes(18)).decode("ascii")
                self._send_html(
                    render_workbench_html(
                        build_workbench_view_model(
                            matter,
                            draft_observations=draft_observations_from_matter(matter),
                            formal_run_history=formal_run_history_from_bindings(
                                formal_runs
                            ),
                        ),
                        nonce=nonce,
                    ),
                    nonce=nonce,
                )
            elif route.endpoint == "state":
                self._send_json(
                    HTTPStatus.OK,
                    self._response(self.state.service.status(matter_id=self.state.matter_id)),
                )
            elif route.endpoint == "evidence/search":
                result = self.state.service.search(
                    matter_id=self.state.matter_id,
                    query=route.query["query"],
                    limit=navigation_limit(route.query),
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "format": "evidence-review/workbench-navigation-response",
                        "version": 1,
                        "surface": "WORKBENCH",
                        "reviewer_id": self.state.reviewer_id,
                        "query": result.query,
                        "evidence_snapshot_hash": result.evidence_snapshot_hash,
                        "evidence_db_sha256": result.evidence_db_sha256,
                        "hits": [
                            {
                                "evidence_id": hit.evidence_id,
                                "document_id": hit.document_id,
                                "revision_id": hit.revision_id,
                                "page_number": hit.page_number,
                                "bbox": [
                                    hit.bbox.left,
                                    hit.bbox.bottom,
                                    hit.bbox.right,
                                    hit.bbox.top,
                                ],
                                "source_hash": hit.source_hash,
                                "title": hit.title,
                                "text": hit.text,
                                "citation_id": hit.citation.citation_id,
                            }
                            for hit in result.hits
                        ],
                    },
                )
            else:
                self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
                return
        except (MatterNotFound, FileNotFoundError):
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return
        except (OSError, ValueError, RoutePayloadError):
            self._reject(HTTPStatus.BAD_REQUEST, "INVALID_REQUEST")
            return
        self.state.mark_activity()

    def _content_length(self) -> int | None:
        try:
            return validate_content_length(self.headers, self.state.max_body_bytes)
        except ContentLengthError as error:
            if error.length is not None:
                reject_oversized_body(self, error.length, self._reject)
                return None
            self._reject(
                HTTPStatus.LENGTH_REQUIRED
                if error.code == "CONTENT_LENGTH_REQUIRED"
                else HTTPStatus.BAD_REQUEST,
                error.code,
            )
            return None

    def _mutate(self, endpoint: str, payload: Mapping[str, object]) -> dict[str, object]:
        expected_revision = payload["expected_revision"]
        if endpoint == "issues":
            matter = self.state.service.add_issue(
                matter_id=self.state.matter_id,
                expected_revision=cast(int, expected_revision),
                issue_id=cast(str, payload["issue_id"]),
                question=cast(str, payload["question"]),
                work_state=cast(Any, payload["work_state"]),
                depends_on=cast(list[str], payload["depends_on"]),
            )
            return self._response(matter)
        if endpoint == "evidence/bind":
            return self._response(
                self.state.service.bind_evidence(
                    matter_id=self.state.matter_id,
                    expected_revision=cast(int, expected_revision),
                )
            )
        if endpoint == "evidence/select":
            return self._response(
                self.state.service.select_evidence(
                    matter_id=self.state.matter_id,
                    expected_revision=cast(int, expected_revision),
                    query=cast(str, payload["query"]),
                    evidence_id=cast(str, payload["evidence_id"]),
                    limit=cast(int, payload["limit"]),
                )
            )
        if endpoint == "formalize":
            formalized = self.state.service.formalize(
                matter_id=self.state.matter_id,
                expected_revision=cast(int, expected_revision),
            )
            return {
                "format": "evidence-review/workbench-formalization-response",
                "version": 1,
                "surface": "WORKBENCH",
                "reviewer_id": self.state.reviewer_id,
                "formalization": {
                    "matter_id": formalized.snapshot.matter_id,
                    "matter_revision": formalized.snapshot.matter_revision,
                    "snapshot_id": formalized.snapshot.snapshot_id,
                    "run_id": formalized.prepared.run_id,
                    "status": formalized.prepared.status,
                },
            }
        raise RuntimeError("unknown mutation endpoint")

    def do_POST(self) -> None:  # noqa: N802
        route = self._route()
        if route is None or not self._authorized(route, require_origin=True):
            return
        contract = self._require_method(route, "POST")
        if contract is None:
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
        if content_type != "application/json":
            self._reject(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_MEDIA_TYPE")
            return
        length = self._content_length()
        if length is None:
            return
        body = self.rfile.read(length)
        if len(body) != length:
            self._reject(HTTPStatus.BAD_REQUEST, "INCOMPLETE_BODY")
            return
        try:
            payload = decode_payload(body, contract)
            response = self._mutate(route.endpoint, payload)
        except RoutePayloadError as error:
            self._reject(HTTPStatus.BAD_REQUEST, error.code)
            return
        except MatterRevisionConflict:
            self._reject(HTTPStatus.CONFLICT, "STALE_MATTER_REVISION")
            return
        except MatterNotFound:
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return
        except (FileNotFoundError, OSError, ValueError):
            self._reject(HTTPStatus.BAD_REQUEST, "INVALID_REQUEST")
            return
        self.state.mark_activity()
        self._send_json(HTTPStatus.OK, response)

    def _method_not_allowed(self) -> None:
        route = self._route()
        if route is None or not self._authorized(route, require_origin=False):
            return
        self._reject(
            HTTPStatus.METHOD_NOT_ALLOWED,
            "METHOD_NOT_ALLOWED",
            allow=self.state.route_contracts[route.endpoint].method,
        )

    do_DELETE = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_PUT = _method_not_allowed


def create_workbench_server(
    workspace_root: Path,
    *,
    matter_id: str,
    token: str,
    reviewer_id: str,
    max_body_bytes: int = 65536,
    idle_timeout_seconds: float | None = None,
) -> WorkbenchHTTPServer:
    """Create a loopback-only server for exactly one existing mutable Matter."""
    if (
        isinstance(max_body_bytes, bool)
        or not isinstance(max_body_bytes, int)
        or max_body_bytes < 1
    ):
        raise ValueError("max_body_bytes must be positive")
    if idle_timeout_seconds is not None:
        validate_idle_timeout(idle_timeout_seconds)
    service = ReviewMatterService.open(workspace_root)
    validated_matter_id = _validated_matter_id(matter_id)
    service.status(matter_id=validated_matter_id)
    return WorkbenchHTTPServer(
        service,
        matter_id=validated_matter_id,
        token=_validated_token(token),
        reviewer_id=validate_identifier(reviewer_id, "reviewer_id"),
        max_body_bytes=max_body_bytes,
        idle_timeout_seconds=None if idle_timeout_seconds is None else float(idle_timeout_seconds),
    )


def serve_with_idle_timeout(server: WorkbenchHTTPServer) -> None:
    """Serve until stop or a Workbench-valid request leaves the idle window."""
    monitor_stop = Event()

    def supervise() -> None:
        while server.idle_timeout_seconds is not None:
            with server._activity_lock:
                remaining = max(
                    0.0, server.idle_timeout_seconds - (time.monotonic() - server._last_activity)
                )
            if monitor_stop.wait(min(remaining, 0.5)):
                return
            if server.idle_expired() and server.begin_shutdown():
                server.shutdown()
                return

    monitor = Thread(target=supervise, daemon=True)
    monitor.start()
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        monitor_stop.set()
        server._activity_event.set()
        monitor.join(timeout=1)


def _process_is_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            return (
                bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)))
                and exit_code.value == _STILL_ACTIVE
            )
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError):
        return False


def _server_command_matches(pid: int, matter_id: str, token_hash: object) -> bool:
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
                timeout=3,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return False
        if "evidence_review.workbench.local_server" not in command_line:
            return False
        arguments = command_line.split()
    else:
        try:
            arguments = [
                item.decode("utf-8")
                for item in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
                if item
            ]
        except OSError:
            return False
        if "evidence_review.workbench.local_server" not in arguments:
            return False
    try:
        actual_matter_id = arguments[arguments.index("--matter-id") + 1]
        token = arguments[arguments.index("--token") + 1]
    except (ValueError, IndexError):
        return False
    return (
        actual_matter_id == matter_id
        and hashlib.sha256(token.encode("ascii")).hexdigest() == token_hash
    )


def _verified_server_is_alive(pid: int, matter_id: str, token_hash: object) -> bool:
    return _process_is_alive(pid) and _server_command_matches(pid, matter_id, token_hash)


def workbench_server_status(workspace_root: Path, matter_id: str) -> dict[str, object]:
    """Return state only for an exact live Workbench process, clearing stale state."""
    validated_matter_id = _validated_matter_id(matter_id)
    try:
        path = _existing_state_path(workspace_root, validated_matter_id)
    except (OSError, ValueError):
        return {"running": False, "matter_id": validated_matter_id}
    if path is None:
        return {"running": False, "matter_id": validated_matter_id}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        pid = state.get("pid") if isinstance(state, dict) else None
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
            raise ValueError("invalid workbench server state")
    except (OSError, ValueError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return {"running": False, "matter_id": validated_matter_id}
    if not _verified_server_is_alive(pid, validated_matter_id, state.get("token_sha256")):
        path.unlink(missing_ok=True)
        return {"running": False, "matter_id": validated_matter_id}
    return {
        "running": True,
        "matter_id": validated_matter_id,
        "pid": pid,
        "port": state.get("port"),
        "reviewer_id": state.get("reviewer_id"),
    }


def stop_workbench_server(workspace_root: Path, matter_id: str) -> None:
    """Stop only the still-verified exact Workbench process for one Matter."""
    validated_matter_id = _validated_matter_id(matter_id)
    status = workbench_server_status(workspace_root, validated_matter_id)
    if not status["running"]:
        return
    pid = cast(int, status["pid"])
    path = _existing_state_path(workspace_root, validated_matter_id)
    if path is None:
        return
    state = json.loads(path.read_text(encoding="utf-8"))
    os.kill(pid, signal.SIGTERM)
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if (
        isinstance(state, dict)
        and isinstance(current, dict)
        and current.get("pid") == pid
        and current.get("token_sha256") == state.get("token_sha256")
    ):
        path.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class WorkbenchServerSession:
    """Detached Workbench server identity returned to the caller."""

    port: int
    path: str
    url: str


def _readline_with_timeout(stream: IO[str]) -> str:
    values: queue.Queue[str] = queue.Queue(maxsize=1)
    Thread(target=lambda: values.put(stream.readline()), daemon=True).start()
    try:
        return values.get(timeout=_READY_TIMEOUT_SECONDS)
    except queue.Empty:
        return ""


def serve_workbench(
    workspace_root: Path,
    matter_id: str,
    *,
    reviewer_id: str,
    detach: bool,
    idle_timeout_seconds: float = DEFAULT_IDLE_TIMEOUT_SECONDS,
) -> WorkbenchServerSession:
    """Start an explicitly reviewer-bound detached Workbench server."""
    if not detach:
        raise ValueError("Workbench server must be detached")
    validated_matter_id = _validated_matter_id(matter_id)
    validated_reviewer_id = validate_identifier(reviewer_id, "reviewer_id")
    validated_timeout = validate_idle_timeout(idle_timeout_seconds)
    service = ReviewMatterService.open(workspace_root)
    service.status(matter_id=validated_matter_id)
    if workbench_server_status(service.workspace, validated_matter_id)["running"]:
        raise RuntimeError("protected workbench server is already running")
    token = secrets.token_urlsafe(32)
    command = (
        sys.executable,
        "-m",
        "evidence_review.workbench.local_server",
        "--server-process",
        "--workspace",
        str(service.workspace),
        "--matter-id",
        validated_matter_id,
        "--token",
        token,
        "--reviewer-id",
        validated_reviewer_id,
        "--idle-timeout-seconds",
        str(validated_timeout),
    )
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[2])
        + os.pathsep
        + os.environ.get("PYTHONPATH", ""),
    }
    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
        creationflags=creationflags,
        env=environment,
    )
    try:
        assert process.stdout is not None
        port = int(_readline_with_timeout(process.stdout).strip())
    except (AssertionError, OSError, ValueError):
        process.terminate()
        process.wait(timeout=2)
        raise OSError("protected workbench server did not start") from None
    path = workbench_path(validated_matter_id, token)
    return WorkbenchServerSession(port=port, path=path, url=f"http://127.0.0.1:{port}{path}")


def _server_process_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--matter-id", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument(
        "--idle-timeout-seconds", type=validate_idle_timeout, default=DEFAULT_IDLE_TIMEOUT_SECONDS
    )
    args = parser.parse_args(argv)
    server = create_workbench_server(
        args.workspace,
        matter_id=args.matter_id,
        token=args.token,
        reviewer_id=args.reviewer_id,
        idle_timeout_seconds=args.idle_timeout_seconds,
    )
    state_path = _create_state_path(server.service.workspace, server.matter_id)
    state = {
        "pid": os.getpid(),
        "port": server.server_address[1],
        "matter_id": server.matter_id,
        "token_sha256": hashlib.sha256(server.token.encode("ascii")).hexdigest(),
        "reviewer_id": server.reviewer_id,
        "idle_timeout_seconds": server.idle_timeout_seconds,
    }
    try:
        with state_path.open("x", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
        print(server.server_address[1], flush=True)

        def request_shutdown(_signum: int, _frame: object) -> None:
            if server.begin_shutdown():
                Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, request_shutdown)
        signal.signal(signal.SIGINT, request_shutdown)
        serve_with_idle_timeout(server)
    finally:
        server.server_close()
        try:
            current_path = _existing_state_path(server.service.workspace, server.matter_id)
            current = (
                None
                if current_path is None
                else json.loads(current_path.read_text(encoding="utf-8"))
            )
            if (
                isinstance(current, dict)
                and current_path is not None
                and current.get("pid") == os.getpid()
                and current.get("token_sha256") == state["token_sha256"]
            ):
                current_path.unlink(missing_ok=True)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments.pop(0) != "--server-process":
        raise SystemExit("workbench local_server is a protected process entrypoint")
    return _server_process_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "WorkbenchHTTPServer",
    "WorkbenchServerSession",
    "create_workbench_server",
    "serve_with_idle_timeout",
    "serve_workbench",
    "stop_workbench_server",
    "workbench_server_status",
]
