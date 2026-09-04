import json

from evidence_review.review_packet.case_visual_asset_server import (
    _protected_review_html,
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


def test_case_asset_protector_leaves_reference_page_on_generic_namespace() -> None:
    source_hash = "c" * 64
    html = _review_html(
        {
            "asset_key": "ATT-1-p1",
            "attachment_id": "ATT-1",
            "page": 1,
            "image_sha256": "a" * 64,
        },
        (
            '<image data-reference-page-image '
            f'data-reference-page-src="./page-images/REV-REF/12/{source_hash}"/>'
        ),
    )

    protected = protect_case_visual_sources(html).decode("utf-8")

    assert (
        f'data-reference-page-src="./page-images/REV-REF/12/{source_hash}"'
        in protected
    )
    assert "./reference-pages/" not in protected


def test_protected_review_html_removes_case_payload_from_review_model() -> None:
    source_hash = "c" * 64
    model = {
        "claims": [
            {
                "citations": [
                    {
                        "citation_id": "CIT-1",
                        "revision_id": "REV-1",
                        "page_number": 1,
                        "source_hash": source_hash,
                    }
                ]
            }
        ],
        "case_visual_review": {
            "pages": [
                {
                    "asset_key": "ATT-1-p1",
                    "attachment_id": "ATT-1",
                    "page": 1,
                    "image_sha256": "a" * 64,
                    "data_uri": "data:image/png;base64,AAAA",
                    "tiles": [],
                }
            ]
        },
    }
    html = (
        '<div class="app-shell"></div>'
        '<article class="citation" data-asset-key="page-1" '
        'data-citation-id="CIT-1"></article>'
        '<figure class="evidence-page" data-asset-key="page-1">'
        '<img data-page-image-source="page-1" src="data:image/png;base64,BBBB">'
        "</figure>"
        '<figure class="case-visual-page" data-case-page="ATT-1-p1">'
        '<image data-case-page-src="./case-pages/ATT-1/1/'
        + "a" * 64
        + '"></figure>'
        '<script id="review-model" type="application/json">'
        + json.dumps(model, sort_keys=True, separators=(",", ":"))
        + "</script>"
    ).encode("utf-8")

    protected = _protected_review_html(html).decode("utf-8")

    assert '"data_uri"' not in protected
    assert 'data-page-src="./page-images/REV-1/1/' + source_hash + '"' in protected
