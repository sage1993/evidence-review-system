"""Small inline SVG icon set used by the self-contained review workspace."""

from html import escape

_PATHS = {
    "check": '<path d="M20 6 9 17l-5-5" />',
    "chevron-down": '<path d="m6 9 6 6 6-6" />',
    "chevron-left": '<path d="m15 18-6-6 6-6" />',
    "chevron-right": '<path d="m9 18 6-6-6-6" />',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" />',  # noqa: E501
    "file-text": '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z" /><path d="M14 2v5a1 1 0 0 0 1 1h5" /><path d="M10 9H8M16 13H8M16 17H8" />',  # noqa: E501
    "info": '<circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" />',
    "lock": '<rect width="18" height="11" x="3" y="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />',  # noqa: E501
    "maximize": '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3" />',  # noqa: E501
    "minus": '<path d="M5 12h14" />',
    "plus": '<path d="M5 12h14M12 5v14" />',
    "printer": '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6" /><rect x="6" y="14" width="12" height="8" rx="1" />',  # noqa: E501
    "search": '<path d="m21 21-4.34-4.34" /><circle cx="11" cy="11" r="8" />',
}


def icon_svg(name: str, *, size: int = 16, label: str | None = None) -> str:
    """Return a crisp, currentColor inline SVG from the shared icon set."""
    try:
        paths = _PATHS[name]
    except KeyError as error:
        raise ValueError(f"unsupported icon: {name}") from error
    aria = (
        f' role="img" aria-label="{escape(label, quote=True)}"'
        if label
        else ' aria-hidden="true"'
    )
    return (
        f'<svg class="icon icon-{escape(name, quote=True)}" '
        f'width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round"{aria}>'
        f"{paths}</svg>"
    )


__all__ = ["icon_svg"]
