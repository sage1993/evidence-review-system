from __future__ import annotations

import socket
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

import pytest

from ansim_review.review_packet.browser_launcher import close_open_review_servers
from ansim_review.review_run import open_review_run

RUN_ID = "RUN-0123456789ABCDEF0123"


@pytest.fixture(autouse=True)
def _close_review_servers() -> None:
    yield
    close_open_review_servers()


def _artifacts(root: Path) -> tuple[Path, bytes, bytes]:
    run_directory = root / "runs" / RUN_ID
    run_directory.mkdir(parents=True)
    packet = b'{"human_decision":null,"run_id":"RUN-0123456789ABCDEF0123"}'
    html = b"<html><body>protected review</body></html>"
    (run_directory / "final-review-packet.json").write_bytes(packet)
    (run_directory / "review.html").write_bytes(html)
    return run_directory, packet, html


def test_open_review_run_opens_a_tokenized_loopback_route_and_preserves_packet_bytes(
    tmp_path: Path,
) -> None:
    _, packet, html = _artifacts(tmp_path)
    opened: list[str] = []

    url = open_review_run(tmp_path, RUN_ID, browser=lambda value: opened.append(value) or True)

    assert opened == [url]
    parsed = urlsplit(url)
    assert parsed.scheme == "http"
    assert parsed.hostname == "127.0.0.1"
    assert parsed.path.startswith(f"/runs/{RUN_ID}/")
    assert parsed.path.endswith("/review")
    assert not url.startswith("file:")
    with urlopen(url, timeout=5) as response:
        assert response.read() == html
    with urlopen(url.removesuffix("/review") + "/packet", timeout=5) as response:
        assert response.read() == packet
    assert (tmp_path / "runs" / RUN_ID / "final-review-packet.json").read_bytes() == packet


@pytest.mark.parametrize("missing", ("review.html", "final-review-packet.json"))
def test_open_review_run_fails_closed_without_final_artifacts(
    tmp_path: Path,
    missing: str,
) -> None:
    run_directory, _, _ = _artifacts(tmp_path)
    (run_directory / missing).unlink()
    opened: list[str] = []

    with pytest.raises(FileNotFoundError):
        open_review_run(tmp_path, RUN_ID, browser=lambda value: opened.append(value) or True)

    assert opened == []


def test_open_review_run_closes_its_server_when_the_browser_rejects_the_url(
    tmp_path: Path,
) -> None:
    _artifacts(tmp_path)
    opened: list[str] = []

    with pytest.raises(OSError, match="browser"):
        open_review_run(tmp_path, RUN_ID, browser=lambda value: opened.append(value) or False)

    assert len(opened) == 1
    parsed = urlsplit(opened[0])
    assert parsed.hostname == "127.0.0.1"
    assert parsed.port is not None
    with pytest.raises(OSError):
        socket.create_connection((parsed.hostname, parsed.port), timeout=1)
