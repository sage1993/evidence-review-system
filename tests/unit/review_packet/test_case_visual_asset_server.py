from types import SimpleNamespace

import pytest

from evidence_review.review_packet import local_server
from evidence_review.review_packet.case_visual_asset_server import (
    CaseVisualReviewHandler,
    _case_asset_route,
    configure_case_visual_server,
)

RUN_ID = "RUN-0123456789ABCDEF0123"
TOKEN = "a" * 43
PAGE_HASH = "b" * 64
TILE_HASH = "c" * 64


def test_case_page_route_parses_normalized_protected_identity() -> None:
    route = _case_asset_route(
        f"/runs/{RUN_ID}/{TOKEN}/case-pages/ATT-CASE/12/{PAGE_HASH}"
    )

    assert route is not None
    assert route.run_id == RUN_ID
    assert route.token == TOKEN
    assert route.kind == "page"
    assert route.attachment_id == "ATT-CASE"
    assert route.page_number == 12
    assert route.image_sha256 == PAGE_HASH
    assert route.tile_x is None
    assert route.tile_y is None


def test_case_tile_route_parses_normalized_protected_identity() -> None:
    route = _case_asset_route(
        f"/runs/{RUN_ID}/{TOKEN}/case-tiles/ATT-CASE/12/2048/0/{TILE_HASH}"
    )

    assert route is not None
    assert route.kind == "tile"
    assert route.attachment_id == "ATT-CASE"
    assert route.page_number == 12
    assert route.tile_x == 2048
    assert route.tile_y == 0
    assert route.image_sha256 == TILE_HASH


@pytest.mark.parametrize(
    "path",
    [
        f"/runs/{RUN_ID}/{TOKEN}/case-pages/ATT-CASE/12/{PAGE_HASH}?probe=1",
        f"/runs/{RUN_ID}/{TOKEN}/case-pages/%2E%2E/12/{PAGE_HASH}",
        f"/runs/{RUN_ID}/{TOKEN}/case-pages/ATT%2FCASE/12/{PAGE_HASH}",
        f"/runs/{RUN_ID}/{TOKEN}/case-pages/ATT-CASE/0/{PAGE_HASH}",
        f"/runs/{RUN_ID}/{TOKEN}/case-pages/ATT-CASE/12/not-a-hash",
        f"/runs/{RUN_ID}/{TOKEN}/case-tiles/ATT-CASE/12/-1/0/{TILE_HASH}",
        f"/runs/{RUN_ID}/short/case-pages/ATT-CASE/12/{PAGE_HASH}",
    ],
)
def test_case_asset_route_rejects_noncanonical_or_invalid_paths(path: str) -> None:
    assert _case_asset_route(path) is None


def test_configure_case_visual_server_only_installs_asset_handler() -> None:
    protected_renderer = local_server._protected_review_html
    server = SimpleNamespace(RequestHandlerClass=None)

    configure_case_visual_server(server)  # type: ignore[arg-type]

    assert server.RequestHandlerClass is CaseVisualReviewHandler
    assert local_server._protected_review_html is protected_renderer
