import hashlib
import json
from pathlib import Path

import pytest

from evidence_review.review_packet.case_visual_projection import build_case_visual_projection


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _fixture(tmp_path: Path, *, coordinates: list[float] | None = None) -> tuple[dict[str, object], Path]:
    workspace = tmp_path / "workspace"
    run_id = "RUN-1234567890ABCDEF1234"
    run_dir = workspace / "runs" / run_id
    attachment_id = "ATT-VISUAL-1"
    source_hash = "a" * 64
    image_bytes = b"verified-raster-bytes"
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    image_path = workspace / "case-page-images" / attachment_id / "page-0001.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(image_bytes)

    candidate = {
        "candidate_id": "CAND-VISUAL-1",
        "source_sha256": source_hash,
        "page": 1,
        "candidate_type": "VISUAL_OBSERVATION",
        "origin": "EXTRACTOR",
        "status": "UNCONFIRMED",
        "geometry": {
            "type": "BBOX",
            "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
            "coordinates": coordinates or [10, 20, 80, 90],
        },
        "raw_value": "차량 출입구 위치",
        "normalized_candidate": None,
        "extractor": "codex-vision",
        "extractor_version": "1.0.0",
        "annotation_id": None,
    }
    context = {
        "attachments": [
            {
                "attachment_id": attachment_id,
                "original_name": "배치-test.pdf",
                "stored_path": f"inputs/original/{attachment_id}.pdf",
                "sha256": source_hash,
                "byte_size": 100,
                "mime": "application/pdf",
                "role": "CASE_DRAWING",
            }
        ],
        "drawing_candidates": [candidate],
        "visual_status": "VISUAL_ANALYSIS_VALIDATED",
        "reason_codes": [],
        "visual_pages": [
            {
                "attachment_id": attachment_id,
                "source_sha256": source_hash,
                "page": 1,
                "width": 100.0,
                "height": 120.0,
                "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                "image_sha256": image_hash,
            }
        ],
        "candidate_lineage": [
            {"candidate_id": "CAND-VISUAL-1", "issue_ids": ["I1"]}
        ],
    }
    _write_json(
        run_dir / "track-a-bundle.json",
        {
            "inputs": {
                "question_plan": {
                    "issues": [{"id": "I1", "question": "차량 출입구 기준을 충족하는가"}]
                },
                "case_visual_context": context,
            }
        },
    )
    _write_json(
        run_dir / "track-a-output.json",
        {
            "claims": [
                {
                    "claim_id": "CL-I1-1",
                    "text": "차량 출입구 위치는 해당 기준과 함께 검토해야 한다.",
                    "issue_ids": ["I1"],
                    "citation_ids": ["CIT-RULE-1"],
                    "drawing_candidate_ids": ["CAND-VISUAL-1"],
                }
            ]
        },
    )
    view_model: dict[str, object] = {
        "run_id": run_id,
        "review_items": [
            {"claim_id": "CL-I1-1", "status": "NOT_SATISFIED"}
        ],
    }
    return view_model, workspace


def test_projection_embeds_verified_case_raster_and_candidate(tmp_path: Path) -> None:
    view_model, workspace = _fixture(tmp_path)

    result = build_case_visual_projection(view_model, workspace_root=workspace)

    assert result is not None
    assert result["candidate_count"] == 1
    page = result["pages"][0]
    assert page["document_name"] == "배치-test.pdf"
    assert str(page["data_uri"]).startswith("data:image/png;base64,")
    candidate = page["candidates"][0]
    assert candidate["candidate_id"] == "CAND-VISUAL-1"
    assert candidate["tone"] == "issue"
    assert candidate["issue_ids"] == ["I1"]
    assert candidate["claims"][0]["citation_ids"] == ["CIT-RULE-1"]


def test_projection_fails_closed_when_raster_hash_changes(tmp_path: Path) -> None:
    view_model, workspace = _fixture(tmp_path)
    raster = workspace / "case-page-images" / "ATT-VISUAL-1" / "page-0001.png"
    raster.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="case visual raster hash mismatch"):
        build_case_visual_projection(view_model, workspace_root=workspace)


def test_projection_rejects_geometry_outside_verified_page(tmp_path: Path) -> None:
    view_model, workspace = _fixture(tmp_path, coordinates=[10, 20, 130, 90])

    with pytest.raises(ValueError, match="outside the verified raster page"):
        build_case_visual_projection(view_model, workspace_root=workspace)


def test_projection_is_absent_for_non_visual_review(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    run_id = "RUN-1234567890ABCDEF1234"
    _write_json(workspace / "runs" / run_id / "track-a-bundle.json", {"inputs": {}})

    assert build_case_visual_projection(
        {"run_id": run_id, "review_items": []}, workspace_root=workspace
    ) is None
