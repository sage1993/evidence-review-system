from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from evidence_review.review_packet.html_renderer import render_review_html


def _page_asset(
    root: Path,
    *,
    revision_id: str,
    page_number: int,
    source_hash: str,
) -> None:
    directory = root / revision_id
    directory.mkdir(parents=True, exist_ok=True)
    image = directory / f"page-{page_number:04d}.png"
    image_bytes = b"\x89PNG\r\n\x1a\n" + f"{revision_id}:{page_number}".encode()
    image.write_bytes(image_bytes)
    (directory / f"page-{page_number:04d}.json").write_text(
        json.dumps(
            {
                "format": "evidence-review/page-image",
                "version": 1,
                "revision_id": revision_id,
                "page_number": page_number,
                "source_hash": source_hash,
                "pdf_width": 100.0,
                "pdf_height": 200.0,
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


def _citation(
    *,
    citation_id: str,
    evidence_id: str,
    document_id: str,
    document_name: str,
    revision_id: str,
    page_number: int,
    source_hash: str,
) -> dict[str, object]:
    return {
        "citation_id": citation_id,
        "evidence_id": evidence_id,
        "document_id": document_id,
        "document_name": document_name,
        "revision_id": revision_id,
        "page_number": page_number,
        "source_hash": source_hash,
        "title": f"원문 p.{page_number}",
        "quote": f"{document_name} 인용",
        "evidence_type": "clause",
        "bbox": [10.0, 20.0, 50.0, 40.0],
        "page_width": 100.0,
        "page_height": 200.0,
    }


def _model() -> dict[str, object]:
    citation_a = _citation(
        citation_id="CIT-A",
        evidence_id="E-A",
        document_id="DOC-A",
        document_name="A.pdf",
        revision_id="REV-A",
        page_number=3,
        source_hash="a" * 64,
    )
    citation_b = _citation(
        citation_id="CIT-B",
        evidence_id="E-B",
        document_id="DOC-B",
        document_name="B.pdf",
        revision_id="REV-B",
        page_number=17,
        source_hash="b" * 64,
    )
    return {
        "run_id": "RUN-MULTI",
        "status": "READY_FOR_HUMAN_REVIEW",
        "display_status": "READY_FOR_HUMAN_REVIEW",
        "question": "두 문서 근거 검토",
        "claims": [
            {"claim_id": "C-A", "text": "A 주장", "citations": [citation_a]},
            {"claim_id": "C-B", "text": "B 주장", "citations": [citation_b]},
        ],
        "review_items": [
            {"item_id": "ITEM-A", "claim_id": "C-A", "status": "INDETERMINATE"},
            {"item_id": "ITEM-B", "claim_id": "C-B", "status": "INDETERMINATE"},
        ],
        "calculations": [],
        "rules": [],
        "exceptions": [],
        "conflicts": [],
        "abstention_reasons": [],
        "decision": {"packet_sha256": "c" * 64, "human_decision": None},
        "metadata": {"run_id": "RUN-MULTI"},
        "summary": {},
        "audit": {},
    }


def test_multi_document_viewer_keeps_source_and_page_position_separate(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    _page_asset(
        pages,
        revision_id="REV-A",
        page_number=3,
        source_hash="a" * 64,
    )
    _page_asset(
        pages,
        revision_id="REV-B",
        page_number=17,
        source_hash="b" * 64,
    )

    html = render_review_html(_model(), pages)

    assert '<select data-source-select' in html
    assert 'value="source-1"' in html and ">A.pdf</option>" in html
    assert 'value="source-2"' in html and ">B.pdf</option>" in html
    assert 'data-source-id="source-1"' in html
    assert 'data-source-id="source-2"' in html
    assert 'data-original-page="3"' in html
    assert 'data-original-page="17"' in html
    assert 'data-source-position="1"' in html
    assert 'data-source-count="1"' in html
    assert "근거 페이지 <strong data-current-source-position>1</strong> / " in html
    assert "원문 p.<strong data-current-original-page>3</strong>" in html
    assert re.search(r">\s*3\s*/\s*17\s*<", html) is None


def test_viewer_controls_are_real_and_source_neutral(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    _page_asset(
        pages,
        revision_id="REV-A",
        page_number=3,
        source_hash="a" * 64,
    )
    _page_asset(
        pages,
        revision_id="REV-B",
        page_number=17,
        source_hash="b" * 64,
    )

    html = render_review_html(_model(), pages)

    assert 'data-viewer-mode="original"' in html
    assert 'data-viewer-mode="evidence"' in html
    assert 'data-viewer-mode="compare"' in html
    assert "※ PDF 문서는 정부 기관의 원본을 제공합니다." not in html
    assert "검토에 사용된 원본 문서의 검증된 페이지 이미지를 표시합니다." in html
    assert 'class="evidence-sort"' not in html
    assert "문서별 · 관련도순" in html
