from pathlib import Path

from evidence_review.drawing_review.visual_pages import (
    VisualPageAsset,
    VisualPageTile,
)
from evidence_review.review_packet import case_visual_projection
from evidence_review.review_packet import render_case_visual_lazy


def test_tiled_projection_reuses_verified_metadata_without_tile_payload_read(
    monkeypatch,
    tmp_path: Path,
) -> None:
    tile = VisualPageTile(
        path=tmp_path / "tile-must-not-be-read.png",
        x=0,
        y=0,
        width=2048,
        height=2048,
        image_sha256="b" * 64,
    )
    asset = VisualPageAsset(
        attachment_id="ATT-1",
        source_sha256="a" * 64,
        page=1,
        width=4764.0,
        height=3368.0,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        image_path=tmp_path / "page.png",
        image_sha256="c" * 64,
    )
    monkeypatch.setattr(
        case_visual_projection,
        "ensure_visual_page_tiles",
        lambda _workspace, _asset: (tile,),
    )

    projected = case_visual_projection._page_tile_documents(tmp_path, asset)

    assert projected == [
        {
            "x": 0,
            "y": 0,
            "width": 2048,
            "height": 2048,
            "image_sha256": "b" * 64,
        }
    ]


def test_lazy_renderer_externalizes_metadata_only_tile_without_mutating_model(
    monkeypatch,
) -> None:
    tile_hash = "b" * 64
    model: dict[str, object] = {
        "claims": [],
        "case_visual_review": {
            "pages": [
                {
                    "asset_key": "ATT-1-p1",
                    "attachment_id": "ATT-1",
                    "page": 1,
                    "image_sha256": "a" * 64,
                    "tiles": [
                        {
                            "x": 0,
                            "y": 0,
                            "width": 2048,
                            "height": 2048,
                            "image_sha256": tile_hash,
                        }
                    ],
                }
            ]
        },
    }
    monkeypatch.setattr(
        render_case_visual_lazy,
        "related_reference_claims",
        lambda _visual: [],
    )

    def fake_embedded(rendered_model: object) -> str:
        rendered = rendered_model
        assert isinstance(rendered, dict)
        visual = rendered["case_visual_review"]
        assert isinstance(visual, dict)
        pages = visual["pages"]
        assert isinstance(pages, list)
        page = pages[0]
        assert isinstance(page, dict)
        tiles = page["tiles"]
        assert isinstance(tiles, list)
        tile = tiles[0]
        assert isinstance(tile, dict)
        placeholder = tile["data_uri"]
        assert isinstance(placeholder, str)
        assert placeholder.startswith("data:image/png;base64,")
        return (
            '<figure class="case-visual-page" data-case-page="ATT-1-p1">'
            '<image data-case-page-image data-case-page-src="placeholder"/>'
            '<image data-case-tile data-case-tile-src="placeholder" '
            'data-tile-x="0" data-tile-y="0" '
            'data-tile-width="2048" data-tile-height="2048"/>'
            "</figure>"
        )

    monkeypatch.setattr(
        render_case_visual_lazy,
        "_render_embedded_case_visual_review",
        fake_embedded,
    )

    html = render_case_visual_lazy.render_case_visual_review(model)

    assert (
        f'data-case-tile-src="./case-tiles/ATT-1/1/0/0/{tile_hash}"'
        in html
    )
    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    pages = visual["pages"]
    assert isinstance(pages, list)
    page = pages[0]
    assert isinstance(page, dict)
    tiles = page["tiles"]
    assert isinstance(tiles, list)
    tile = tiles[0]
    assert isinstance(tile, dict)
    assert "data_uri" not in tile
