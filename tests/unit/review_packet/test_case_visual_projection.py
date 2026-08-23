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
    with_reference: bool = True,
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

    reference_source_hash = "b" * 64
    reference_bytes = b"verified-reference-page"
    reference_directory = workspace / "page-images" / "REV-REF"
    reference_directory.mkdir(parents=True, exist_ok=True)
    (reference_directory / "page-0012.png").write_bytes(reference_bytes)
    _write_json(
        reference_directory / "page-0012.json",
        {
            "format": "evidence-review/page-image",
            "version": 1,
            "revision_id": "REV-REF",
            "page_number": 12,
            "source_hash": reference_source_hash,
            "pdf_width": 595.0,
            "pdf_height": 842.0,
            "image_sha256": hashlib.sha256(reference_bytes).hexdigest(),
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
        "review_items": [review_item],
        "claims": [
            {
                "claim_id": "CL-I1-1",
                "citations": (
                    [
                        {
                            "citation_id": "CIT-RULE-1",
                            "evidence_id": "E-RULE-1",
                            "document_id": "DOC-REF",
                            "document_name": "서울특별시 건축조례",
                            "document_page_count": 30,
                            "revision_id": "REV-REF",
                            "page_number": 12,
                            "source_hash": reference_source_hash,
                            "page_width": 595.0,
                            "page_height": 842.0,
                            "page_origin_x": 0.0,
                            "page_origin_y": 0.0,
                            "page_rotation": 0,
                            "page_box_kind": "MEDIA_BOX",
                            "bbox": [72.0, 420.0, 510.0, 460.0],
                            "title": "제8조",
                            "quote": "3미터 이상의 거리를 확보한다.",
                            "reference": {
                                "type": "TEXT",
                                "table": None,
                                "visual": None,
                            },
                        }
                    ]
                    if with_reference
                    else []
                ),
            }
        ],
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
    assert finding["finding_id"] == "CAND-VISUAL-1"
    assert finding["reference_anchors"][0]["page"] == 12
    assert finding["reference_anchors"][0]["page_asset_key"].startswith(
        "reference-page-"
    )
    assert finding["subject_region"] == {
        "page_asset_key": "ATT-VISUAL-1-p1",
        "attachment_id": "ATT-VISUAL-1",
        "page": 1,
        "geometry": candidate["geometry"],
    }
    assert (
        finding["reference_anchors"][0]["bbox"]["coordinate_system"]
        != finding["subject_region"]["geometry"]["coordinate_system"]
    )
    assert len(result["reference_pages"]) == 1
    assert result["reference_documents"][0]["document_id"] == "DOC-REF"


def test_projection_does_not_invent_reference_for_visual_observation(
    tmp_path: Path,
) -> None:
    view_model, workspace = _fixture(tmp_path, with_reference=False)

    result = build_case_visual_projection(view_model, workspace_root=workspace)

    assert result is not None
    assert result["reference_documents"] == []
    assert result["reference_pages"] == []
    assert result["findings"][0]["reference_anchors"] == []


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
