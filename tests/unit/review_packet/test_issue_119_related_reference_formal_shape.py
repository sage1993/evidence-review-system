from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evidence_review.review_packet.case_visual_projection import build_case_visual_projection


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _citation(index: int, *, target: bool = False) -> dict[str, object]:
    evidence_id = "E-UNIT" if target else f"E-BUSINESS-{index}"
    return {
        "citation_id": f"CIT-{evidence_id}",
        "document_id": "REF-001" if target else "REF-002",
        "revision_id": "REV-001" if target else "REV-002",
        "page_number": 24 if target else 3,
        "evidence_id": evidence_id,
        "bbox": [10.0, 20.0, 30.0, 40.0],
        "source_hash": ("c" if target else "b") * 64,
    }


def _evidence_records(*, reverse_evidence: bool) -> list[dict[str, object]]:
    distractor_texts = [
        "제7조 사업계획의 수립 및 제출에 관한 사항",
        "촉진지구 지정 제안 및 지구계획 승인신청서",
        "주택법에 따른 사업계획승인신청서 및 관련 서류",
        "사업대상지 반경 내 주야간 주정차 및 교통현황",
        "안심주택의 건설 관리 운영에 필요한 사항",
    ]
    records = [
        {
            "citation": _citation(index),
            "issue_ids": ["I1"],
            "role": "supporting_fact",
            "text": text,
        }
        for index, text in enumerate(distractor_texts, start=1)
    ]
    records.append(
        {
            "citation": _citation(1, target=True),
            "issue_ids": ["I1"],
            "role": "supporting_fact",
            "text": (
                "2-5-8. 단위세대 계획 시 냉장고, 세탁기, 에어컨 등 "
                "단위세대 설비 항목을 설치하여야 한다."
            ),
        }
    )
    return list(reversed(records)) if reverse_evidence else records


def _fixture(
    root: Path,
    *,
    reverse_evidence: bool,
) -> tuple[dict[str, object], Path]:
    workspace = root / "workspace"
    run_id = "RUN-1234567890ABCDEF1234"
    run_dir = workspace / "runs" / run_id
    attachment_id = "ATT-VISUAL-RELATED-1"
    source_hash = "a" * 64
    image_bytes = b"verified-raster-bytes"
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    image_path = workspace / "case-page-images" / attachment_id / "page-0001.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(image_bytes)

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
        "raw_value": "침실2, 주방, 거실, 욕실, 팬트리, 냉장고 공간",
        "normalized_candidate": (
            "침실 2개, 주방, 거실, 욕실, 팬트리, 냉장고 공간 배치"
        ),
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
    evidence = _evidence_records(reverse_evidence=reverse_evidence)
    lineage = [
        {
            "citation_id": item["citation"]["citation_id"],
            "evidence_id": item["citation"]["evidence_id"],
            "matches": [
                {
                    "issue_ids": ["I1"],
                    "search_request_id": "S-SPACE",
                    "role": "supporting_fact",
                    "query_text": (
                        "단위세대 도면의 공간 구성 치수 설비 및 편의시설"
                    ),
                    "retrieval_query": (
                        "단위세대 도면의 공간 구성 치수 설비 및 편의시설"
                    ),
                    "fallback_stage": "HEADING_SCOPED",
                    "origin": "llm",
                }
            ],
        }
        for item in evidence
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
                            "id": "S-SPACE",
                            "issue_ids": ["I1"],
                            "text": (
                                "단위세대 도면의 공간 구성 치수 설비 및 편의시설"
                            ),
                            "kind": "concept_relation",
                            "source": "planner",
                            "role": "supporting_fact",
                        }
                    ],
                },
                "retrieval_lineage": lineage,
                "case_visual_context": context,
            },
        },
    )
    _write_json(run_dir / "track-a-output.json", {"claims": []})
    return {"run_id": run_id, "review_items": []}, workspace


def _space_finding(result: dict[str, object]) -> dict[str, object]:
    findings = result["findings"]
    assert isinstance(findings, list)
    return next(item for item in findings if item["title"] == "공간 구성")


def test_related_routing_prefers_semantic_target_over_same_lineage_distractors(
    tmp_path: Path,
) -> None:
    view_model, workspace = _fixture(tmp_path, reverse_evidence=False)

    result = build_case_visual_projection(view_model, workspace_root=workspace)

    assert result is not None
    finding = _space_finding(result)
    assert finding["status"] == "not_comparable"
    assert finding["direct_claim_ids"] == []
    assert finding["related_evidence_ids"] == ["E-UNIT"]
    assert [
        item["evidence_id"] for item in result.get("related_references", [])
    ] == ["E-UNIT"]


def test_related_routing_is_independent_of_evidence_input_order(
    tmp_path: Path,
) -> None:
    normal_model, normal_workspace = _fixture(
        tmp_path / "normal",
        reverse_evidence=False,
    )
    reversed_model, reversed_workspace = _fixture(
        tmp_path / "reversed",
        reverse_evidence=True,
    )

    normal = build_case_visual_projection(
        normal_model,
        workspace_root=normal_workspace,
    )
    reversed_result = build_case_visual_projection(
        reversed_model,
        workspace_root=reversed_workspace,
    )

    assert normal is not None
    assert reversed_result is not None
    assert normal["related_references"] == reversed_result["related_references"]
    assert _space_finding(normal)["related_evidence_ids"] == ["E-UNIT"]
    assert _space_finding(reversed_result)["related_evidence_ids"] == ["E-UNIT"]
