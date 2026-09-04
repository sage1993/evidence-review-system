"""Protected lazy asset support for case-specific Visual Review rasters."""
from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlsplit

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.review_packet import local_server

# ruff: noqa: E501

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FIGURE_RE = re.compile(
    r'<figure class="case-visual-page[^\"]*"[^>]*\bdata-case-page="(?P<asset>[^"]+)"[^>]*>.*?</figure>',
    re.DOTALL,
)
_PAGE_SOURCE_RE = re.compile(r'data-case-page-src="data:image/[^\"]+"')
_TILE_TAG_RE = re.compile(r'<image\b(?P<attrs>[^>]*\bdata-case-tile\b[^>]*)/?>')
_TILE_SOURCE_RE = re.compile(r'data-case-tile-src="data:image/[^\"]+"')
_DATA_ATTR_RE = re.compile(r'\b(?P<name>data-[a-z-]+)="(?P<value>[^"]*)"')
_ORIGINAL_PROTECTED_REVIEW_HTML = local_server._protected_review_html
_PROTECTED_HTML_INSTALLED = False


@dataclass(frozen=True, slots=True)
class _CaseAssetRoute:
    run_id: str
    token: str
    kind: str
    attachment_id: str
    page_number: int
    image_sha256: str
    tile_x: int | None = None
    tile_y: int | None = None


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


