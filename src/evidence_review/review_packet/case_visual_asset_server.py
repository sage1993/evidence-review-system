"""Protected lazy asset delivery for case-specific Visual Review rasters."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlsplit

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.filesystem_trust import verified_regular_file_below
from evidence_review.review_packet import local_server

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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


def _trusted_file(workspace_root: Path, *parts: str) -> Path | None:
    try:
        return verified_regular_file_below(
            workspace_root,
            parts,
            field="case visual asset",
        )
    except (FileNotFoundError, OSError, ValueError):
        return None


def _page_asset(workspace_root: Path, route: _CaseAssetRoute) -> bytes | None:
    filename = f"page-{route.page_number:04d}.png"
    for cache_name in ("case-page-images-hq-v1", "case-page-images"):
        path = _trusted_file(
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
    manifest_path = _trusted_file(workspace_root, *directory_parts, "manifest.json")
    if manifest_path is None:
        return None
    try:
        manifest = _mapping(
            json.loads(manifest_path.read_text(encoding="utf-8")),
            "tile manifest",
        )
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
        path = _trusted_file(workspace_root, *directory_parts, filename)
        if path is None:
            return None
        try:
            body = path.read_bytes()
        except OSError:
            return None
        return body if hashlib.sha256(body).hexdigest() == route.image_sha256 else None
    return None


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
        asset_kind = "case-page" if case_route.kind == "page" else "case-tile"
        if case_route.kind == "page":
            route_key = (
                f"case-page/{case_route.attachment_id}/{case_route.page_number}/"
                f"{case_route.image_sha256}"
            )
        else:
            route_key = (
                f"case-tile/{case_route.attachment_id}/{case_route.page_number}/"
                f"{case_route.tile_x}/{case_route.tile_y}/{case_route.image_sha256}"
            )
        if not self.state.asset_allowed(case_route.run_id, asset_kind, route_key):
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
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
    """Enable protected case-page routes without mutating global HTML behavior."""
    server.RequestHandlerClass = CaseVisualReviewHandler


__all__ = ["configure_case_visual_server"]