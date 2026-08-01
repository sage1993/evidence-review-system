"""Runtime and static safeguards for the API-free execution boundary."""

from __future__ import annotations

import ast
import socket
from collections.abc import Iterable
from pathlib import Path
from typing import NoReturn

_DISABLED_MESSAGE = "network access is disabled"
_GUARD_INSTALLED = False
_FORBIDDEN_TOP_LEVEL_MODULES = frozenset({"requests", "httpx", "openai"})


def _blocked_create_connection(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError(_DISABLED_MESSAGE)


def _blocked_socket_connect(self: socket.socket, address: object) -> NoReturn:
    raise RuntimeError(_DISABLED_MESSAGE)


def _blocked_socket_connect_ex(self: socket.socket, address: object) -> NoReturn:
    raise RuntimeError(_DISABLED_MESSAGE)


def install_network_guard() -> None:
    """Disable outbound socket connection entry points for this process."""
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return
    setattr(socket, "create_connection", _blocked_create_connection)  # noqa: B010
    setattr(socket.socket, "connect", _blocked_socket_connect)  # noqa: B010
    setattr(socket.socket, "connect_ex", _blocked_socket_connect_ex)  # noqa: B010
    _GUARD_INSTALLED = True


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
    top_level = module.split(".", maxsplit=1)[0]
    return top_level in _FORBIDDEN_TOP_LEVEL_MODULES or module == "urllib.request"


def find_forbidden_imports(root: Path) -> tuple[str, ...]:
    """Return deterministic findings for forbidden network-client imports."""
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