def _case_page_index(model: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    visual = model.get("case_visual_review")
    if visual is None:
        return {}
    visual_mapping = _mapping(visual, "case_visual_review")
    result: dict[str, Mapping[str, object]] = {}
    for index, raw_page in enumerate(
        _sequence(visual_mapping.get("pages", []), "case_visual_review.pages")
    ):
        page = _mapping(raw_page, f"case_visual_review.pages[{index}]")
        asset_key = page.get("asset_key")
        if isinstance(asset_key, str) and asset_key:
            result[asset_key] = page
    return result


def _tile_index(page: Mapping[str, object]) -> dict[tuple[int, int], str]:
    result: dict[tuple[int, int], str] = {}
    for index, raw_tile in enumerate(_sequence(page.get("tiles", []), "page.tiles")):
        tile = _mapping(raw_tile, f"page.tiles[{index}]")
        x = _integer(tile.get("x"), "tile.x")
        y = _integer(tile.get("y"), "tile.y")
        image_sha256 = tile.get("image_sha256")
        if not isinstance(image_sha256, str) or not _SHA256_RE.fullmatch(image_sha256):
            raise ValueError("case visual tile hash is invalid")
        result[(x, y)] = image_sha256
    return result


def protect_case_visual_sources(html_bytes: bytes) -> bytes:
    """Replace embedded case raster payloads with protected relative asset URLs."""
    try:
        html = html_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("review HTML must be UTF-8") from error
    model_match = local_server._MODEL_SCRIPT.search(html)
    if model_match is None:
        return html_bytes
    try:
        model = _mapping(json.loads(model_match.group("model")), "review model")
    except json.JSONDecodeError as error:
        raise ValueError("review model is invalid JSON") from error
    pages = _case_page_index(model)
    if not pages:
        return html_bytes

    def rewrite_figure(match: re.Match[str]) -> str:
        block = match.group(0)
        page = pages.get(match.group("asset"))
        if page is None:
            raise ValueError("case visual page asset is missing from review model")
        attachment_id = validate_identifier(page.get("attachment_id"), "attachment_id")
        page_number = _integer(page.get("page"), "case visual page")
        image_sha256 = page.get("image_sha256")
        if not isinstance(image_sha256, str) or not _SHA256_RE.fullmatch(image_sha256):
            raise ValueError("case visual page hash is invalid")
        page_url = f"./case-pages/{attachment_id}/{page_number}/{image_sha256}"
        block = _PAGE_SOURCE_RE.sub(
            f'data-case-page-src="{page_url}"',
            block,
            count=1,
        )
        tile_hashes = _tile_index(page)

        def rewrite_tile(tile_match: re.Match[str]) -> str:
            tag = tile_match.group(0)
            attrs = {
                item.group("name"): item.group("value")
                for item in _DATA_ATTR_RE.finditer(tile_match.group("attrs"))
            }
            try:
                x = int(attrs["data-tile-x"])
                y = int(attrs["data-tile-y"])
            except (KeyError, ValueError) as error:
                raise ValueError("case visual tile coordinates are invalid") from error
            tile_hash = tile_hashes.get((x, y))
            if tile_hash is None:
                raise ValueError("case visual tile asset is missing from review model")
            tile_url = (
                f"./case-tiles/{attachment_id}/{page_number}/{x}/{y}/{tile_hash}"
            )
            return _TILE_SOURCE_RE.sub(
                f'data-case-tile-src="{tile_url}"',
                tag,
                count=1,
            )

        return _TILE_TAG_RE.sub(rewrite_tile, block)

    return _FIGURE_RE.sub(rewrite_figure, html).encode("utf-8")


def _strip_case_raster_payload_from_model(html_bytes: bytes) -> bytes:
    """Remove case raster bytes from the protected presentation model only."""
    try:
        html = html_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("review HTML must be UTF-8") from error
    model_match = local_server._MODEL_SCRIPT.search(html)
    if model_match is None:
        return html_bytes
    try:
        model = _mapping(json.loads(model_match.group("model")), "review model")
    except json.JSONDecodeError as error:
        raise ValueError("review model is invalid JSON") from error
    raw_visual = model.get("case_visual_review")
    if raw_visual is None:
        return html_bytes
    visual = _mapping(raw_visual, "case_visual_review")
    pages = _sequence(visual.get("pages", []), "case_visual_review.pages")
    cleaned_pages: list[dict[str, object]] = []
    for index, raw_page in enumerate(pages):
        page = dict(_mapping(raw_page, f"case_visual_review.pages[{index}]"))
        page.pop("data_uri", None)
        raw_tiles = page.get("tiles")
        if isinstance(raw_tiles, list):
            cleaned_tiles: list[dict[str, object]] = []
            for tile_index, raw_tile in enumerate(raw_tiles):
                tile = dict(
                    _mapping(
                        raw_tile,
                        f"case_visual_review.pages[{index}].tiles[{tile_index}]",
                    )
                )
                tile.pop("data_uri", None)
                cleaned_tiles.append(tile)
            page["tiles"] = cleaned_tiles
        cleaned_pages.append(page)
    cleaned_visual = dict(visual)
    cleaned_visual["pages"] = cleaned_pages
    cleaned_model = dict(model)
    cleaned_model["case_visual_review"] = cleaned_visual
    serialized = json.dumps(
        cleaned_model,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    start, end = model_match.span("model")
    return (html[:start] + serialized + html[end:]).encode("utf-8")


def _case_asset_route(path: str) -> _CaseAssetRoute | None:
    parsed = urlsplit(path)
    if parsed.query or parsed.fragment:
        return None
    raw_parts = parsed.path.split("/")
    if not raw_parts or raw_parts[0] != "" or any(not part for part in raw_parts[1:]):
        return None
    parts = [unquote(part) for part in raw_parts[1:]]
    if any(
        part in {".", ".."} or "/" in part or "\\" in part or ":" in part
        for part in parts
    ):
        return None
    if len(parts) not in {7, 9} or parts[0] != "runs":
        return None
    try:
        run_id = validate_identifier(parts[1], "run_id")
        attachment_id = validate_identifier(parts[4], "attachment_id")
        page_number = int(parts[5])
    except (TypeError, ValueError):
        return None
    token = parts[2]
    if not local_server._TOKEN_PATTERN.fullmatch(token) or page_number < 1:
        return None
    if parts[3] == "case-pages" and len(parts) == 7:
        image_sha256 = parts[6]
        if not _SHA256_RE.fullmatch(image_sha256):
            return None
        return _CaseAssetRoute(
            run_id=run_id,
            token=token,
            kind="page",
            attachment_id=attachment_id,
            page_number=page_number,
            image_sha256=image_sha256,
        )
    if parts[3] == "case-tiles" and len(parts) == 9:
        try:
            tile_x = int(parts[6])
            tile_y = int(parts[7])
        except ValueError:
            return None
        image_sha256 = parts[8]
        if tile_x < 0 or tile_y < 0 or not _SHA256_RE.fullmatch(image_sha256):
            return None
        return _CaseAssetRoute(
            run_id=run_id,
            token=token,
            kind="tile",
            attachment_id=attachment_id,
            page_number=page_number,
            image_sha256=image_sha256,
            tile_x=tile_x,
            tile_y=tile_y,
        )
    return None


def _regular_file(root: Path, *parts: str) -> Path | None:
    try:
        resolved_root = root.resolve(strict=True)
        candidate = resolved_root
        for index, part in enumerate(parts):
            candidate = candidate / part
            status = candidate.lstat()
            if stat.S_ISLNK(status.st_mode) or local_server._is_reparse_point(status):
                return None
            if index == len(parts) - 1:
                if not stat.S_ISREG(status.st_mode):
                    return None
            elif not stat.S_ISDIR(status.st_mode):
                return None
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
        return resolved
    except (OSError, ValueError):
        return None


def _page_asset(workspace_root: Path, route: _CaseAssetRoute) -> bytes | None:
    filename = f"page-{route.page_number:04d}.png"
    for cache_name in ("case-page-images-hq-v1", "case-page-images"):
        path = _regular_file(
            workspace_root,
            cache_name,
            route.attachment_id,
            filename,
        )
        if path is None:
            continue
        try:
            body = path.read_bytes()
        except OSError:
            continue
        if hashlib.sha256(body).hexdigest() == route.image_sha256:
            return body
    return None


def _tile_asset(workspace_root: Path, route: _CaseAssetRoute) -> bytes | None:
    if route.tile_x is None or route.tile_y is None:
        return None
    directory_parts = (
        "case-page-tiles-v1",
        route.attachment_id,
        f"page-{route.page_number:04d}",
    )
    manifest_path = _regular_file(workspace_root, *directory_parts, "manifest.json")
    if manifest_path is None:
        return None
    try:
        manifest = _mapping(json.loads(manifest_path.read_text(encoding="utf-8")), "tile manifest")
        records = _sequence(manifest.get("tiles", []), "tile manifest.tiles")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    for index, raw_record in enumerate(records):
        try:
            record = _mapping(raw_record, f"tile manifest.tiles[{index}]")
            x = _integer(record.get("x"), "tile.x")
            y = _integer(record.get("y"), "tile.y")
        except ValueError:
            return None
        if x != route.tile_x or y != route.tile_y:
            continue
        filename = record.get("filename")
        image_sha256 = record.get("image_sha256")
        if (
            not isinstance(filename, str)
            or Path(filename).name != filename
            or image_sha256 != route.image_sha256
        ):
            return None
        path = _regular_file(workspace_root, *directory_parts, filename)
        if path is None:
            return None
        try:
            body = path.read_bytes()
        except OSError:
            return None
        return body if hashlib.sha256(body).hexdigest() == route.image_sha256 else None
    return None


def _protected_review_html(html_bytes: bytes) -> bytes:
    sanitized = _strip_case_raster_payload_from_model(html_bytes)
    return _ORIGINAL_PROTECTED_REVIEW_HTML(protect_case_visual_sources(sanitized))


class CaseVisualReviewHandler(local_server._ReviewHandler):
    def do_GET(self) -> None:  # noqa: N802
        case_route = _case_asset_route(self.path)
        if case_route is None:
            super().do_GET()
            return
        authorization_route = local_server._Route(
            run_id=case_route.run_id,
            token=case_route.token,
            endpoint="review",
        )
        if not self._authorized(authorization_route, require_origin=False):
            return
        self.state.mark_activity()
        body = (
            _page_asset(self.state.workspace_root, case_route)
            if case_route.kind == "page"
            else _tile_asset(self.state.workspace_root, case_route)
        )
        if body is None:
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return
        self._send_bytes(HTTPStatus.OK, body, "image/png")


def configure_case_visual_server(server: ThreadingHTTPServer) -> None:
    """Enable protected case-page routes on one loopback review server."""
    global _PROTECTED_HTML_INSTALLED
    if not _PROTECTED_HTML_INSTALLED:
        local_server._protected_review_html = _protected_review_html
        _PROTECTED_HTML_INSTALLED = True
    server.RequestHandlerClass = CaseVisualReviewHandler


__all__ = ["configure_case_visual_server", "protect_case_visual_sources"]
