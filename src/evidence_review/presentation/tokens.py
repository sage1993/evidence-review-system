"""Presentation-only tokens with no data, route, or state authority."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

PresentationToken = int | str

_TOKENS: Mapping[str, PresentationToken] = MappingProxyType(
    {
        "font_family": '"Segoe UI", "Noto Sans KR", "Malgun Gothic", sans-serif',
        "font_size_px": 16,
        "line_height": "1.55",
        "control_height_px": 44,
        "control_radius_px": 8,
        "focus_outline_px": 3,
    }
)


def presentation_tokens() -> Mapping[str, PresentationToken]:
    """Return immutable typography and control dimensions shared by review UIs."""
    return _TOKENS


def presentation_css_variables() -> str:
    """Project the immutable tokens as deterministic CSS custom properties."""
    tokens = presentation_tokens()
    return "\n".join(
        (
            ":root {",
            f"  --ers-font-family: {tokens['font_family']};",
            f"  --ers-font-size: {tokens['font_size_px']}px;",
            f"  --ers-line-height: {tokens['line_height']};",
            f"  --ers-control-height: {tokens['control_height_px']}px;",
            f"  --ers-control-radius: {tokens['control_radius_px']}px;",
            f"  --ers-focus-outline: {tokens['focus_outline_px']}px;",
            "}",
        )
    )


__all__ = ["PresentationToken", "presentation_css_variables", "presentation_tokens"]
