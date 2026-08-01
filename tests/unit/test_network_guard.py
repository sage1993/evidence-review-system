import socket
from pathlib import Path

import pytest

import ansim_review.network_guard as network_guard
from ansim_review.network_guard import find_forbidden_imports, install_network_guard


def test_nonloopback_create_connection_is_blocked() -> None:
    install_network_guard()

    with pytest.raises(RuntimeError, match="non-loopback network access is disabled"):
        socket.create_connection(("8.8.8.8", 53))


def test_nonloopback_direct_connect_is_blocked() -> None:
    install_network_guard()
    with socket.socket() as client:
        with pytest.raises(RuntimeError, match="non-loopback network access is disabled"):
            client.connect(("192.168.0.10", 80))


def test_loopback_tcp_delegates_to_original(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    def fake_connect(client: socket.socket, address: object) -> None:
        calls.append(address)

    monkeypatch.setattr(network_guard, "_ORIGINAL_CONNECT", fake_connect)
    install_network_guard()
    with socket.socket() as client:
        client.connect(("127.0.0.1", 17841))
        client.connect(("::1", 17841, 0, 0))

    assert calls == [("127.0.0.1", 17841), ("::1", 17841, 0, 0)]


def test_loopback_create_connection_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    calls: list[object] = []

    def fake_create_connection(address: object, *args: object, **kwargs: object) -> object:
        calls.append(address)
        return sentinel

    monkeypatch.setattr(
        network_guard,
        "_ORIGINAL_CREATE_CONNECTION",
        fake_create_connection,
    )
    install_network_guard()

    assert socket.create_connection(("localhost", 17841)) is sentinel
    assert calls == [("localhost", 17841)]


def test_nonloopback_udp_sendto_is_blocked() -> None:
    install_network_guard()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        with pytest.raises(RuntimeError, match="non-loopback network access is disabled"):
            client.sendto(b"payload", ("8.8.8.8", 53))


def test_loopback_udp_sendto_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[bytes, tuple[object, ...]]] = []

    def fake_sendto(
        client: socket.socket,
        data: bytes,
        *args: object,
    ) -> int:
        calls.append((data, args))
        return len(data)

    monkeypatch.setattr(network_guard, "_ORIGINAL_SENDTO", fake_sendto)
    install_network_guard()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        assert client.sendto(b"payload", ("127.0.0.1", 17841)) == 7

    assert calls == [(b"payload", (("127.0.0.1", 17841),))]


def test_guard_installation_is_idempotent() -> None:
    install_network_guard()
    create_connection = socket.create_connection
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    sendto = socket.socket.sendto

    install_network_guard()

    assert socket.create_connection is create_connection
    assert socket.socket.connect is connect
    assert socket.socket.connect_ex is connect_ex
    assert socket.socket.sendto is sendto


def test_runtime_has_no_forbidden_capabilities() -> None:
    findings = find_forbidden_imports(Path("src"))

    assert findings == ()
