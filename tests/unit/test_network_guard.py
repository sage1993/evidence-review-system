import socket
from pathlib import Path

import pytest

from ansim_review.network_guard import find_forbidden_imports, install_network_guard


def test_socket_create_connection_is_blocked() -> None:
    install_network_guard()

    with pytest.raises(RuntimeError, match="network access is disabled"):
        socket.create_connection(("example.com", 443))


def test_direct_socket_connect_is_blocked() -> None:
    install_network_guard()
    with socket.socket() as client:
        with pytest.raises(RuntimeError, match="network access is disabled"):
            client.connect(("127.0.0.1", 9))


def test_runtime_has_no_forbidden_client_imports() -> None:
    findings = find_forbidden_imports(Path("src"))

    assert findings == ()
