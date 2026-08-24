"""Bounded local rendering coverage for the non-developer Review Workspace."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import struct
import tracemalloc
import zlib
from pathlib import Path
from time import perf_counter

from evidence_review.review_packet.html_renderer import render_review_html

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


def _visual_twenty_page_model(source_hashes: list[str]) -> dict[str, object]:
    base = _twenty_page_model(source_hashes)
    subject_uri = "data:image/png;base64," + base64.b64encode(b"subject-page").decode()
    candidates: list[dict[str, object]] = []
    anchors: list[dict[str, object]] = []
    for index, claim in enumerate(base["claims"]):
        claim_mapping = claim
        citation = claim_mapping["citations"][0]
        candidate_id = f"CAND-{index + 1:03d}"
        candidates.append(
            {
                "candidate_id": candidate_id,
                "page": 1,
                "candidate_type": "VISUAL_OBSERVATION",
                "geometry": {
                    "type": "BBOX",
                    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                    "coordinates": [
                        float(index % 10 * 50),
                        float(index // 10 * 70),
                        float(index % 10 * 50 + 30),
                        float(index // 10 * 70 + 30),
                    ],
                },
                "issue_ids": ["I1"],
                "claims": [
                    {
                        "claim_id": claim_mapping["claim_id"],
                        "citation_ids": [citation["citation_id"]],
                    }
                ],
                "review_statuses": [],
                "tone": "observation",
                "display_value": f"Subject region {index + 1}",
            }
        )
        page_number = int(citation["page_number"])
        anchors.append(
            {
                "anchor_id": citation["citation_id"],
                "type": "TEXT",
                "document_id": "DOC-PERFORMANCE",
                "revision_id": "REV-PERFORMANCE",
                "document_name": "performance-reference.pdf",
                "page": page_number,
                "page_asset_key": f"reference-page-{page_number}",
                "title": citation["title"],
                "quote": citation["quote"],
                "bbox": {
                    "coordinate_system": "PDF_BOTTOM_LEFT_POINTS",
                    "coordinates": citation["bbox"],
                },
                "table": None,
                "visual": None,
            }
        )
    reference_pages = [
        {
            "asset_key": f"reference-page-{page_number}",
            "document_id": "DOC-PERFORMANCE",
            "revision_id": "REV-PERFORMANCE",
            "page": page_number,
            "source_hash": source_hashes[page_number - 1],
            "width": 600.0,
            "height": 800.0,
            "rotation": 0,
            "data_uri": "data:image/png;base64,"
            + base64.b64encode(VALID_MINIMAL_PNG + bytes([page_number])).decode(),
        }
        for page_number in range(1, PAGE_COUNT + 1)
    ]
    base["case_visual_review"] = {
        "status": "VISUAL_ANALYSIS_VALIDATED",
        "attachment_count": 1,
        "candidate_count": CITATION_COUNT,
        "pages": [
            {
                "asset_key": "ATT-SUBJECT-p1",
                "attachment_id": "ATT-SUBJECT",
                "document_name": "subject.pdf",
                "page": 1,
                "width": 600.0,
                "height": 800.0,
                "data_uri": subject_uri,
                "candidates": candidates,
            }
        ],
        "reference_documents": [
            {
                "document_id": "DOC-PERFORMANCE",
                "revision_id": "REV-PERFORMANCE",
                "document_name": "performance-reference.pdf",
                "page_count": PAGE_COUNT,
                "page_asset_keys": [page["asset_key"] for page in reference_pages],
            }
        ],
        "reference_pages": reference_pages,
        "findings": [
            {
                "finding_id": candidate["candidate_id"],
                "reference_anchors": [anchor],
                "subject_region": {
                    "page_asset_key": "ATT-SUBJECT-p1",
                    "attachment_id": "ATT-SUBJECT",
                    "page": 1,
                    "geometry": candidate["geometry"],
                },
            }
            for candidate, anchor in zip(candidates, anchors, strict=True)
        ],
    }
    return base


def test_visual_workspace_renders_twenty_reference_pages_and_one_subject_once(
    tmp_path: Path,
) -> None:
    source_hashes = _write_shared_page_assets(tmp_path / "pages")
    model = _visual_twenty_page_model(source_hashes)

    tracemalloc.start()
    started = perf_counter()
    html = render_review_html(model, tmp_path / "pages")
    elapsed = perf_counter() - started
    _current, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(html.encode("utf-8")) < 2_000_000
    assert peak_memory < 128 * 1024 * 1024
    assert html.count('data-reference-page="reference-page-') == PAGE_COUNT
    assert html.count('data-page-image-source="reference-page-') == PAGE_COUNT
    assert html.count("data:image/png;base64,") == PAGE_COUNT + 1
    assert 'id="evidence-viewer"' not in html
    assert elapsed <= LOCAL_RENDER_BUDGET_SECONDS

    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    assert all("data_uri" not in page for page in visual["reference_pages"])
    assert "data_uri" not in visual["pages"][0]
