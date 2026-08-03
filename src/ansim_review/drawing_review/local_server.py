"""Loopback-only HTTP server for the drawing annotation workspace."""

from __future__ import annotations

import json
import re
import secrets
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import cast
from urllib.parse import urlsplit

from ansim_review.drawing_review.actions import decode_annotation_action
from ansim_review.drawing_review.service import (
    AnnotationActionResult,
    record_annotation_action,
)
from ansim_review.drawing_review.view_model import DrawingPage
from ansim_review.parsing.drawing_case import CaseManifestEntry

_REPARSE_POINT_ATTRIBUTE = 0x400
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_DEFAULT_MAX_BODY_BYTES = 64 * 1024
_CSP = (
    "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)


def _entry_document(entry: CaseManifestEntry | None) -> dict[str, object] | None:
    if entry is None:
        return None
    return {
        "artifact_id": entry.artifact_id,
        "relative_path": entry.relative_path,
        "sha256": entry.sha256,
    }


def _result_document(result: AnnotationActionResult) -> dict[str, object]:
    return {
        "candidate": _entry_document(result.candidate_entry),
        "confirmation": _entry_document(result.confirmation_entry),
    }


def _validate_case_dir(case_dir: Path) -> Path:
    try:
        status = case_dir.lstat()
    except FileNotFoundError:
        raise ValueError("case_dir must be an existing directory") from None
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise ValueError("case_dir must be a regular non-link directory")
    if getattr(status, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE:
        raise ValueError("case_dir cannot be a Windows reparse point")
    return case_dir.resolve()


def _validated_token(token: str | None) -> str:
    value = secrets.token_urlsafe(32) if token is None else token
    if not _TOKEN_PATTERN.fullmatch(value):
        raise ValueError("token must be a 32-128 character URL-safe string")
    return value


class _AnnotationHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        *,
        html: str,
        case_dir: Path,
        page: DrawingPage,
        candidate_entries: Mapping[str, CaseManifestEntry],
        token: str,
        port: int,
        max_body_bytes: int,
    ) -> None:
        self.html_bytes = html.encode("utf-8")
        self.case_dir = case_dir
        self.page = page
        self.candidate_entries = dict(candidate_entries)
        self.token = token
        self.max_body_bytes = max_body_bytes
        self.results: list[AnnotationActionResult] = []
        self.action_lock = Lock()
        super().__init__(("127.0.0.1", port), _AnnotationHandler)
        host, assigned_port = cast(tuple[str, int], self.server_address)
        self.expected_host = f"{host}:{assigned_port}"
        self.origin = f"http://{self.expected_host}"


class _AnnotationHandler(BaseHTTPRequestHandler):
    server_version = "EvidenceReviewAnnotation/1"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:
        return None

    @property
    def state(self) -> _AnnotationHTTPServer:
        return cast(_AnnotationHTTPServer, self.server)

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", _CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: Mapping[str, object]) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _reject(self, status: int, code: str) -> None:
        self._send_json(status, {"error": code})

    def _matches_route(self, suffix: str) -> bool:
        parsed = urlsplit(self.path)
        expected = f"/annotation/{self.state.token}{suffix}"
        if parsed.query or parsed.fragment:
            self._reject(404, "NOT_FOUND")
            return False
        if parsed.path == expected:
            return True
        if parsed.path.startswith("/annotation/"):
            self._reject(403, "FORBIDDEN")
            return False
        self._reject(404, "NOT_FOUND")
        return False

    def _authorized(self, *, require_origin: bool) -> bool:
        if self.headers.get("Host") != self.state.expected_host:
            self._reject(403, "FORBIDDEN")
            return False
        origin = self.headers.get("Origin")
        if require_origin and origin != self.state.origin:
            self._reject(403, "FORBIDDEN")
            return False
        if origin is not None and origin != self.state.origin:
            self._reject(403, "FORBIDDEN")
            return False
        return True

    def do_GET(self) -> None:
        if not self._matches_route(""):
            return
        if not self._authorized(require_origin=False):
            return
        self._send_bytes(200, self.state.html_bytes, "text/html; charset=utf-8")

    def _content_length(self) -> int | None:
        value = self.headers.get("Content-Length")
        if value is None:
            self._reject(411, "CONTENT_LENGTH_REQUIRED")
            return None
        try:
            length = int(value)
        except ValueError:
            self._reject(400, "INVALID_CONTENT_LENGTH")
            return None
        if length < 1:
            self._reject(400, "EMPTY_BODY")
            return None
        if length > self.state.max_body_bytes:
            self._reject(413, "BODY_TOO_LARGE")
            return None
        return length

    def do_POST(self) -> None:
        if not self._matches_route("/actions"):
            return
        if not self._authorized(require_origin=True):
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
        if content_type != "application/json":
            self._reject(415, "UNSUPPORTED_MEDIA_TYPE")
            return
        length = self._content_length()
        if length is None:
            return
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
            action = decode_annotation_action(payload)
            with self.state.action_lock:
                result = record_annotation_action(
                    self.state.case_dir,
                    self.state.page,
                    self.state.candidate_entries,
                    action,
                )
                if result.candidate_entry is not None:
                    self.state.candidate_entries[
                        result.candidate_entry.artifact_id
                    ] = result.candidate_entry
                self.state.results.append(result)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            self._reject(400, "INVALID_ACTION")
            return
        except FileNotFoundError:
            self._reject(404, "NOT_FOUND")
            return
        except FileExistsError:
            self._reject(409, "ALREADY_EXISTS")
            return
        except OSError:
            self._reject(500, "INTERNAL_ERROR")
            return
        self._send_json(201, _result_document(result))


@dataclass(slots=True)
class AnnotationServer:
    """Running annotation server with deterministic shutdown semantics."""

    _server: _AnnotationHTTPServer
    _thread: Thread

    @property
    def host(self) -> str:
        return "127.0.0.1"

    @property
    def port(self) -> int:
        return cast(tuple[str, int], self._server.server_address)[1]

    @property
    def origin(self) -> str:
        return self._server.origin

    @property
    def url(self) -> str:
        return f"{self.origin}/annotation/{self._server.token}"

    @property
    def results(self) -> tuple[AnnotationActionResult, ...]:
        with self._server.action_lock:
            return tuple(self._server.results)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self) -> AnnotationServer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self.close()


def serve_annotation_workspace(
    *,
    html: str,
    case_dir: Path,
    page: DrawingPage,
    candidate_entries: Mapping[str, CaseManifestEntry],
    token: str | None = None,
    port: int = 0,
    max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
) -> AnnotationServer:
    """Start one loopback-only annotation workspace server."""
    if not isinstance(html, str) or not html:
        raise ValueError("html must be a non-empty string")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    if (
        isinstance(max_body_bytes, bool)
        or not isinstance(max_body_bytes, int)
        or max_body_bytes < 1
    ):
        raise ValueError("max_body_bytes must be positive")
    server = _AnnotationHTTPServer(
        html=html,
        case_dir=_validate_case_dir(case_dir),
        page=page,
        candidate_entries=candidate_entries,
        token=_validated_token(token),
        port=port,
        max_body_bytes=max_body_bytes,
    )
    thread = Thread(
        target=server.serve_forever,
        name="drawing-annotation-server",
        daemon=True,
    )
    thread.start()
    return AnnotationServer(server, thread)
