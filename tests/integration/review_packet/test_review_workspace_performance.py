"""Bounded local readiness coverage for the offline Review Workspace."""

from __future__ import annotations

import hashlib
import json
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


def _assert_valid_minimal_png(image_bytes: bytes) -> None:
    assert image_bytes.startswith(_PNG_SIGNATURE)
    offset = len(_PNG_SIGNATURE)
    chunk_types: list[bytes] = []
    idat = bytearray()
    ihdr = b""
    while offset < len(image_bytes):
        length = struct.unpack(">I", image_bytes[offset : offset + 4])[0]
        chunk_type = image_bytes[offset + 4 : offset + 8]
        payload_start = offset + 8
        payload_end = payload_start + length
        payload = image_bytes[payload_start:payload_end]
        stored_crc = struct.unpack(">I", image_bytes[payload_end : payload_end + 4])[0]
        assert len(payload) == length
        assert stored_crc == zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
        chunk_types.append(chunk_type)
        if chunk_type == b"IHDR":
            ihdr = payload
        if chunk_type == b"IDAT":
            idat.extend(payload)
        offset = payload_end + 4
    assert offset == len(image_bytes)
    assert chunk_types == [b"IHDR", b"IDAT", b"IEND"]
    assert struct.unpack(">IIBBBBB", ihdr) == (1, 1, 8, 6, 0, 0, 0)
    assert zlib.decompress(idat) == b"\x00\x00\x00\x00\xff"


def test_valid_minimal_png_has_verified_chunks_and_decompressible_idat() -> None:
    _assert_valid_minimal_png(VALID_MINIMAL_PNG)


def _write_shared_page_assets(root: Path) -> list[str]:
    """Create twenty verified pages reused by the hundred citations below."""
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
        item_id = f"ITEM-{number:03d}"
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
                    }
                ],
            }
        )
        review_items.append(
            {
                "item_id": item_id,
                "claim_id": f"CLAIM-{number:03d}",
                "status": "NOT_EVALUATED",
                "completeness": "COMPLETE",
            }
        )
    return {
        "run_id": "RUN-PERFORMANCE-0001",
        "status": "READY_FOR_HUMAN_REVIEW",
        "human_decision": None,
        "question": "Review the supplied evidence.",
        "claims": claims,
        "review_items": review_items,
        "calculations": [],
        "rules": [],
        "summary": {"citation_count": CITATION_COUNT},
        "audit": {"uncited_count": 0},
        "abstention_reasons": [],
        "decision": {
            "human_decision": None,
            "allowed_values": ["SATISFIED", "NOT_SATISFIED"],
            "packet_sha256": "a" * 64,
        },
    }


def test_review_workspace_renders_twenty_shared_pages_and_one_hundred_items_within_budget(
    tmp_path: Path,
) -> None:
    source_hashes = _write_shared_page_assets(tmp_path / "pages")
    model = _twenty_page_model(source_hashes)

    started = perf_counter()
    html = render_review_html(model, tmp_path / "pages")
    elapsed = perf_counter() - started

    assert source_hashes == [source_hashes[0]] * PAGE_COUNT
    for page_number in range(1, PAGE_COUNT + 1):
        directory = tmp_path / "pages" / "REV-PERFORMANCE"
        image_bytes = (directory / f"page-{page_number:04d}.png").read_bytes()
        metadata = json.loads((directory / f"page-{page_number:04d}.json").read_text())
        assert image_bytes == VALID_MINIMAL_PNG
        assert metadata["image_sha256"] == hashlib.sha256(image_bytes).hexdigest()
        assert metadata["source_hash"] == source_hashes[0]
    assert html.count("data:image/png;base64,") == PAGE_COUNT
    for number in range(1, CITATION_COUNT + 1):
        assert f'data-item-id="ITEM-{number:03d}"' in html
    assert elapsed <= LOCAL_RENDER_BUDGET_SECONDS


def test_review_workspace_shows_ready_state_without_a_selected_decision(
    tmp_path: Path,
) -> None:
    source_hashes = _write_shared_page_assets(tmp_path / "pages")
    model = _twenty_page_model(source_hashes)

    html = render_review_html(model, tmp_path / "pages")

    assert "READY_FOR_HUMAN_REVIEW" in html
    assert "None recorded." in html
    assert '<option value="" selected disabled>Select a decision</option>' in html
    assert '<option value="SATISFIED" selected>' not in html
    assert '<option value="NOT_SATISFIED" selected>' not in html


def test_review_workspace_shows_abstain_reasons_without_a_selected_decision(
    tmp_path: Path,
) -> None:
    source_hashes = _write_shared_page_assets(tmp_path / "pages")
    model = _twenty_page_model(source_hashes)
    model["status"] = "ABSTAIN"
    model["abstention_reasons"] = ["MISSING_REQUIRED_EVIDENCE"]

    html = render_review_html(model, tmp_path / "pages")

    assert "ABSTAIN" in html
    assert "MISSING_REQUIRED_EVIDENCE" in html
    assert '<option value="" selected disabled>Select a decision</option>' in html
    assert '<option value="SATISFIED" selected>' not in html
    assert '<option value="NOT_SATISFIED" selected>' not in html
