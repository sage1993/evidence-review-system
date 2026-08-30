"""Shared Review Workspace shell for reference-only and visual review modes."""

from __future__ import annotations

from collections.abc import Mapping
from html import escape


def workspace_mode(model: Mapping[str, object]) -> str:
    """Return the presentation mode without changing packet authority."""
    return "reference-subject" if model.get("case_visual_review") is not None else "reference-only"


def render_workspace(model: Mapping[str, object], content: str) -> str:
    """Wrap one review projection in the shared workspace shell."""
    mode = escape(workspace_mode(model), quote=True)
    return (
        '<main class="review-workspace" data-review-workspace="unified" '
        f'data-review-workspace-mode="{mode}">{content}</main>'
    )


__all__ = ["render_workspace", "workspace_mode"]
