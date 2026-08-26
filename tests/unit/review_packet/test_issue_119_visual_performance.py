import hashlib
from pathlib import Path

from evidence_review.review_packet.case_visual_projection import (
    _resolve_visual_raster_path,
)
from evidence_review.review_packet.render_case_visual import render_case_visual_review


def test_projection_prefers_hash_matched_high_resolution_case_pdf_cache(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    attachment_id = "ATT-VISUAL-1"
    hq = (
        workspace
        / "case-page-images-hq-v1"
        / attachment_id
        / "page-0001.png"
    )
    normal = workspace / "case-page-images" / attachment_id / "page-0001.png"
    hq.parent.mkdir(parents=True, exist_ok=True)
    normal.parent.mkdir(parents=True, exist_ok=True)
    hq.write_bytes(b"high-resolution-page")
    normal.write_bytes(b"stale-normal-page")
    expected = hashlib.sha256(hq.read_bytes()).hexdigest()

    assert _resolve_visual_raster_path(workspace, attachment_id, 1, expected) == hq


def test_renderer_defers_large_page_tile_decode_until_viewport_use() -> None:
    tile_uri = "data:image/png;base64,dGlsZQ=="
    model: dict[str, object] = {
        "claims": [],
        "case_visual_review": {
            "status": "VISUAL_ANALYSIS_VALIDATED",
            "attachment_count": 1,
            "candidate_count": 1,
            "pages": [
                {
                    "asset_key": "ATT-1-p1",
                    "attachment_id": "ATT-1",
                    "document_name": "대형도면.pdf",
                    "source_sha256": "a" * 64,
                    "page": 1,
                    "width": 5000.0,
                    "height": 4200.0,
                    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                    "image_sha256": "b" * 64,
                    "tiles": [
                        {
                            "x": 0,
                            "y": 0,
                            "width": 2048,
                            "height": 2048,
                            "image_sha256": "c" * 64,
                            "data_uri": tile_uri,
                        }
                    ],
                    "candidates": [
                        {
                            "candidate_id": "CAND-1",
                            "source_sha256": "a" * 64,
                            "page": 1,
                            "candidate_type": "DIMENSION",
                            "origin": "EXTRACTOR",
                            "status": "UNCONFIRMED",
                            "geometry": {
                                "type": "BBOX",
                                "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                                "coordinates": [100.0, 100.0, 500.0, 300.0],
                            },
                            "raw_value": "2.4m",
                            "normalized_candidate": "2.4m",
                            "extractor": "codex-vision",
                            "extractor_version": "1",
                            "annotation_id": None,
                            "issue_ids": ["I1"],
                            "issue_questions": [],
                            "claims": [],
                            "review_statuses": [],
                            "tone": "observation",
                            "display_value": "2.4m",
                        }
                    ],
                }
            ],
            "findings": [
                {
                    "finding_id": "VF-1",
                    "title": "주요 치수·거리",
                    "category": "dimension",
                    "status": "not_comparable",
                    "page_asset_key": "ATT-1-p1",
                    "candidate_ids": ["CAND-1"],
                    "issue_ids": ["I1"],
                    "subject_value": "2.4m",
                    "focus_bbox": [100.0, 100.0, 500.0, 300.0],
                    "direct_claim_ids": [],
                    "related_claim_ids": [],
                }
            ],
        },
    }

    html = render_case_visual_review(model)

    assert f'data-case-tile-src="{tile_uri}"' in html
    assert f'href="{tile_uri}"' not in html
    assert "ensureVisibleTiles" in html
    assert "requestAnimationFrame" in html
