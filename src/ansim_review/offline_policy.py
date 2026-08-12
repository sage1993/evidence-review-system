"""Shared application-level offline execution policy."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path

POLICY_VERSION = 1
APPLICATION_OFFLINE_GUARD = "APPLICATION_OFFLINE_GUARD"
OS_ISOLATED = "OS_ISOLATED"


@dataclass(frozen=True, slots=True)
class OfflinePolicy:
    """Immutable capabilities denied by the packaged Python runtime."""

    version: int
    assurance_level: str
    forbidden_import_roots: frozenset[str]
    forbidden_import_names: frozenset[str]
    forbidden_process_calls: frozenset[str]
    forbidden_socket_capabilities: frozenset[str]


def default_offline_policy() -> OfflinePolicy:
    """Return the canonical application-level offline policy."""
    return OfflinePolicy(
        version=POLICY_VERSION,
        assurance_level=APPLICATION_OFFLINE_GUARD,
        forbidden_import_roots=frozenset(
            {
                "aiohttp",
                "anthropic",
                "httpx",
                "openai",
                "requests",
                "subprocess",
            }
        ),
        forbidden_import_names=frozenset({"urllib.request"}),
        forbidden_socket_capabilities=frozenset({
            "dns_resolution", "connect", "connect_ex", "send", "sendall",
            "sendmsg", "sendto",
        }),
        forbidden_process_calls=frozenset(
            {
                "asyncio.create_subprocess_exec",
                "asyncio.create_subprocess_shell",
                "os.popen",
                "os.system",
                "subprocess.Popen",
                "subprocess.call",
                "subprocess.check_call",
                "subprocess.check_output",
                "subprocess.run",
            }
        ),
    )


def _is_loopback_host(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if value.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def is_allowed_resolution_host(host: object) -> bool:
    """Allow DNS APIs to resolve only loopback names or literal loopback IPs."""
    return _is_loopback_host(host)


def _is_unix_socket_address(value: object) -> bool:
    if isinstance(value, os.PathLike):
        return True
    if not isinstance(value, str) or not value:
        return False
    if value.startswith("\0"):
        return True
    return "/" in value or "\\" in value or Path(value).is_absolute()


def is_allowed_local_address(address: object) -> bool:
    """Classify local transport intent without DNS resolution."""
    if isinstance(address, tuple):
        if len(address) not in (2, 4):
            return False
        return _is_loopback_host(address[0])
    return _is_unix_socket_address(address)
