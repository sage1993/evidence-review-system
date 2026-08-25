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
_DATA_ATTR_RE = re.compile(r'\b(?P<name>data-[a-z-]+)="(?P<value>[^"]*)"')


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
    visual = _mapping(model.get("case_visual_review"), "case_visual_review")
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


def externalize_case_visual_sources(
    fragment: str,
    model: Mapping[str, object],
) -> str:
    """Replace embedded case raster bytes with protected-server relative URLs."""
    pages = _page_index(model)

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
    if "data:image/png;base64," in externalized:
        raise ValueError("case visual fragment still contains embedded raster bytes")
    return externalized


def render_case_visual_review(model: Mapping[str, object]) -> str:
    """Render Visual Review without embedding case raster bytes in review.html."""
    fragment = _render_embedded_case_visual_review(
        _with_related_reference_claims(model)
    )
    if not fragment:
        return ""
    return externalize_case_visual_sources(fragment, model)


__all__ = ["externalize_case_visual_sources", "render_case_visual_review"]
