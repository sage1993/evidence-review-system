"""Runtime and static safeguards for the application offline boundary."""

from __future__ import annotations

import ast
import socket
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NoReturn
from unittest.mock import patch

from ansim_review.offline_policy import (
    default_offline_policy,
    is_allowed_local_address,
)

_DISABLED_MESSAGE = "non-loopback network access is disabled"
_GUARD_INSTALLED = False
_ORIGINAL_CREATE_CONNECTION = socket.create_connection
_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_SENDTO = socket.socket.sendto


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
    return _ORIGINAL_SENDTO(self, data, *args)


def install_network_guard() -> None:
    """Install an idempotent loopback-only outbound socket guard."""
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return
    setattr(socket, "create_connection", _guarded_create_connection)  # noqa: B010
    setattr(socket.socket, "connect", _guarded_socket_connect)  # noqa: B010
    setattr(socket.socket, "connect_ex", _guarded_socket_connect_ex)  # noqa: B010
    setattr(socket.socket, "sendto", _guarded_socket_sendto)  # noqa: B010
    _GUARD_INSTALLED = True


@contextmanager
def offline_guard_context() -> Iterator[None]:
    """Temporarily apply the same loopback-only guard used by the runtime."""
    with (
        patch.object(socket, "create_connection", _guarded_create_connection),
        patch.object(socket.socket, "connect", _guarded_socket_connect),
        patch.object(socket.socket, "connect_ex", _guarded_socket_connect_ex),
        patch.object(socket.socket, "sendto", _guarded_socket_sendto),
    ):
        yield


def _imported_modules(node: ast.Import | ast.ImportFrom) -> Iterable[str]:
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name
        return

    module = node.module or ""
    if module == "urllib":
        for alias in node.names:
            if alias.name == "request":
                yield "urllib.request"
    if module:
        yield module


def _is_forbidden_import(module: str) -> bool:
    policy = default_offline_policy()
    top_level = module.split(".", maxsplit=1)[0]
    return (
        top_level in policy.forbidden_import_roots
        or module in policy.forbidden_import_names
    )


def find_forbidden_imports(root: Path) -> tuple[str, ...]:
    """Return deterministic findings for currently forbidden imports."""
    findings: list[str] = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as error:
            findings.append(f"{path.as_posix()}:0:SCAN_ERROR:{error}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for module in _imported_modules(node):
                if _is_forbidden_import(module):
                    findings.append(f"{path.as_posix()}:{node.lineno}:{module}")
    return tuple(sorted(findings))
