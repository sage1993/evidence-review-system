from pathlib import Path

from evidence_review.drawing_review.visual_pages import (
    VisualPageAsset,
    VisualPageTile,
)
from evidence_review.review_packet import case_visual_projection, render_case_visual_lazy


def test_tiled_projection_reuses_verified_metadata_without_tile_payload_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    page = VisualPageAsset(
        attachment_id="ATT-TEST",
        page_number=1,
        width_px=4764,
        height_px=3368,
        image_path=workspace / "missing-page.png",
        image_sha256="a" * 64,
    )
    tile = VisualPageTile(
        x=0,
        y=0,
        width=2048,
        height=2048,
        path=workspace / "missing-tile.png",
        image_sha256="b" * 64,
    )
    monkeypatch.setattr(
        case_visual_projection,
        "ensure_visual_page_tiles",
        lambda _workspace, _asset: (tile,),
    )

    documents = case_visual_projection._page_tile_documents(workspace, page)

    assert documents == [
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
    model = {
        "case_visual_review": {
            "pages": [
                {
                    "attachment_id": "ATT-TEST",
                    "page_number": 1,
                    "width_px": 4764,
                    "height_px": 3368,
                    "image_sha256": "a" * 64,
                    "tiles": [
                        {
                            "x": 0,
                            "y": 0,
                            "width": 2048,
                            "height": 2048,
                            "image_sha256": "b" * 64,
                        }
                    ],
                }
            ]
        }
    }

    monkeypatch.setattr(
        render_case_visual_lazy,
        "related_reference_claims",
        lambda _model: [],
    )

    def fake_embedded_renderer(rendered_model: object) -> str:
        assert isinstance(rendered_model, dict)
        visual = rendered_model["case_visual_review"]
        assert isinstance(visual, dict)
        pages = visual["pages"]
        assert isinstance(pages, list)
        page = pages[0]
        assert isinstance(page, dict)
        tiles = page["tiles"]
        assert isinstance(tiles, list)
        tile = tiles[0]
        assert isinstance(tile, dict)
        data_uri = tile["data_uri"]
        assert isinstance(data_uri, str)
        assert data_uri.startswith("data:image/")
        return (
            '<img data-case-tile-src="'
            + data_uri
            + '" data-case-attachment-id="ATT-TEST" '
            + 'data-case-page-number="1" data-case-tile-x="0" '
            + 'data-case-tile-y="0">'
        )

    monkeypatch.setattr(
        render_case_visual_lazy,
        "_render_case_visual_review_embedded",
        fake_embedded_renderer,
    )

    html = render_case_visual_lazy.render_case_visual_review(model)

    assert (
        './case-tiles/ATT-TEST/1/0/0/' + "b" * 64
    ) in html
    assert "data:image/png;base64," not in html
    tile = model["case_visual_review"]["pages"][0]["tiles"][0]
    assert "data_uri" not in tile
