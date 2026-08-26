import json

from evidence_review.review_packet.case_visual_asset_server import (
    protect_case_visual_sources,
)


def _review_html(page: dict[str, object], raster_markup: str) -> bytes:
    model = {"case_visual_review": {"pages": [page]}}
    return (
        '<script id="review-model" type="application/json">'
        + json.dumps(model, sort_keys=True, separators=(",", ":"))
        + "</script>"
        + '<figure class="case-visual-page" data-case-page="ATT-1-p1">'
        + raster_markup
        + "</figure>"
    ).encode("utf-8")


def test_protected_visual_page_source_uses_lazy_relative_url() -> None:
    image_hash = "a" * 64
    html = _review_html(
        {
            "asset_key": "ATT-1-p1",
            "attachment_id": "ATT-1",
            "page": 1,
            "image_sha256": image_hash,
        },
        '<image data-case-page-image data-case-page-src="data:image/png;base64,AAAA"/>',
    )

    protected = protect_case_visual_sources(html).decode("utf-8")

    assert "data:image/png;base64" not in protected
    assert (
        f'data-case-page-src="./case-pages/ATT-1/1/{image_hash}"'
        in protected
    )


def test_protected_visual_tiles_use_lazy_relative_urls() -> None:
    page_hash = "a" * 64
    tile_hash = "b" * 64
    html = _review_html(
        {
            "asset_key": "ATT-1-p1",
            "attachment_id": "ATT-1",
            "page": 1,
            "image_sha256": page_hash,
            "tiles": [
                {
                    "x": 2048,
                    "y": 0,
                    "width": 2048,
                    "height": 2048,
                    "image_sha256": tile_hash,
                }
            ],
        },
        (
            '<image data-case-tile data-case-tile-src="data:image/png;base64,BBBB" '
            'data-tile-x="2048" data-tile-y="0" '
            'data-tile-width="2048" data-tile-height="2048"/>'
        ),
    )

    protected = protect_case_visual_sources(html).decode("utf-8")

    assert "data:image/png;base64" not in protected
    assert (
        f'data-case-tile-src="./case-tiles/ATT-1/1/2048/0/{tile_hash}"'
        in protected
    )
