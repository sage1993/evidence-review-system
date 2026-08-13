"""Bounded local rendering coverage for the non-developer Review Workspace."""
from __future__ import annotations

import hashlib
import json
import re
import struct
import zlib
from pathlib import Path
from time import perf_counter

from ansim_review.review_packet.html_renderer import render_review_html

PAGE_COUNT = 20
CITATION_COUNT = 100
LOCAL_RENDER_BUDGET_SECONDS = 5.0
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


VALID_MINIMAL_PNG = (
    _PNG_SIGNATURE
    + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    + _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\xff"))
    + _png_chunk(b"IEND", b"")
)


def _write_shared_page_assets(root: Path) -> list[str]:
    revision_id = "REV-PERFORMANCE"
    source_hash = hashlib.sha256(b"source-revision-performance").hexdigest()
    directory = root / revision_id
    directory.mkdir(parents=True)
    source_hashes: list[str] = []
    for page_number in range(1, PAGE_COUNT + 1):
        source_hashes.append(source_hash)
        image_bytes = VALID_MINIMAL_PNG
        (directory / f"page-{page_number:04d}.png").write_bytes(image_bytes)
        (directory / f"page-{page_number:04d}.json").write_text(
            json.dumps(
                {
                    "format": "ansim/page-image",
                    "version": 1,
                    "revision_id": revision_id,
                    "page_number": page_number,
                    "source_hash": source_hash,
                    "pdf_width": 600.0,
                    "pdf_height": 800.0,
                    "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
    return source_hashes


def _twenty_page_model(source_hashes: list[str]) -> dict[str, object]:
    claims: list[dict[str, object]] = []
    review_items: list[dict[str, object]] = []
    for index in range(CITATION_COUNT):
        number = index + 1
        page_number = index % PAGE_COUNT + 1
        claims.append(
            {
                "claim_id": f"CLAIM-{number:03d}",
                "text": f"Traceable claim {number}",
                "numeric_tokens": [],
                "citations": [
                    {
                        "citation_id": f"CIT-E{number:03d}",
                        "document_id": "DOC-PERFORMANCE",
                        "revision_id": "REV-PERFORMANCE",
                        "page_number": page_number,
                        "evidence_id": f"E{number:03d}",
                        "bbox": [10.0, 20.0, 110.0, 40.0],
                        "source_hash": source_hashes[page_number - 1],
                        "title": f"Page {page_number} evidence",
                        "quote": f"Verified citation {number}",
                        "evidence_type": "clause",
                        "page_width": 600.0,
                        "page_height": 800.0,
                    }
                ],
            }
        )
        review_items.append(
            {
                "item_id": f"ITEM-{number:03d}",
                "claim_id": f"CLAIM-{number:03d}",
                "status": "INDETERMINATE",
                "completeness": "COMPLETE",
            }
        )
    return {
        "run_id": "RUN-PERFORMANCE-0001",
        "status": "READY_FOR_HUMAN_REVIEW",
        "display_status": "READY_FOR_HUMAN_REVIEW",
        "question": "Review the supplied evidence.",
        "claims": claims,
        "review_items": review_items,
        "calculations": [],
        "rules": [],
        "summary": {
            "citation_count": CITATION_COUNT,
            "missing_input_count": 0,
            "exception_count": 0,
            "conflict_count": 0,
        },
        "audit": {"uncited_count": 0},
        "exceptions": [],
        "conflicts": [],
        "abstention_reasons": [],
        "decision": {
            "human_decision": None,
            "allowed_values": ["SATISFIED", "NOT_SATISFIED"],
            "packet_sha256": "a" * 64,
        },
    }


def _decision_form(html: str) -> str:
    match = re.search(r'<section id="decision-form".*?</section>', html, re.DOTALL)
    assert match is not None
    return match.group(0)


def test_large_workspace_renders_shared_pages_once_within_local_budget(tmp_path: Path) -> None:
    source_hashes = _write_shared_page_assets(tmp_path / "pages")
    model = _twenty_page_model(source_hashes)

    started = perf_counter()
    html = render_review_html(model, tmp_path / "pages")
    elapsed = perf_counter() - started

    assert html.count("data:image/png;base64,") == PAGE_COUNT
    for number in range(1, CITATION_COUNT + 1):
        assert f'data-item-id="ITEM-{number:03d}"' in html
    assert elapsed <= LOCAL_RENDER_BUDGET_SECONDS


def test_ready_state_is_korean_and_has_no_empty_additional_panel(tmp_path: Path) -> None:
    model = _twenty_page_model(_write_shared_page_assets(tmp_path / "pages"))

    html = render_review_html(model, tmp_path / "pages")

    assert "검토 준비 완료" in html
    assert 'id="additional-review"' not in html
    assert 'value="SATISFIED" required' in html
    assert 'value="NOT_SATISFIED" required' in html
    assert " checked" not in _decision_form(html)


def test_abstain_state_surfaces_additional_review_without_selecting_decision(
    tmp_path: Path,
) -> None:
    model = _twenty_page_model(_write_shared_page_assets(tmp_path / "pages"))
    model["status"] = "ABSTAIN"
    model["display_status"] = "ABSTAIN"
    model["abstention_reasons"] = ["MISSING_REQUIRED_EVIDENCE"]

    html = render_review_html(model, tmp_path / "pages")

    assert "추가 자료 필요" in html
    assert 'id="additional-review"' in html
    assert "MISSING REQUIRED EVIDENCE" in html
    assert " checked" not in _decision_form(html)
