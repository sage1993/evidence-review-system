"""Timed verification boundary for cached Review Workspace page images."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ansim_review.review_packet.html_renderer import _mapping, _page_assets, _sequence


def verify_review_page_images(
    view_model: Mapping[str, object],
    page_image_root: Path,
) -> None:
    """Verify every cited page image and citation geometry without rendering HTML."""
    model = _mapping(view_model, "view_model")
    claims = _sequence(model.get("claims", []), "claims")
    _page_assets(claims, page_image_root)


__all__ = ["verify_review_page_images"]
