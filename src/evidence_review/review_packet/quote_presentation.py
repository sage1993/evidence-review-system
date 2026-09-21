"""Read-only presentation of preserved parser text; no inferred table semantics."""
from __future__ import annotations

import re
from html import escape

_PARSER_CELL_DUMP = re.compile(r"행 \d+ 열 \d+:\s*.*", re.DOTALL)


def _is_parser_cell_dump(quote: str) -> bool:
    return bool(_PARSER_CELL_DUMP.match(quote))


def quote_preview(quote: str) -> str:
    """Return reviewer-facing preview text without leaking parser coordinates."""
    if _is_parser_cell_dump(quote):
        return "원문 표의 강조 위치를 확인하세요."
    return quote


def render_quote(quote: str) -> str:
    """Present source text without turning parser coordinates into reviewer content."""
    if _is_parser_cell_dump(quote):
        return '<p class="reference-location-hint">원문에서 강조된 표 위치를 확인하세요.</p>'
    return f'<blockquote>{escape(quote)}</blockquote>'
