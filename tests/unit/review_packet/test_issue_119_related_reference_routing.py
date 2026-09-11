import hashlib
import json
from pathlib import Path

from evidence_review.review_packet.case_visual_projection import build_case_visual_projection
from evidence_review.review_packet.render_case_visual_lazy import render_case_visual_review


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[dict[str, object], Path]:
    workspace = tmp_path / "workspace"
    run_id = "RUN-1234567890ABCDEF1234"
    run_dir = workspace / "runs" / run_id
    attachment_id = "ATT-VISUAL-RELATED-1"
    source_hash = "a" * 64
    image_bytes = b"verified-raster-bytes"
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    image_path = workspace / "case-page-images" / attachment_id / "page-0001.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(image_bytes)
    reference_image_bytes = b"verified-related-reference-page"
    reference_image_path = (
        workspace / "page-images" / "REV-001" / "page-0024.png"
    )
    reference_image_path.parent.mkdir(parents=True, exist_ok=True)
    reference_image_path.write_bytes(reference_image_bytes)
    _write_json(
        reference_image_path.with_suffix(".json"),
        {
            "format": "evidence-review/page-image",
            "version": 1,
            "revision_id": "REV-001",
            "page_number": 24,
            "source_hash": "c" * 64,
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
        "candidate_id": "CAND-SPACE-1",
        "source_sha256": source_hash,
        "page": 1,
        "candidate_type": "unit_floor_plan_configuration",
        "origin": "EXTRACTOR",
        "status": "UNCONFIRMED",
        "geometry": {
            "type": "BBOX",
            "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
            "coordinates": [10, 20, 80, 90],
        },
        "raw_value": "침실2, 주방, 거실, 현관, 팬트리",
        "normalized_candidate": "침실 2개, 주방, 거실, 현관, 팬트리 배치",
        "extractor": "codex-vision",
        "extractor_version": "1.0.0",
        "annotation_id": None,
        "attachment_id": attachment_id,
    }
    context = {
        "attachments": [
            {
                "attachment_id": attachment_id,
                "original_name": "단위세대.png",
                "stored_path": f"inputs/original/{attachment_id}.png",
                "sha256": source_hash,
                "byte_size": 100,
                "mime": "image/png",
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
            {"candidate_id": "CAND-SPACE-1", "issue_ids": ["I1"]}
        ],
    }
    evidence = [
        {
            "citation": {
                "citation_id": "CIT-BUSINESS",
                "document_id": "REF-002",
                "revision_id": "REV-002",
                "page_number": 3,
                "evidence_id": "E-BUSINESS",
                "bbox": [1.0, 2.0, 3.0, 4.0],
                "source_hash": "b" * 64,
            },
            "issue_ids": ["I1"],
            "role": "rule",
            "text": "사업계획의 수립ㆍ제출에 관한 관련 없는 조항",
        },
        {
            "citation": {
                "citation_id": "CIT-UNIT",
                "document_id": "REF-001",
                "revision_id": "REV-001",
                "page_number": 24,
                "evidence_id": "E-UNIT",
                "bbox": [10.0, 20.0, 30.0, 40.0],
                "source_hash": "c" * 64,
            },
            "issue_ids": ["I1"],
            "role": "supporting_fact",
            "text": "2-5-8. 단위세대 계획 시 다음 항목을 의무적으로 설치하여야 한다.",
        },
    ]
    _write_json(
        run_dir / "track-a-bundle.json",
        {
            "evidence": evidence,
            "inputs": {
                "question_plan": {
                    "issues": [
                        {"id": "I1", "question": "단위세대가 기준에 적합한가"}
                    ],
                    "search_requests": [
                        {
                            "id": "S-RULE",
                            "issue_ids": ["I1"],
                            "text": "안심주택 단위세대 적용 기준",
                            "kind": "legal_anchor",
                            "source": "planner",
                            "role": "rule",
                        },
                        {
                            "id": "S-SPACE",
                            "issue_ids": ["I1"],
                            "text": "단위세대 도면의 공간 구성 치수 설비 및 편의시설",
                            "kind": "concept_relation",
                            "source": "planner",
                            "role": "supporting_fact",
                        },
                    ],
                },
                "retrieval_lineage": [
                    {
                        "citation_id": "CIT-BUSINESS",
                        "evidence_id": "E-BUSINESS",
                        "matches": [
                            {
                                "issue_ids": ["I1"],
                                "search_request_id": "S-RULE",
                                "role": "rule",
                                "query_text": "안심주택 단위세대 적용 기준",
                                "retrieval_query": "안심주택 단위세대 적용 기준",
                                "fallback_stage": "HEADING_SCOPED",
                                "origin": "llm",
                            }
                        ],
                    },
                    {
                        "citation_id": "CIT-UNIT",
                        "evidence_id": "E-UNIT",
                        "matches": [
                            {
                                "issue_ids": ["I1"],
                                "search_request_id": "S-SPACE",
                                "role": "supporting_fact",
                                "query_text": "단위세대 도면의 공간 구성 치수 설비 및 편의시설",
                                "retrieval_query": (
                                    "단위세대 도면의 공간 구성 치수 설비 및 편의시설"
                                ),
                                "fallback_stage": "HEADING_SCOPED",
                                "origin": "llm",
                            }
                        ],
                    },
                ],
                "case_visual_context": context,
            },
        },
    )
    _write_json(run_dir / "track-a-output.json", {"claims": []})
    return {
        "run_id": run_id,
        "review_items": [],
        "reference_citations": [
            {
                "citation_id": "CIT-UNIT",
                "evidence_id": "E-UNIT",
                "document_id": "REF-001",
                "revision_id": "REV-001",
                "page_number": 24,
                "bbox": [10.0, 20.0, 30.0, 40.0],
                "source_hash": "c" * 64,
                "document_name": "unit-rules.pdf",
                "document_page_count": 30,
                "page_width": 120.0,
                "page_height": 200.0,
                "page_origin_x": 0.0,
                "page_origin_y": 0.0,
                "page_rotation": 0,
                "page_box_kind": "MEDIA_BOX",
                "title": "Unit rule",
                "quote": "2-5-8. Unit planning requirement.",
                "reference": {
                    "type": "TEXT",
                    "table": None,
                    "visual": None,
                },
            }
        ],
    }, workspace


def test_projection_routes_retrieved_issue_evidence_as_related_reference(
    tmp_path: Path,
) -> None:
    view_model, workspace = _fixture(tmp_path)

    result = build_case_visual_projection(view_model, workspace_root=workspace)

    assert result is not None
    finding = result["findings"][0]
    assert finding["status"] == "not_comparable"
    assert finding["direct_claim_ids"] == []
    assert finding.get("related_evidence_ids") == ["E-UNIT"]
    assert [item["evidence_id"] for item in result.get("related_references", [])] == [
        "E-UNIT"
    ]
    finding = result["findings"][0]
    assert finding["direct_reference_anchors"] == []
    assert len(finding["related_reference_anchors"]) == 1
    anchor = finding["related_reference_anchors"][0]
    assert anchor["reference_role"] == "related"
    assert anchor["anchor_id"] == "CIT-UNIT"
    assert anchor["page"] == 24
    assert {
        item["anchor_id"] for item in finding["related_reference_anchors"]
    } == {"CIT-UNIT"}


def test_renderer_shows_related_retrieval_reference_without_track_a_claim(
    tmp_path: Path,
) -> None:
    view_model, workspace = _fixture(tmp_path)
    projection = build_case_visual_projection(view_model, workspace_root=workspace)
    assert projection is not None
    model = {
        "status": "ABSTAIN",
        "display_status": "ABSTAIN",
        "abstention_reasons": ["직접 비교 가능한 기준 근거가 부족합니다."],
        "claims": [],
        "case_visual_review": projection,
    }

    html = render_case_visual_review(model)

    assert "직접 대조 가능한 기준을 찾지 못했습니다." in html
    assert "관련 근거 1건" in html
    assert "2-5-8. 단위세대 계획 시 다음 항목을 의무적으로 설치하여야 한다." in html
    assert "사업계획의 수립ㆍ제출에 관한 관련 없는 조항" not in html
    assert 'data-finding-status="not_comparable"' in html
