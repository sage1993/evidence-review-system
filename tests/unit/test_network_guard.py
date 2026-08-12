import socket
from pathlib import Path

import pytest

import ansim_review.network_guard as network_guard
from ansim_review.network_guard import (
    find_forbidden_imports,
    install_network_guard,
    offline_guard_context,
)


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

def test_nonloopback_getaddrinfo_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def fake_getaddrinfo(host: object, *args: object, **kwargs: object) -> object:
        calls.append(host)
        return ()

    monkeypatch.setattr(network_guard, "_ORIGINAL_GETADDRINFO", fake_getaddrinfo)
    install_network_guard()

    with pytest.raises(RuntimeError, match="non-loopback network access is disabled"):
        socket.getaddrinfo("external.example", 443)

    assert calls == []


def test_loopback_resolvers_delegate_to_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    def fake_getaddrinfo(host: object, *args: object, **kwargs: object) -> object:
        calls.append(("getaddrinfo", host))
        return ()

    def fake_gethostbyname(host: str) -> str:
        calls.append(("gethostbyname", host))
        return "127.0.0.1"

    def fake_gethostbyname_ex(host: str) -> tuple[str, list[str], list[str]]:
        calls.append(("gethostbyname_ex", host))
        return host, [], ["127.0.0.1"]

    monkeypatch.setattr(network_guard, "_ORIGINAL_GETADDRINFO", fake_getaddrinfo)
    monkeypatch.setattr(network_guard, "_ORIGINAL_GETHOSTBYNAME", fake_gethostbyname)
    monkeypatch.setattr(
        network_guard,
        "_ORIGINAL_GETHOSTBYNAME_EX",
        fake_gethostbyname_ex,
    )
    install_network_guard()

    socket.getaddrinfo("localhost", 17841)
    socket.getaddrinfo("127.0.0.1", 17841)
    socket.getaddrinfo("::1", 17841)
    socket.gethostbyname("localhost")
    socket.gethostbyname_ex("127.0.0.1")

    assert calls == [
        ("getaddrinfo", "localhost"),
        ("getaddrinfo", "127.0.0.1"),
        ("getaddrinfo", "::1"),
        ("gethostbyname", "localhost"),
        ("gethostbyname_ex", "127.0.0.1"),
    ]


@pytest.mark.skipif(not hasattr(socket.socket, "sendmsg"), reason="sendmsg unavailable")
def test_nonloopback_sendmsg_is_blocked() -> None:
    install_network_guard()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        with pytest.raises(RuntimeError, match="non-loopback network access is disabled"):
            client.sendmsg([b"x"], [], 0, ("8.8.8.8", 53))


def test_connected_socket_send_and_sendall_are_guarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    send_calls: list[bytes] = []
    sendall_calls: list[bytes] = []

    def fake_send(client: socket.socket, data: bytes, *args: object) -> int:
        send_calls.append(data)
        return len(data)

    def fake_sendall(client: socket.socket, data: bytes, *args: object) -> None:
        sendall_calls.append(data)

    monkeypatch.setattr(network_guard, "_ORIGINAL_SEND", fake_send)
    monkeypatch.setattr(network_guard, "_ORIGINAL_SENDALL", fake_sendall)
    monkeypatch.setattr(
        socket.socket,
        "getpeername",
        lambda client: ("8.8.8.8", 53),
    )
    install_network_guard()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        with pytest.raises(RuntimeError, match="non-loopback network access is disabled"):
            client.send(b"x")
        with pytest.raises(RuntimeError, match="non-loopback network access is disabled"):
            client.sendall(b"x")

    assert send_calls == []
    assert sendall_calls == []


def test_offline_guard_context_restores_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def sentinel(*args: object, **kwargs: object) -> tuple[object, ...]:
        return ()
    monkeypatch.setattr(socket, "getaddrinfo", sentinel)

    with offline_guard_context():
        assert socket.getaddrinfo is not sentinel

    assert socket.getaddrinfo is sentinel