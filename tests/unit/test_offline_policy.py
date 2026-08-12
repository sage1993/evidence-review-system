from pathlib import Path

import pytest

from ansim_review.offline_policy import (
    POLICY_VERSION,
    default_offline_policy,
    is_allowed_local_address,
    is_allowed_resolution_host,
)


def test_policy_has_stable_version_and_required_blocks() -> None:
    policy = default_offline_policy()

    assert POLICY_VERSION == 1
    assert policy.version == POLICY_VERSION
    assert {
        "requests",
        "httpx",
        "aiohttp",
        "openai",
        "anthropic",
        "subprocess",
    } <= policy.forbidden_import_roots
    assert "urllib.request" in policy.forbidden_import_names
    assert {
        "asyncio.create_subprocess_exec",
        "asyncio.create_subprocess_shell",
        "os.system",
        "os.popen",
    } <= policy.forbidden_process_calls


@pytest.mark.parametrize(
    "address",
    [
        ("127.0.0.1", 17841),
        ("::1", 17841, 0, 0),
        ("localhost", 17841),
        Path("/tmp/evidence-review.sock"),
        "/tmp/evidence-review.sock",
        "\0evidence-review",
    ],
)
def test_local_addresses_are_allowed(address: object) -> None:
    assert is_allowed_local_address(address) is True


@pytest.mark.parametrize(
    "address",
    [
        ("8.8.8.8", 53),
        ("192.168.0.10", 80),
        ("0.0.0.0", 80),
        ("::", 80, 0, 0),
        ("2001:4860:4860::8888", 53, 0, 0),
        ("example.com", 443),
        "example.com",
        object(),
    ],
)
def test_nonlocal_addresses_are_rejected(address: object) -> None:
    assert is_allowed_local_address(address) is False

@pytest.mark.parametrize(
    "host",
    ["localhost", "LOCALHOST", "127.0.0.1", "::1"],
)
def test_resolution_hosts_allow_only_loopback_names_and_addresses(host: str) -> None:
    assert is_allowed_resolution_host(host) is True


@pytest.mark.parametrize(
    "host",
    ["example.com", "8.8.8.8", "2001:4860:4860::8888", None],
)
def test_resolution_hosts_reject_nonloopback_values(host: object) -> None:
    assert is_allowed_resolution_host(host) is False