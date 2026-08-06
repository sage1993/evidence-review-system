"""Bounded local readiness coverage for the offline Review Workspace."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from time import perf_counter

from ansim_review.review_packet.html_renderer import render_review_html

PAGE_COUNT = 20
CITATION_COUNT = 100
LOCAL_RENDER_BUDGET_SECONDS = 5.0
VALID_MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLk0QAAAABJRU5ErkJggg=="
)


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
