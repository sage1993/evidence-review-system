"""Explicit protected Review Workspace projection and asset capability manifest."""
from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.review_packet.page_image_verifier import (
    read_verified_page_image,
    verify_review_page_images,
)

_MODEL_SCRIPT = re.compile(
    r'<script id="review-model" type="application/json">(?P<model>.*?)</script>',
    re.DOTALL,
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
AssetKind = Literal["reference-page", "case-page", "case-tile"]


@dataclass(frozen=True, slots=True)
class ProtectedAssetRef:
    asset_kind: AssetKind
    route_key: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ProtectedReviewProjection:
    model: dict[str, object]
    assets: Sequence[ProtectedAssetRef]


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be a SHA-256")
    return value


def load_archive_review_model(html_bytes: bytes) -> dict[str, object]:
    """Parse the canonical review-model script without treating archive markup as authority."""
    try:
        html = html_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("review HTML must be UTF-8") from error
    match = _MODEL_SCRIPT.search(html)
    if match is None:
        raise ValueError("review model missing")
    import json

    try:
        value = json.loads(match.group("model"))
    except json.JSONDecodeError as error:
        raise ValueError("review model is invalid JSON") from error
    return dict(_mapping(value, "review model"))


def _assert_no_raster_payload(value: object, field: str = "review model") -> None:
    if isinstance(value, str):
        if value.startswith("data:image/"):
            raise ValueError(f"{field} contains embedded raster payload")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_no_raster_payload(item, f"{field}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _assert_no_raster_payload(item, f"{field}[{index}]")


def build_protected_review_projection(
    view_model: Mapping[str, object],
    page_image_root: Path,
) -> ProtectedReviewProjection:
    """Build a raster-payload-free model plus the exact assets it is allowed to request."""
    model = copy.deepcopy(dict(_mapping(view_model, "view_model")))
    assets: dict[tuple[AssetKind, str], ProtectedAssetRef] = {}

    def add(kind: AssetKind, route_key: str, image_sha256: str) -> None:
        ref = ProtectedAssetRef(kind, route_key, _sha256(image_sha256, "asset.sha256"))
        key = (kind, route_key)
        previous = assets.get(key)
        if previous is not None and previous.sha256 != ref.sha256:
            raise ValueError("protected asset route has conflicting hashes")
        assets[key] = ref

    for verified in verify_review_page_images(model, page_image_root):
        route_key = (
            f"reference-page/{verified.revision_id}/{verified.page_number}/"
            f"{verified.source_hash}"
        )
        add("reference-page", route_key, verified.image_sha256)

    raw_visual = model.get("case_visual_review")
    if raw_visual is not None:
        visual = dict(_mapping(raw_visual, "case_visual_review"))
        protected_pages: list[dict[str, object]] = []
        for page_index, raw_page in enumerate(
            _sequence(visual.get("pages", []), "case_visual_review.pages")
        ):
            page = dict(
                _mapping(raw_page, f"case_visual_review.pages[{page_index}]")
            )
            page.pop("data_uri", None)
            attachment_id = validate_identifier(
                page.get("attachment_id"), "attachment_id"
            )
            page_number = _positive_int(page.get("page"), "case visual page")
            page_hash = _sha256(
                page.get("image_sha256"), "case visual image_sha256"
            )
            page_route = (
                f"case-page/{attachment_id}/{page_number}/{page_hash}"
            )
            page["protected_asset"] = {
                "kind": "case-page",
                "route_key": page_route,
            }
            add("case-page", page_route, page_hash)

            protected_tiles: list[dict[str, object]] = []
            for tile_index, raw_tile in enumerate(
                _sequence(page.get("tiles", []), f"case_visual_review.pages[{page_index}].tiles")
            ):
                tile = dict(
                    _mapping(
                        raw_tile,
                        f"case_visual_review.pages[{page_index}].tiles[{tile_index}]",
                    )
                )
                tile.pop("data_uri", None)
                x = _nonnegative_int(tile.get("x"), "case visual tile x")
                y = _nonnegative_int(tile.get("y"), "case visual tile y")
                tile_hash = _sha256(
                    tile.get("image_sha256"), "case visual tile image_sha256"
                )
                tile_route = (
                    f"case-tile/{attachment_id}/{page_number}/{x}/{y}/{tile_hash}"
                )
                tile["protected_asset"] = {
                    "kind": "case-tile",
                    "route_key": tile_route,
                }
                add("case-tile", tile_route, tile_hash)
                protected_tiles.append(tile)
            page["tiles"] = protected_tiles
            protected_pages.append(page)
        visual["pages"] = protected_pages

        protected_reference_pages: list[dict[str, object]] = []
        for reference_index, raw_page in enumerate(
            _sequence(
                visual.get("reference_pages", []),
                "case_visual_review.reference_pages",
            )
        ):
            page = dict(
                _mapping(
                    raw_page,
                    f"case_visual_review.reference_pages[{reference_index}]",
                )
            )
            revision_id = validate_identifier(
                page.get("revision_id"), "reference revision_id"
            )
            page_number = _positive_int(
                page.get("page"), "reference page"
            )
            source_hash = _sha256(
                page.get("source_hash"), "reference source_hash"
            )
            verified = read_verified_page_image(
                page_image_root,
                revision_id,
                page_number,
                source_hash,
            )
            route_key = (
                f"reference-page/{revision_id}/{page_number}/{source_hash}"
            )
            page["protected_asset"] = {
                "kind": "reference-page",
                "route_key": route_key,
            }
            add("reference-page", route_key, verified.image_sha256)
            protected_reference_pages.append(page)
        visual["reference_pages"] = protected_reference_pages
        model["case_visual_review"] = visual

    _assert_no_raster_payload(model)
    return ProtectedReviewProjection(
        model=model,
        assets=tuple(assets.values()),
    )


__all__ = [
    "ProtectedAssetRef",
    "ProtectedReviewProjection",
    "build_protected_review_projection",
    "load_archive_review_model",
]
