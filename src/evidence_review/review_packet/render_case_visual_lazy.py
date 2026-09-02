"""Render Visual Review with external lazy raster sources."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from html import escape
from typing import cast

from evidence_review.review_packet.related_reference_routing import (
    related_reference_claims,
)
from evidence_review.review_packet.render_case_visual import (
    render_case_visual_review as _render_embedded_case_visual_review,
)

# ruff: noqa: E501

_FIGURE_RE = re.compile(
    r'<figure class="case-visual-page[^\"]*"[^>]*\bdata-case-page="(?P<asset>[^"]+)"[^>]*>.*?</figure>',
    re.DOTALL,
)
_PAGE_SOURCE_RE = re.compile(r'data-case-page-src="[^"]+"')
_TILE_TAG_RE = re.compile(r'<image\b(?P<attrs>[^>]*\bdata-case-tile\b[^>]*)/?>')
_TILE_SOURCE_RE = re.compile(r'data-case-tile-src="[^"]+"')
_REFERENCE_IMAGE_RE = re.compile(
    r'(?P<before><div class="reference-page-stage"[^>]*\bdata-reference-page="(?P<asset>[^"]+)"[^>]*>.*?)'
    r'(?P<image><image\b[^>]*\bdata-reference-page-image\b[^>]*/?>)',
    re.DOTALL,
)
_REFERENCE_SOURCE_RE = re.compile(r'data-reference-page-src="[^"]*"')
_DATA_ATTR_RE = re.compile(r'\b(?P<name>data-[a-z-]+)="(?P<value>[^"]*)"')
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LAZY_TILE_PLACEHOLDER = "data:image/png;base64,AA=="


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _page_index(model: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    visual = _mapping(model.get("case_visual_review"), "case_visual_review")
    result: dict[str, Mapping[str, object]] = {}
    for index, raw_page in enumerate(
        _sequence(visual.get("pages", []), "case_visual_review.pages")
    ):
        page = _mapping(raw_page, f"case_visual_review.pages[{index}]")
        asset_key = _text(page.get("asset_key"), "case visual asset_key")
        if asset_key in result:
            raise ValueError("duplicate case visual asset_key")
        result[asset_key] = page
    return result


def _reference_page_index(model: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    visual = _mapping(model.get("case_visual_review"), "case_visual_review")
    result: dict[str, Mapping[str, object]] = {}
    for index, raw_page in enumerate(
        _sequence(visual.get("reference_pages", []), "case_visual_review.reference_pages")
    ):
        page = _mapping(raw_page, f"case_visual_review.reference_pages[{index}]")
        asset_key = _text(page.get("asset_key"), "reference page asset_key")
        if asset_key in result:
            raise ValueError("duplicate reference page asset_key")
        source_hash = _text(page.get("source_hash"), "reference page source_hash")
        if not _SHA256_RE.fullmatch(source_hash):
            raise ValueError("reference page source_hash is invalid")
        _text(page.get("revision_id"), "reference page revision_id")
        _integer(page.get("page"), "reference page page")
        result[asset_key] = page
    return result


def _tile_hashes(page: Mapping[str, object]) -> dict[tuple[int, int], str]:
    result: dict[tuple[int, int], str] = {}
    for index, raw_tile in enumerate(_sequence(page.get("tiles", []), "page.tiles")):
        tile = _mapping(raw_tile, f"page.tiles[{index}]")
        key = (_integer(tile.get("x"), "tile.x"), _integer(tile.get("y"), "tile.y"))
        image_sha256 = _text(tile.get("image_sha256"), "tile.image_sha256")
        if key in result:
            raise ValueError("duplicate case visual tile coordinates")
        result[key] = image_sha256
    return result


def _with_related_reference_claims(model: Mapping[str, object]) -> Mapping[str, object]:
    """Add render-only related-reference claims without mutating machine claims."""
    raw_visual = model.get("case_visual_review")
    if raw_visual is None:
        return model
    visual = _mapping(raw_visual, "case_visual_review")
    related = related_reference_claims(visual)
    if not related:
        return model
    rendered_model = dict(model)
    claims = [
        dict(_mapping(item, f"claims[{index}]"))
        for index, item in enumerate(_sequence(model.get("claims", []), "claims"))
    ]
    existing_ids = {
        str(claim.get("claim_id")) for claim in claims if claim.get("claim_id")
    }
    for claim in related:
        claim_id = str(claim.get("claim_id", ""))
        if claim_id and claim_id not in existing_ids:
            claims.append(claim)
            existing_ids.add(claim_id)
    rendered_model["claims"] = claims
    return rendered_model


def _with_lazy_raster_placeholders(
    model: Mapping[str, object],
) -> Mapping[str, object]:
    """Copy case pages for rendering and synthesize only non-payload tile placeholders."""
    raw_visual = model.get("case_visual_review")
    if raw_visual is None:
        return model
    visual = _mapping(raw_visual, "case_visual_review")
    rendered_model = dict(model)
    rendered_visual = dict(visual)
    rendered_pages: list[dict[str, object]] = []
    for page_index, raw_page in enumerate(
        _sequence(visual.get("pages", []), "case_visual_review.pages")
    ):
        page = dict(_mapping(raw_page, f"case_visual_review.pages[{page_index}]"))
        raw_tiles = _sequence(page.get("tiles", []), f"case_visual_review.pages[{page_index}].tiles")
        if raw_tiles:
            tiles: list[dict[str, object]] = []
            for tile_index, raw_tile in enumerate(raw_tiles):
                tile = dict(
                    _mapping(
                        raw_tile,
                        f"case_visual_review.pages[{page_index}].tiles[{tile_index}]",
                    )
                )
                if "data_uri" not in tile:
                    tile["data_uri"] = _LAZY_TILE_PLACEHOLDER
                tiles.append(tile)
            page["tiles"] = tiles
        rendered_pages.append(page)
    rendered_visual["pages"] = rendered_pages
    rendered_model["case_visual_review"] = rendered_visual
    return rendered_model


def externalize_case_visual_sources(
    fragment: str,
    model: Mapping[str, object],
) -> str:
    """Replace embedded case raster bytes with protected-server relative URLs."""
    pages = _page_index(model)
    reference_pages = _reference_page_index(model)

    def rewrite_figure(match: re.Match[str]) -> str:
        page = pages.get(match.group("asset"))
        if page is None:
            raise ValueError("case visual page is missing from review model")
        attachment_id = escape(
            _text(page.get("attachment_id"), "case visual attachment_id"), quote=True
        )
        page_number = _integer(page.get("page"), "case visual page")
        page_hash = escape(
            _text(page.get("image_sha256"), "case visual image_sha256"), quote=True
        )
        block = _PAGE_SOURCE_RE.sub(
            f'data-case-page-src="./case-pages/{attachment_id}/{page_number}/{page_hash}"',
            match.group(0),
            count=1,
        )
        hashes = _tile_hashes(page)

        def rewrite_tile(tile_match: re.Match[str]) -> str:
            attrs = {
                item.group("name"): item.group("value")
                for item in _DATA_ATTR_RE.finditer(tile_match.group("attrs"))
            }
            try:
                x = int(attrs["data-tile-x"])
                y = int(attrs["data-tile-y"])
            except (KeyError, ValueError) as error:
                raise ValueError("case visual tile coordinates are invalid") from error
            tile_hash = hashes.get((x, y))
            if tile_hash is None:
                raise ValueError("case visual tile is missing from review model")
            url = (
                f"./case-tiles/{attachment_id}/{page_number}/{x}/{y}/"
                f"{escape(tile_hash, quote=True)}"
            )
            return _TILE_SOURCE_RE.sub(
                f'data-case-tile-src="{url}"',
                tile_match.group(0),
                count=1,
            )

        return _TILE_TAG_RE.sub(rewrite_tile, block)

    externalized = _FIGURE_RE.sub(rewrite_figure, fragment)

    def rewrite_reference(match: re.Match[str]) -> str:
        page = reference_pages.get(match.group("asset"))
        if page is None:
            raise ValueError("reference page is missing from review model")
        revision_id = escape(
            _text(page.get("revision_id"), "reference page revision_id"), quote=True
        )
        page_number = _integer(page.get("page"), "reference page page")
        source_hash = escape(
            _text(page.get("source_hash"), "reference page source_hash"), quote=True
        )
        url = f"./page-images/{revision_id}/{page_number}/{source_hash}"
        image = _REFERENCE_SOURCE_RE.sub(
            f'data-reference-page-src="{url}"',
            match.group("image"),
            count=1,
        )
        return match.group("before") + image

    externalized = _REFERENCE_IMAGE_RE.sub(rewrite_reference, externalized)
    if "data:image/png;base64," in externalized:
        raise ValueError("case visual fragment still contains embedded raster bytes")
    return externalized


def render_case_visual_review(model: Mapping[str, object]) -> str:
    """Render Visual Review without embedding case raster bytes in review.html."""
    rendered_model = _with_lazy_raster_placeholders(
        _with_related_reference_claims(model)
    )
    fragment = _render_embedded_case_visual_review(rendered_model)
    if not fragment:
        return ""
    return externalize_case_visual_sources(fragment, model)


__all__ = ["externalize_case_visual_sources", "render_case_visual_review"]