"""Read-only presentation of preserved parser text; no inferred table semantics."""
from __future__ import annotations

import re
from html import escape


def render_quote(quote: str) -> str:
    """Show explicitly recorded row/column values, retaining the exact raw text."""
    parts = quote.split(" | ")
    cells = [re.fullmatch(r"행 (\d+) 열 (\d+):\s*(.*)", part, re.DOTALL) for part in parts]
    if len(cells) > 1 and all(cells):
        rows = "".join(
            f"<tr><td>{cell[1]}</td><td>{cell[2]}</td><td>{escape(cell[3])}</td></tr>"
            for cell in cells if cell is not None
        )
        return (
            '<div class="extracted-table-scroll"><table class="extracted-table">'
            '<caption>원문 표의 추출 셀 · 행과 열 번호는 원문 위치입니다</caption>'
            '<thead><tr><th>행</th><th>열</th><th>내용</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
            f'<details class="raw-quote"><summary>원시 추출문 보기</summary>'
            f'<blockquote>{escape(quote)}</blockquote></details>'
        )
    return f'<blockquote>{escape(quote)}</blockquote>'
