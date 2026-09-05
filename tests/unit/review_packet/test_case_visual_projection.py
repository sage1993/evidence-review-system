import hashlib
import json
from pathlib import Path

import pytest

from evidence_review.review_packet.case_visual_projection import (
    build_case_visual_projection,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _fixture(
    tmp_path: Path,
    *,
    coordinates: list[float] | None = None,
    with_rule: bool = True,
) -> tuple[dict[str, object], Path]:
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
    reference_image_bytes = b"verified-reference-page"
    reference_image_path = (
        workspace / "page-images" / "REV-RULE-1" / "page-0001.png"
    )
    reference_image_path.parent.mkdir(parents=True, exist_ok=True)
    reference_image_path.write_bytes(reference_image_bytes)
    _write_json(
        reference_image_path.with_suffix(".json"),
        {
            "format": "evidence-review/page-image",
            "version": 1,
            "revision_id": "REV-RULE-1",
            "page_number": 1,
            "source_hash": "d" * 64,
            "pdf_width": 120.0,
            "pdf_height": 200.0,
            "origin_x": 0.0,
            "origin_y": 0.0,
            "rotation": 0,
            "box_kind": "MEDIA_BOX",
            "image_sha256": hashlib.sha256(reference_image_bytes).hexdigest(),
        },
    )

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
                    "issues": [
                        {
                            "id": "I1",
                            "question": "차량 출입구 기준을 충족하는가",
                        }
                    ]
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
    review_item: dict[str, object] = {
        "claim_id": "CL-I1-1",
        "status": "NOT_SATISFIED" if with_rule else "INDETERMINATE",
        "rule_ids": ["RULE-1"] if with_rule else [],
    }
    view_model: dict[str, object] = {
        "run_id": run_id,
        "claims": [
            {
                "claim_id": "CL-I1-1",
                "citations": [{"citation_id": "CIT-RULE-1"}],
            }
        ],
        "reference_citations": [
            {
                "citation_id": "CIT-RULE-1",
                "evidence_id": "E-RULE-1",
                "document_id": "REF-RULE-1",
                "revision_id": "REV-RULE-1",
                "page_number": 1,
                "bbox": [10.0, 20.0, 80.0, 90.0],
                "source_hash": "d" * 64,
                "document_name": "rules.pdf",
                "document_page_count": 3,
                "page_width": 120.0,
                "page_height": 200.0,
                "page_origin_x": 0.0,
                "page_origin_y": 0.0,
                "page_rotation": 0,
                "page_box_kind": "MEDIA_BOX",
                "title": "Direct rule",
                "quote": "Direct rule quote",
                "reference": {
                    "type": "TEXT",
                    "table": None,
                    "visual": None,
                },
            }
        ],
        "review_items": [review_item],
    }
    return view_model, workspace


def test_projection_embeds_verified_case_raster_and_candidate(
    tmp_path: Path,
) -> None:
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
    finding = result["findings"][0]
    assert finding["direct_reference_anchors"][0]["reference_role"] == "direct"
    assert finding["direct_reference_anchors"][0]["anchor_id"] == "CIT-RULE-1"
    assert finding["related_reference_anchors"] == []
    assert result["reference_pages"][0]["asset_key"] == "reference-page-1"


def test_projection_keeps_ruleless_visual_observation_blue(tmp_path: Path) -> None:
    view_model, workspace = _fixture(tmp_path, with_rule=False)

    result = build_case_visual_projection(view_model, workspace_root=workspace)

    assert result is not None
    candidate = result["pages"][0]["candidates"][0]
    assert candidate["review_statuses"] == []
    assert candidate["tone"] == "observation"


def test_projection_fails_closed_when_raster_hash_changes(
    tmp_path: Path,
) -> None:
    view_model, workspace = _fixture(tmp_path)
    raster = workspace / "case-page-images" / "ATT-VISUAL-1" / "page-0001.png"
    raster.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="case visual raster hash mismatch"):
        build_case_visual_projection(view_model, workspace_root=workspace)


def test_projection_rejects_geometry_outside_verified_page(
    tmp_path: Path,
) -> None:
    view_model, workspace = _fixture(tmp_path, coordinates=[10, 20, 130, 90])

    with pytest.raises(ValueError, match="outside the verified raster page"):
        build_case_visual_projection(view_model, workspace_root=workspace)


def test_projection_is_absent_for_non_visual_review(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    run_id = "RUN-1234567890ABCDEF1234"
    _write_json(
        workspace / "runs" / run_id / "track-a-bundle.json",
        {"inputs": {}},
    )

    assert (
        build_case_visual_projection(
            {"run_id": run_id, "review_items": []},
            workspace_root=workspace,
        )
        is None
    )

def test_projection_uses_empty_reference_projection_for_legacy_view_model(
    tmp_path: Path,
) -> None:
    view_model, workspace = _fixture(tmp_path)
    view_model.pop("reference_citations")

    result = build_case_visual_projection(view_model, workspace_root=workspace)

    assert result is not None
    finding = result["findings"][0]
    assert finding["direct_reference_anchors"] == []
    assert finding["related_reference_anchors"] == []
    assert result["reference_documents"] == []
    assert result["reference_pages"] == []

def test_projection_rejects_case_raster_symlink_escape(tmp_path: Path) -> None:
    view_model, workspace = _fixture(tmp_path)
    raster = workspace / "case-page-images" / "ATT-VISUAL-1" / "page-0001.png"
    outside = tmp_path / "outside.png"
    outside.write_bytes(raster.read_bytes())
    raster.unlink()
    try:
        raster.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"case raster symlink creation unavailable: {error}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        build_case_visual_projection(view_model, workspace_root=workspace)
