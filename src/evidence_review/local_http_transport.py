"""Shared fail-closed transport primitives for protected loopback HTTP servers."""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable, Mapping
from email.message import Message
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from io import BufferedReader
from typing import cast

OVERSIZED_BODY_DRAIN_TIMEOUT_SECONDS = 0.5
OVERSIZED_BODY_READ_CHUNK_BYTES = 8192
REJECTED_BODY_DRAIN_MAX_BYTES = 4 * 1024 * 1024


class ContentLengthError(ValueError):
    """A rejected request body length with a stable transport error code."""

    def __init__(self, code: str, *, length: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.length = length


def send_protected_response(
    handler: BaseHTTPRequestHandler,
    status: HTTPStatus | int,
    body: bytes,
    content_type: str,
    *,
    content_security_policy: str,
    allow: str | None = None,
) -> None:
    """Send one no-store loopback response with the required security headers."""
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Security-Policy", content_security_policy)
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    if allow is not None:
        handler.send_header("Allow", allow)
    handler.end_headers()
    handler.wfile.write(body)


def drain_rejected_body(
    handler: BaseHTTPRequestHandler,
    *,
    max_bytes: int = REJECTED_BODY_DRAIN_MAX_BYTES,
) -> None:
    """Drain a bounded rejected request body before sending its response.

    Windows clients can observe a connection reset when a server rejects a
    POST while unread request bytes remain in the socket.  Drain only a
    bounded amount and for a bounded time so an unauthorized client cannot
    hold the handler indefinitely; an incomplete drain forces connection
    closure instead of allowing leftover bytes to be parsed as another
    request.
    """
    values = handler.headers.get_all("Content-Length") or []
    if len(values) != 1:
        return
    try:
        length = int(values[0])
    except ValueError:
        return
    if length <= 0:
        return
    remaining = min(length, max_bytes)
    deadline = time.monotonic() + OVERSIZED_BODY_DRAIN_TIMEOUT_SECONDS
    try:
        reader = cast(BufferedReader, handler.rfile)
        while remaining:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                break
            handler.connection.settimeout(timeout)
            chunk = reader.read1(min(OVERSIZED_BODY_READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
    except OSError:
        remaining = 1
    finally:
        if remaining or length > max_bytes:
            handler.close_connection = True


def loopback_request_is_authorized(
    headers: Message[str, str],
    *,
    expected_host: str,
    expected_origin: str,
    require_origin: bool,
    presented_token: str | None = None,
    expected_token: str | None = None,
) -> bool:
    """Validate Host/Origin cardinality and, when supplied, a route token."""
    host_values = headers.get_all("Host") or []
    if len(host_values) != 1 or host_values[0] != expected_host:
        return False
    origin_values = headers.get_all("Origin") or []
    if len(origin_values) > 1:
        return False
    if require_origin and (len(origin_values) != 1 or origin_values[0] != expected_origin):
        return False
    if origin_values and origin_values[0] != expected_origin:
        return False
    if presented_token is None and expected_token is None:
        return True
    if not isinstance(presented_token, str) or not isinstance(expected_token, str):
        return False
    return secrets.compare_digest(presented_token, expected_token)


def token_matches(presented_token: str, expected_token: str) -> bool:
    """Compare a parsed route token without exposing an early mismatch."""
    return secrets.compare_digest(presented_token, expected_token)


def tokenized_route_matches(
    path: str,
    *,
    route_name: str,
    expected_token: str,
    suffix: tuple[str, ...] = (),
) -> bool:
    """Match a tokenized route while comparing its token in constant time."""
    parts = path.split("/")
    return (
        len(parts) == 3 + len(suffix)
        and parts[0] == ""
        and parts[1] == route_name
        and tuple(parts[3:]) == suffix
        and token_matches(parts[2], expected_token)
    )


def allowed_methods_for_tokenized_route(
    path: str,
    *,
    expected_token: str,
    routes: Mapping[tuple[str, tuple[str, ...]], str],
) -> str | None:
    """Resolve an Allow value for one exact tokenized route, if any."""
    for (route_name, suffix), allowed_methods in routes.items():
        if tokenized_route_matches(
            path,
            route_name=route_name,
            expected_token=expected_token,
            suffix=suffix,
        ):
            return allowed_methods
    return None


def validate_content_length(
    headers: Message[str, str], max_body_bytes: int, *, reject_transfer_encoding: bool = False
) -> int:
    """Return the one valid non-empty body length or raise a typed rejection."""
    if reject_transfer_encoding and headers.get("Transfer-Encoding") is not None:
        raise ContentLengthError("CONTENT_LENGTH_REQUIRED")
    values = headers.get_all("Content-Length") or []
    if len(values) != 1:
        code = "CONTENT_LENGTH_REQUIRED" if not values else "INVALID_CONTENT_LENGTH"
        raise ContentLengthError(code)
    try:
        length = int(values[0])
    except ValueError as error:
        raise ContentLengthError("INVALID_CONTENT_LENGTH") from error
    if length < 1:
        raise ContentLengthError("EMPTY_BODY")
    if length > max_body_bytes:
        raise ContentLengthError("BODY_TOO_LARGE", length=length)
    return length


def reject_oversized_body(
    handler: BaseHTTPRequestHandler,
    length: int,
    reject: Callable[[HTTPStatus, str], None],
) -> None:
    """Flush 413 first, then drain only until the one total deadline and close."""
    handler.close_connection = True
    reject(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "BODY_TOO_LARGE")
    try:
        handler.wfile.flush()
        deadline = time.monotonic() + OVERSIZED_BODY_DRAIN_TIMEOUT_SECONDS
        reader = cast(BufferedReader, handler.rfile)
        remaining = length
        while remaining:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                break
            handler.connection.settimeout(timeout)
            chunk = reader.read1(min(OVERSIZED_BODY_READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
    except OSError:
        return
