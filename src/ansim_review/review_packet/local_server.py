"""Protected loopback server for immutable review artifacts and human decisions."""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import stat
import time
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Literal, cast
from urllib.parse import unquote, urlsplit

from ansim_review.contracts.identifiers import validate_identifier
from ansim_review.review_packet.decision_record import (
    HumanDecisionRecord,
    build_human_decision_envelope,
    load_latest_valid_human_decision,
    validate_human_decision_request,
    write_human_decision,
)
from ansim_review.review_packet.page_image_verifier import read_verified_page_image

_REPARSE_POINT_ATTRIBUTE = 0x400
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_DECISION_FIELDS = frozenset({"reviewer_id", "packet_hash", "decision", "notes"})
_CSP = (
    "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)
_EMBEDDED_PAGE_IMAGE = re.compile(
    r'(<img\b[^>]*\bdata-page-image-source="[^"]+"[^>]*\bsrc=")'
    r'data:image/png;base64,[^"]*(")'
)


@dataclass(frozen=True, slots=True)
class _Route:
    run_id: str
    endpoint: Literal[
        "confirmation",
        "review",
        "packet",
        "packet_hash",
        "decision",
        "decision_status",
        "page_image",
    ]
    token: str | None = None
    revision_id: str | None = None
    page_number: int | None = None
    source_hash: str | None = None


def _is_reparse_point(status: object) -> bool:
    return bool(getattr(status, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE)


def _validated_workspace_root(workspace_root: Path) -> Path:
    try:
        status = workspace_root.lstat()
    except OSError as error:
        raise ValueError("workspace_root must be an existing regular directory") from error
    if (
        stat.S_ISLNK(status.st_mode)
        or not stat.S_ISDIR(status.st_mode)
        or _is_reparse_point(status)
    ):
        raise ValueError("workspace_root must be an existing regular directory")
    return workspace_root.resolve(strict=True)


def _validated_tokens(run_tokens: Mapping[str, str]) -> dict[str, str]:
    validated: dict[str, str] = {}
    for candidate_run_id, candidate_token in run_tokens.items():
        run_id = validate_identifier(candidate_run_id, "run_id")
        if not isinstance(candidate_token, str) or not _TOKEN_PATTERN.fullmatch(candidate_token):
            raise ValueError("run token must be a 32-128 character URL-safe string")
        validated[run_id] = candidate_token
    return validated


def _validated_reviewer_ids(
    run_tokens: Mapping[str, str],
    reviewer_ids: Mapping[str, str] | None,
) -> dict[str, str]:
    if reviewer_ids is None:
        return {}
    known_runs = set(run_tokens)
    validated: dict[str, str] = {}
    for candidate_run_id, candidate_reviewer_id in reviewer_ids.items():
        run_id = validate_identifier(candidate_run_id, "run_id")
        if run_id not in known_runs:
            raise ValueError("reviewer identity references an unknown run")
        validated[run_id] = validate_identifier(candidate_reviewer_id, "reviewer_id")
    return validated


def _route_path(path: str) -> _Route | None:
    parsed = urlsplit(path)
    if parsed.query or parsed.fragment:
        return None
    raw_parts = parsed.path.split("/")
    if not raw_parts or raw_parts[0] != "" or any(not part for part in raw_parts[1:]):
        return None
    parts = [unquote(part) for part in raw_parts[1:]]
    if any(
        part in {".", ".."} or "/" in part or "\\" in part or ":" in part
        for part in parts
    ):
        return None
    if len(parts) < 3 or parts[0] != "runs":
        return None
    try:
        run_id = validate_identifier(parts[1], "run_id")
    except ValueError:
        return None
    token = parts[2]
    if not _TOKEN_PATTERN.fullmatch(token):
        return None
    if len(parts) == 4 and parts[3] in {"confirmation", "review", "packet", "decision"}:
        endpoint = cast(Literal["confirmation", "review", "packet", "decision"], parts[3])
        return _Route(run_id=run_id, token=token, endpoint=endpoint)
    if len(parts) == 5 and parts[3:] in (["packet", "hash"], ["decision", "status"]):
        return _Route(
            run_id=run_id,
            token=token,
            endpoint="packet_hash" if parts[3:] == ["packet", "hash"] else "decision_status",
        )
    if len(parts) == 7 and parts[3] == "page-images":
        revision_id = parts[4]
        if not revision_id or revision_id in {".", ".."}:
            return None
        try:
            page_number = int(parts[5])
        except ValueError:
            return None
        source_hash = parts[6]
        if page_number < 1 or not _SHA256_PATTERN.fullmatch(source_hash):
            return None
        return _Route(
            run_id=run_id,
            token=token,
            endpoint="page_image",
            revision_id=revision_id,
            page_number=page_number,
            source_hash=source_hash,
        )
    return None


def _regular_child(root: Path, *parts: str, final_is_file: bool) -> Path | None:
    candidate = root
    try:
        for index, part in enumerate(parts):
            candidate = candidate / part
            status = candidate.lstat()
            final = index == len(parts) - 1
            if stat.S_ISLNK(status.st_mode) or _is_reparse_point(status):
                return None
            if final:
                if final_is_file != stat.S_ISREG(status.st_mode):
                    return None
            elif not stat.S_ISDIR(status.st_mode):
                return None
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if not isinstance(key, str) or key in result:
            raise ValueError("invalid JSON object")
        result[key] = value
    return result


def _protected_review_html(html_bytes: bytes) -> bytes:
    """Derive a protected presentation without mutating archival review.html."""
    try:
        html = html_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("review HTML must be UTF-8") from error
    marker = '<div class="app-shell"'
    if marker not in html:
        raise ValueError("review HTML app shell missing")
    html = html.replace(
        marker,
        '<div class="app-shell" data-protected-presentation="true"',
        1,
    )
    html = _EMBEDDED_PAGE_IMAGE.sub(r"\1\2", html)
    return html.encode("utf-8")


class _ReviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        workspace_root: Path,
        run_tokens: Mapping[str, str],
        reviewer_ids: Mapping[str, str],
        max_body_bytes: int,
        idle_timeout_seconds: float | None,
    ) -> None:
        self.workspace_root = workspace_root
        self.run_tokens = dict(run_tokens)
        self.reviewer_ids = dict(reviewer_ids)
        self.max_body_bytes = max_body_bytes
        self.idle_timeout_seconds = idle_timeout_seconds
        self._activity_lock = Lock()
        self._activity_event = Event()
        self._last_activity = time.monotonic()
        self._shutdown_started = False
        super().__init__(("127.0.0.1", 0), _ReviewHandler)
        host, port = cast(tuple[str, int], self.server_address)
        self.expected_host = f"{host}:{port}"
        self.origin = f"http://{self.expected_host}"

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
            if self.idle_timeout_seconds is None or self._shutdown_started:
                return False
            return time.monotonic() - self._last_activity >= self.idle_timeout_seconds


class _ReviewHandler(BaseHTTPRequestHandler):
    server_version = "evidence-review-local/2"
    sys_version = ""

    @property
    def state(self) -> _ReviewHTTPServer:
        return cast(_ReviewHTTPServer, self.server)

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _send_bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", _CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, payload: Mapping[str, object]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _reject(self, status: HTTPStatus, code: str) -> None:
        self._send_json(status, {"error": code})

    def _route(self) -> _Route | None:
        route = _route_path(self.path)
        if route is None:
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
        return route

    def _authorized(self, route: _Route, *, require_origin: bool) -> bool:
        host_values = self.headers.get_all("Host") or []
        if len(host_values) != 1 or host_values[0] != self.state.expected_host:
            self._reject(HTTPStatus.FORBIDDEN, "FORBIDDEN")
            return False
        origin_values = self.headers.get_all("Origin") or []
        if len(origin_values) > 1:
            self._reject(HTTPStatus.FORBIDDEN, "FORBIDDEN")
            return False
        if require_origin and (
            len(origin_values) != 1 or origin_values[0] != self.state.origin
        ):
            self._reject(HTTPStatus.FORBIDDEN, "FORBIDDEN")
            return False
        if origin_values and origin_values[0] != self.state.origin:
            self._reject(HTTPStatus.FORBIDDEN, "FORBIDDEN")
            return False
        if route.token is None:
            return True
        expected_token = self.state.run_tokens.get(route.run_id)
        if expected_token is None or not secrets.compare_digest(route.token, expected_token):
            self._reject(HTTPStatus.FORBIDDEN, "FORBIDDEN")
            return False
        return True

    def _run_directory(self, run_id: str) -> Path | None:
        return _regular_child(
            self.state.workspace_root,
            "runs",
            run_id,
            final_is_file=False,
        )

    def _artifact(self, run_id: str, *names: str) -> Path | None:
        return _regular_child(
            self.state.workspace_root,
            "runs",
            run_id,
            *names,
            final_is_file=True,
        )

    def _packet_and_html(self, run_id: str) -> bytes | None:
        packet = self._artifact(run_id, "final-review-packet.json")
        html = self._artifact(run_id, "review.html")
        if packet is None or html is None:
            return None
        try:
            return packet.read_bytes()
        except OSError:
            return None

    def _latest_decision(
        self,
        run_id: str,
        packet_bytes: bytes,
    ) -> HumanDecisionRecord | None:
        run_directory = self._run_directory(run_id)
        if run_directory is None:
            return None
        return load_latest_valid_human_decision(
            run_directory,
            hashlib.sha256(packet_bytes).hexdigest(),
        )

    def _display_status(self, run_id: str, packet_bytes: bytes) -> str:
        try:
            document = json.loads(packet_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            document = {}
        machine_status = "READY_FOR_HUMAN_REVIEW"
        if isinstance(document, dict):
            candidate = document.get("finalizer_status", document.get("status"))
            if isinstance(candidate, str) and candidate:
                machine_status = candidate
        if self._latest_decision(run_id, packet_bytes) is not None:
            return "REVIEW_COMPLETED"
        return machine_status

    def _send_page_image(self, route: _Route) -> None:
        if route.revision_id is None or route.page_number is None or route.source_hash is None:
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return
        try:
            verified = read_verified_page_image(
                self.state.workspace_root / "page-images",
                route.revision_id,
                route.page_number,
                route.source_hash,
            )
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError, ValueError):
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return
        self._send_bytes(HTTPStatus.OK, verified.image_bytes, "image/png")

    def do_GET(self) -> None:  # noqa: N802
        route = self._route()
        if route is None or not self._authorized(route, require_origin=False):
            return
        self.state.mark_activity()
        if route.endpoint == "page_image":
            self._send_page_image(route)
            return
        if route.endpoint == "confirmation":
            artifact = self._artifact(route.run_id, "machine", "drawing-confirmation.json")
            if artifact is None:
                self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
                return
            try:
                self._send_bytes(
                    HTTPStatus.OK,
                    artifact.read_bytes(),
                    "application/json; charset=utf-8",
                )
            except OSError:
                self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return
        if route.endpoint == "decision_status":
            packet_bytes = self._packet_and_html(route.run_id)
            if packet_bytes is None:
                self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
                return
            packet_hash = hashlib.sha256(packet_bytes).hexdigest()
            record = self._latest_decision(route.run_id, packet_bytes)
            decision_record: dict[str, str] | None = None
            if record is not None:
                decision_record = {
                    "reviewer_id": record.reviewer_id,
                    "reviewed_at": record.reviewed_at,
                    "decision": record.decision,
                    "notes": record.notes,
                }
            self._send_json(
                HTTPStatus.OK,
                {
                    "display_status": self._display_status(route.run_id, packet_bytes),
                    "reviewer_id": self.state.reviewer_ids.get(route.run_id),
                    "packet_hash": packet_hash,
                    "decision_record": decision_record,
                },
            )
            return
        if route.endpoint not in {"review", "packet", "packet_hash"}:
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return
        packet_bytes = self._packet_and_html(route.run_id)
        if packet_bytes is None:
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return
        if route.endpoint == "review":
            html = self._artifact(route.run_id, "review.html")
            if html is None:
                self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
                return
            try:
                protected = _protected_review_html(html.read_bytes())
            except (OSError, ValueError):
                self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
                return
            self._send_bytes(HTTPStatus.OK, protected, "text/html; charset=utf-8")
            return
        if route.endpoint == "packet":
            self._send_bytes(HTTPStatus.OK, packet_bytes, "application/json; charset=utf-8")
            return
        self._send_json(
            HTTPStatus.OK,
            {"packet_hash": hashlib.sha256(packet_bytes).hexdigest()},
        )

    def _content_length(self) -> int | None:
        value = self.headers.get("Content-Length")
        if value is None:
            self._reject(HTTPStatus.LENGTH_REQUIRED, "CONTENT_LENGTH_REQUIRED")
            return None
        try:
            length = int(value)
        except ValueError:
            self._reject(HTTPStatus.BAD_REQUEST, "INVALID_CONTENT_LENGTH")
            return None
        if length < 1:
            self._reject(HTTPStatus.BAD_REQUEST, "EMPTY_BODY")
            return None
        if length > self.state.max_body_bytes:
            self._reject(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "BODY_TOO_LARGE")
            return None
        return length

    def _decision_payload(self, body: bytes, run_id: str) -> dict[str, str]:
        try:
            decoded = json.loads(body.decode("utf-8"), object_pairs_hook=_strict_object)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise ValueError("invalid decision JSON") from error
        if not isinstance(decoded, dict) or set(decoded) != _REQUIRED_DECISION_FIELDS:
            raise ValueError("invalid decision JSON")
        try:
            request = validate_human_decision_request(decoded)
        except ValueError as error:
            raise ValueError("invalid decision JSON") from error
        configured = self.state.reviewer_ids.get(run_id)
        if configured is not None and not secrets.compare_digest(
            request["reviewer_id"], configured
        ):
            raise ValueError("invalid decision JSON")
        return request

    def do_POST(self) -> None:  # noqa: N802
        route = self._route()
        if route is None or not self._authorized(route, require_origin=True):
            return
        if route.endpoint != "decision":
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
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
            payload = self._decision_payload(body, route.run_id)
        except ValueError:
            self._reject(HTTPStatus.BAD_REQUEST, "INVALID_DECISION")
            return
        packet_bytes = self._packet_and_html(route.run_id)
        run_directory = self._run_directory(route.run_id)
        if packet_bytes is None or run_directory is None:
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return
        packet_hash = hashlib.sha256(packet_bytes).hexdigest()
        if not secrets.compare_digest(payload["packet_hash"], packet_hash):
            self._reject(HTTPStatus.BAD_REQUEST, "PACKET_HASH_MISMATCH")
            return
        try:
            envelope = build_human_decision_envelope(payload)
            output = write_human_decision(run_directory, **envelope)
        except ValueError:
            self._reject(HTTPStatus.BAD_REQUEST, "INVALID_DECISION")
            return
        except FileExistsError:
            self._reject(HTTPStatus.CONFLICT, "DECISION_ALREADY_EXISTS")
            return
        except OSError:
            self._reject(HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
            return
        self.state.mark_activity()
        self._send_json(
            HTTPStatus.CREATED,
            {
                "filename": output.name,
                "status": "RECORDED",
                "display_status": self._display_status(route.run_id, packet_bytes),
                "reviewed_at": envelope["reviewed_at"],
            },
        )


def create_review_server(
    workspace_root: Path,
    *,
    run_tokens: Mapping[str, str],
    reviewer_ids: Mapping[str, str] | None = None,
    max_body_bytes: int = 65536,
    idle_timeout_seconds: float | None = None,
) -> _ReviewHTTPServer:
    """Create a loopback-only server bound to immutable run artifacts."""
    if (
        isinstance(max_body_bytes, bool)
        or not isinstance(max_body_bytes, int)
        or max_body_bytes < 1
    ):
        raise ValueError("max_body_bytes must be positive")
    if idle_timeout_seconds is not None and (
        isinstance(idle_timeout_seconds, bool)
        or not isinstance(idle_timeout_seconds, (int, float))
        or not math.isfinite(idle_timeout_seconds)
        or idle_timeout_seconds <= 0
    ):
        raise ValueError("idle_timeout_seconds must be finite and positive")
    root = _validated_workspace_root(workspace_root)
    tokens = _validated_tokens(run_tokens)
    reviewers = _validated_reviewer_ids(tokens, reviewer_ids)
    return _ReviewHTTPServer(
        root,
        tokens,
        reviewers,
        max_body_bytes,
        None if idle_timeout_seconds is None else float(idle_timeout_seconds),
    )


def serve_with_idle_timeout(server: ThreadingHTTPServer) -> None:
    """Serve until explicitly stopped or the configured idle deadline expires."""
    typed_server = cast(_ReviewHTTPServer, server)
    monitor_stop = Event()

    def supervise() -> None:
        while typed_server.idle_timeout_seconds is not None:
            with typed_server._activity_lock:
                remaining = max(
                    0.0,
                    typed_server.idle_timeout_seconds
                    - (time.monotonic() - typed_server._last_activity),
                )
            if monitor_stop.wait(min(remaining, 0.5)):
                return
            if typed_server.idle_expired() and typed_server.begin_shutdown():
                typed_server.shutdown()
                return

    monitor = Thread(target=supervise, daemon=True)
    monitor.start()
    try:
        typed_server.serve_forever(poll_interval=0.1)
    finally:
        monitor_stop.set()
        typed_server._activity_event.set()
        monitor.join(timeout=1)


__all__ = ["create_review_server", "serve_with_idle_timeout"]