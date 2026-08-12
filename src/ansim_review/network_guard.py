"""Runtime safeguards for the application offline boundary."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, NoReturn, cast
from unittest.mock import patch

from ansim_review.offline_policy import (
    is_allowed_local_address,
    is_allowed_resolution_host,
)
from ansim_review.offline_scanner import scan_source_tree

_DISABLED_MESSAGE = "non-loopback network access is disabled"
_GUARD_INSTALLED = False
_ORIGINAL_CREATE_CONNECTION: Any = socket.create_connection
_ORIGINAL_CONNECT: Any = socket.socket.connect
_ORIGINAL_CONNECT_EX: Any = socket.socket.connect_ex
_ORIGINAL_SENDTO: Any = socket.socket.sendto
_ORIGINAL_SEND: Any = socket.socket.send
_ORIGINAL_SENDALL: Any = socket.socket.sendall
_ORIGINAL_SENDMSG: Any = getattr(socket.socket, "sendmsg", None)
_ORIGINAL_GETADDRINFO: Any = socket.getaddrinfo
_ORIGINAL_GETHOSTBYNAME: Any = socket.gethostbyname
_ORIGINAL_GETHOSTBYNAME_EX: Any = socket.gethostbyname_ex
_ORIGINAL_GETNAMEINFO: Any = socket.getnameinfo


def _raise_blocked(address: object) -> NoReturn:
    raise RuntimeError(f"{_DISABLED_MESSAGE}: {address}")


def _guarded_create_connection(
    address: object,
    *args: object,
    **kwargs: object,
) -> Any:
    if not is_allowed_local_address(address):
        _raise_blocked(address)
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


def _guarded_socket_connect(self: socket.socket, address: object) -> Any:
    if not is_allowed_local_address(address):
        _raise_blocked(address)
    return _ORIGINAL_CONNECT(self, address)


def _guarded_socket_connect_ex(self: socket.socket, address: object) -> Any:
    if not is_allowed_local_address(address):
        _raise_blocked(address)
    return _ORIGINAL_CONNECT_EX(self, address)


def _sendto_address(args: tuple[object, ...]) -> object:
    if len(args) not in (1, 2):
        raise TypeError("sendto requires an address")
    return args[-1]


def _guarded_socket_sendto(
    self: socket.socket,
    data: bytes | bytearray | memoryview,
    *args: object,
) -> int:
    address = _sendto_address(args)
    if not is_allowed_local_address(address):
        _raise_blocked(address)
    return cast(int, _ORIGINAL_SENDTO(self, data, *args))


def _connected_peer(client: socket.socket) -> object:
    try:
        return client.getpeername()
    except OSError as error:
        raise RuntimeError(_DISABLED_MESSAGE) from error


def _guarded_socket_send(
    self: socket.socket,
    data: bytes | bytearray | memoryview,
    *args: object,
) -> int:
    peer = _connected_peer(self)
    if not is_allowed_local_address(peer):
        _raise_blocked(peer)
    return cast(int, _ORIGINAL_SEND(self, data, *args))


def _guarded_socket_sendall(
    self: socket.socket,
    data: bytes | bytearray | memoryview,
    *args: object,
) -> None:
    peer = _connected_peer(self)
    if not is_allowed_local_address(peer):
        _raise_blocked(peer)
    _ORIGINAL_SENDALL(self, data, *args)


def _guarded_socket_sendmsg(
    self: socket.socket,
    buffers: object,
    *args: object,
) -> int:
    address = args[2] if len(args) >= 3 else _connected_peer(self)
    if address is None:
        address = _connected_peer(self)
    if not is_allowed_local_address(address):
        _raise_blocked(address)
    return cast(int, _ORIGINAL_SENDMSG(self, buffers, *args))


def _guarded_getaddrinfo(host: object, *args: object, **kwargs: object) -> Any:
    if not is_allowed_resolution_host(host):
        _raise_blocked(host)
    return _ORIGINAL_GETADDRINFO(host, *args, **kwargs)


def _guarded_gethostbyname(host: str) -> Any:
    if not is_allowed_resolution_host(host):
        _raise_blocked(host)
    return _ORIGINAL_GETHOSTBYNAME(host)


def _guarded_gethostbyname_ex(host: str) -> Any:
    if not is_allowed_resolution_host(host):
        _raise_blocked(host)
    return _ORIGINAL_GETHOSTBYNAME_EX(host)


def _guarded_getnameinfo(sockaddr: object, flags: int) -> Any:
    if not is_allowed_local_address(sockaddr):
        _raise_blocked(sockaddr)
    return _ORIGINAL_GETNAMEINFO(sockaddr, flags)


def _patch_targets() -> tuple[tuple[Any, str, Any], ...]:
    targets: list[tuple[Any, str, Any]] = [
        (socket, "create_connection", _guarded_create_connection),
        (socket, "getaddrinfo", _guarded_getaddrinfo),
        (socket, "gethostbyname", _guarded_gethostbyname),
        (socket, "gethostbyname_ex", _guarded_gethostbyname_ex),
        (socket, "getnameinfo", _guarded_getnameinfo),
        (socket.socket, "connect", _guarded_socket_connect),
        (socket.socket, "connect_ex", _guarded_socket_connect_ex),
        (socket.socket, "sendto", _guarded_socket_sendto),
        (socket.socket, "send", _guarded_socket_send),
        (socket.socket, "sendall", _guarded_socket_sendall),
    ]
    if _ORIGINAL_SENDMSG is not None:
        targets.append((socket.socket, "sendmsg", _guarded_socket_sendmsg))
    return tuple(targets)


def install_network_guard() -> None:
    """Install an idempotent loopback-only outbound socket guard."""
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return
    for owner, name, replacement in _patch_targets():
        setattr(owner, name, replacement)  # noqa: B010
    _GUARD_INSTALLED = True


@contextmanager
def offline_guard_context() -> Iterator[None]:
    """Temporarily apply the same loopback-only guard used by the runtime."""
    with ExitStack() as stack:
        for owner, name, replacement in _patch_targets():
            stack.enter_context(patch.object(owner, name, replacement))
        yield


def find_forbidden_imports(root: Path) -> tuple[str, ...]:
    """Return compatibility strings derived from the shared source scanner."""
    return tuple(
        f"{finding.path}:{finding.line}:{finding.kind}:{finding.symbol}"
        for finding in scan_source_tree(root)
    )