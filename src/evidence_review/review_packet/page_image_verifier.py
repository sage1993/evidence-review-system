"""Verification boundary for cached Review Workspace page images."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from evidence_review.contracts.legacy_formats import LEGACY_PAGE_IMAGE_FORMAT
from evidence_review.filesystem_trust import verified_regular_file_below

_PAGE_IMAGE_FORMAT = "evidence-review/page-image"
_GEOMETRY_TOLERANCE = 0.5


@dataclass(frozen=True, slots=True)
class VerifiedPageImage:
    revision_id: str
    page_number: int
    source_hash: str
    image_path: Path
    image_sha256: str
    image_bytes: bytes
    pdf_width: float
    pdf_height: float
    origin_x: float
    origin_y: float
    rotation: int
    box_kind: str


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _page_number(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("citation page_number must be a positive integer")
    return value


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be finite")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be finite")
    return number


def _positive_number(value: object, field: str) -> float:
    number = _number(value, field)
    if number <= 0:
        raise ValueError(f"{field} must be positive")
    return number


def _citation_identity(citation: Mapping[str, object]) -> tuple[str, int, str]:
    return (
        str(citation.get("revision_id", "")),
        _page_number(citation.get("page_number")),
        str(citation.get("source_hash", "")),
    )


def _verify_page_geometry(
    citation: Mapping[str, object],
    page_image: VerifiedPageImage,
) -> None:
    width = _positive_number(citation.get("page_width"), "citation.page_width")
    height = _positive_number(citation.get("page_height"), "citation.page_height")
    if (
        abs(width - page_image.pdf_width) > _GEOMETRY_TOLERANCE
        or abs(height - page_image.pdf_height) > _GEOMETRY_TOLERANCE
    ):
        raise ValueError(
            "PAGE_RENDER_GEOMETRY_MISMATCH: "
            f"citation={width}x{height} "
            f"page_image={page_image.pdf_width}x{page_image.pdf_height}"
        )
    expected = (
        ("page_origin_x", page_image.origin_x),
        ("page_origin_y", page_image.origin_y),
        ("page_rotation", page_image.rotation),
        ("page_box_kind", page_image.box_kind),
    )
    for field, value in expected:
        provided = citation.get(field)
        if provided is not None and provided != value:
            raise ValueError(f"PAGE_RENDER_GEOMETRY_MISMATCH: {field}")


def read_verified_page_image(
    page_root: Path,
    revision_id: str,
    page_number: int,
    source_hash: str,
) -> VerifiedPageImage:
    """Read one cached page image only after exact metadata/hash validation."""
    if not revision_id or "/" in revision_id or "\\" in revision_id or revision_id in {".", ".."}:
        raise ValueError("invalid revision_id")
    if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
        raise ValueError("invalid page_number")
    if (
        not isinstance(source_hash, str)
        or len(source_hash) != 64
        or any(character not in "0123456789abcdef" for character in source_hash)
    ):
        raise ValueError("invalid source_hash")

    stem = f"page-{page_number:04d}"
    try:
        image_path = verified_regular_file_below(
            page_root,
            (revision_id, f"{stem}.png"),
            field="page image",
        )
        metadata_path = verified_regular_file_below(
            page_root,
            (revision_id, f"{stem}.json"),
            field="page image metadata",
        )
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"verified page image missing: {revision_id} page {page_number}"
        ) from error

    try:
        document = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("page image metadata is invalid") from error
    metadata = _mapping(document, "page image metadata")
    required = {
        "format",
        "version",
        "revision_id",
        "page_number",
        "source_hash",
        "pdf_width",
        "pdf_height",
        "image_sha256",
    }
    optional = {"origin_x", "origin_y", "rotation", "box_kind"}
    if not required.issubset(metadata) or set(metadata) - required - optional:
        raise ValueError("page image metadata fields are invalid")
    if metadata["format"] not in {_PAGE_IMAGE_FORMAT, LEGACY_PAGE_IMAGE_FORMAT}:
        raise ValueError("unsupported page image metadata")
    if metadata["version"] != 1:
        raise ValueError("unsupported page image metadata")
    if metadata["revision_id"] != revision_id or metadata["page_number"] != page_number:
        raise ValueError("page image identity mismatch")
    if metadata["source_hash"] != source_hash:
        raise ValueError("page image source hash mismatch")
    image_sha256 = metadata["image_sha256"]
    if (
        not isinstance(image_sha256, str)
        or len(image_sha256) != 64
        or any(character not in "0123456789abcdef" for character in image_sha256)
    ):
        raise ValueError("page image hash is invalid")
    image_bytes = image_path.read_bytes()
    if hashlib.sha256(image_bytes).hexdigest() != image_sha256:
        raise ValueError("page image hash mismatch")

    pdf_width = _number(metadata["pdf_width"], "pdf_width")
    pdf_height = _number(metadata["pdf_height"], "pdf_height")
    if pdf_width <= 0 or pdf_height <= 0:
        raise ValueError("page image dimensions must be positive")
    origin_x = _number(metadata.get("origin_x", 0.0), "origin_x")
    origin_y = _number(metadata.get("origin_y", 0.0), "origin_y")
    rotation = metadata.get("rotation", 0)
    if (
        isinstance(rotation, bool)
        or not isinstance(rotation, int)
        or rotation not in {0, 90, 180, 270}
    ):
        raise ValueError("page image rotation is invalid")
    box_kind = metadata.get("box_kind", "MEDIA_BOX")
    if box_kind not in {"CROP_BOX", "MEDIA_BOX"}:
        raise ValueError("page image box kind is invalid")

    return VerifiedPageImage(
        revision_id=revision_id,
        page_number=page_number,
        source_hash=source_hash,
        image_path=image_path,
        image_sha256=image_sha256,
        image_bytes=image_bytes,
        pdf_width=pdf_width,
        pdf_height=pdf_height,
        origin_x=origin_x,
        origin_y=origin_y,
        rotation=rotation,
        box_kind=box_kind,
    )


def verify_review_page_images(
    view_model: Mapping[str, object],
    page_image_root: Path,
) -> Sequence[VerifiedPageImage]:
    """Verify each distinct cited page once and validate every citation geometry."""
    model = _mapping(view_model, "view_model")
    claims = _sequence(model.get("claims", []), "claims")
    verified_by_identity: dict[tuple[str, int, str], VerifiedPageImage] = {}
    ordered: list[VerifiedPageImage] = []

    for claim_index, claim_value in enumerate(claims):
        claim = _mapping(claim_value, f"claims[{claim_index}]")
        citations = _sequence(claim.get("citations", []), f"claims[{claim_index}].citations")
        for citation_index, citation_value in enumerate(citations):
            citation = _mapping(
                citation_value,
                f"claims[{claim_index}].citations[{citation_index}]",
            )
            identity = _citation_identity(citation)
            page_image = verified_by_identity.get(identity)
            if page_image is None:
                page_image = read_verified_page_image(
                    page_image_root,
                    identity[0],
                    identity[1],
                    identity[2],
                )
                verified_by_identity[identity] = page_image
                ordered.append(page_image)
            _verify_page_geometry(citation, page_image)

    return tuple(ordered)


__all__ = ["VerifiedPageImage", "read_verified_page_image", "verify_review_page_images"]
