"""Protected lazy asset delivery for case-specific Visual Review rasters."""
from __future__ import annotations

import hashlib
import json
import logging
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
_LOGGER = logging.getLogger(__name__)


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


def _trusted_file(workspace_root: Path, *parts: str) -> tuple[str, Path | None]:
    try:
        return (
            "AVAILABLE",
            verified_regular_file_below(
                workspace_root,
                parts,
                field="case visual asset",
            ),
        )
    except FileNotFoundError:
        return "ASSET_MISSING", None
    except (PermissionError, OSError):
        return "ASSET_PERMISSION_DENIED", None
    except ValueError:
        return "ASSET_MISSING", None


def _page_asset(
    workspace_root: Path,
    route: _CaseAssetRoute,
    *,
    cache_identity: str | None = None,
) -> tuple[str, bytes | None]:
    filename = f"page-{route.page_number:04d}.png"
    permission_denied = False
    hash_mismatch = False
    identities = (cache_identity, route.attachment_id)
    for cache_name in ("case-page-images-hq-v1", "case-page-images"):
        for identity in identities:
            if identity is None:
                continue
            trust_status, path = _trusted_file(
                workspace_root,
                cache_name,
                identity,
                filename,
            )
            if path is None:
                permission_denied = permission_denied or trust_status == "ASSET_PERMISSION_DENIED"
                continue
            try:
                body = path.read_bytes()
            except (PermissionError, OSError):
                permission_denied = True
                continue
            if hashlib.sha256(body).hexdigest() == route.image_sha256:
                return "AVAILABLE", body
            hash_mismatch = True
    if permission_denied:
        return "ASSET_PERMISSION_DENIED", None
    if hash_mismatch:
        return "ASSET_HASH_MISMATCH", None
    return "ASSET_MISSING", None


def _tile_asset(
    workspace_root: Path,
    route: _CaseAssetRoute,
    *,
    cache_identity: str | None = None,
) -> tuple[str, bytes | None]:
    if route.tile_x is None or route.tile_y is None:
        return "ASSET_MISSING", None
    permission_denied = False
    invalid = False
    hash_mismatch = False
    identities = (cache_identity, route.attachment_id)
    for identity in identities:
        if identity is None:
            continue
        directory_parts = (
            "case-page-tiles-v1",
            identity,
            f"page-{route.page_number:04d}",
        )
        manifest_status, manifest_path = _trusted_file(
            workspace_root,
            *directory_parts,
            "manifest.json",
        )
        if manifest_path is None:
            permission_denied = permission_denied or manifest_status == "ASSET_PERMISSION_DENIED"
            continue
        try:
            manifest = _mapping(
                json.loads(manifest_path.read_text(encoding="utf-8")),
                "tile manifest",
            )
            records = _sequence(manifest.get("tiles", []), "tile manifest.tiles")
        except PermissionError:
            permission_denied = True
            continue
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            invalid = True
            continue
        for index, raw_record in enumerate(records):
            try:
                record = _mapping(raw_record, f"tile manifest.tiles[{index}]")
                x = _integer(record.get("x"), "tile.x")
                y = _integer(record.get("y"), "tile.y")
            except ValueError:
                invalid = True
                continue
            if x != route.tile_x or y != route.tile_y:
                continue
            filename = record.get("filename")
            image_sha256 = record.get("image_sha256")
            if (
                not isinstance(filename, str)
                or Path(filename).name != filename
                or image_sha256 != route.image_sha256
            ):
                hash_mismatch = True
                break
            trust_status, path = _trusted_file(workspace_root, *directory_parts, filename)
            if path is None:
                permission_denied = permission_denied or trust_status == "ASSET_PERMISSION_DENIED"
                continue
            try:
                body = path.read_bytes()
            except (PermissionError, OSError):
                permission_denied = True
                continue
            if hashlib.sha256(body).hexdigest() == route.image_sha256:
                return "AVAILABLE", body
            hash_mismatch = True
            break
    if permission_denied:
        return "ASSET_PERMISSION_DENIED", None
    if hash_mismatch:
        return "ASSET_HASH_MISMATCH", None
    if invalid:
        return "ASSET_INVALID", None
    return "ASSET_MISSING", None


class CaseVisualReviewHandler(local_server._ReviewHandler):
    def _case_cache_identity(self, route: _CaseAssetRoute) -> str | None:
        projection = self.state.protected_projections.get(route.run_id)
        if projection is None:
            return None
        visual = projection.model.get("case_visual_review")
        if not isinstance(visual, Mapping):
            return None
        pages = visual.get("pages")
        if not isinstance(pages, Sequence) or isinstance(pages, (str, bytes, bytearray)):
            return None
        for raw_page in pages:
            if not isinstance(raw_page, Mapping):
                continue
            if (
                raw_page.get("attachment_id") != route.attachment_id
                or raw_page.get("page") != route.page_number
            ):
                continue
            if route.kind == "page":
                if raw_page.get("image_sha256") != route.image_sha256:
                    continue
            else:
                tiles = raw_page.get("tiles")
                if not isinstance(tiles, Sequence) or isinstance(tiles, (str, bytes, bytearray)):
                    continue
                if not any(
                    isinstance(raw_tile, Mapping)
                    and raw_tile.get("x") == route.tile_x
                    and raw_tile.get("y") == route.tile_y
                    and raw_tile.get("image_sha256") == route.image_sha256
                    for raw_tile in tiles
                ):
                    continue
            case_id = raw_page.get("case_id")
            source_sha256 = raw_page.get("source_sha256")
            if (
                isinstance(case_id, str)
                and case_id
                and isinstance(source_sha256, str)
                and _SHA256_RE.fullmatch(source_sha256)
            ):
                return f"{case_id}--{route.attachment_id}--{source_sha256}"
        return None

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
        if self._current_presentation(authorization_route) is None:
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
        diagnostic, body = (
            _page_asset(
                self.state.workspace_root,
                case_route,
                cache_identity=self._case_cache_identity(case_route),
            )
            if case_route.kind == "page"
            else _tile_asset(
                self.state.workspace_root,
                case_route,
                cache_identity=self._case_cache_identity(case_route),
            )
        )
        if body is None:
            _LOGGER.info(
                "protected case asset unavailable: diagnostic=%s run_id=%s "
                "kind=%s attachment_id=%s page=%s",
                diagnostic,
                case_route.run_id,
                case_route.kind,
                case_route.attachment_id,
                case_route.page_number,
            )
            self._reject(HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return
        self._send_bytes(HTTPStatus.OK, body, "image/png")


def configure_case_visual_server(server: ThreadingHTTPServer) -> None:
    """Enable protected case-page routes without mutating global HTML behavior."""
    server.RequestHandlerClass = CaseVisualReviewHandler


__all__ = ["configure_case_visual_server"]
