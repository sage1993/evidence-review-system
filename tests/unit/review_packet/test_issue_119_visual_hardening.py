import hashlib
import json
from pathlib import Path

from evidence_review.review_packet.case_visual_projection import build_case_visual_projection
from evidence_review.review_packet.render_case_visual import render_case_visual_review
from evidence_review.review_packet.render_summary import render_additional_review


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _projection_fixture(tmp_path: Path, *, with_rule: bool) -> tuple[dict[str, object], Path]:
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

    candidates = [
        {
            "candidate_id": "CAND-VISUAL-1",
            "source_sha256": source_hash,
            "page": 1,
            "candidate_type": "TEXT_ELEMENT",
            "origin": "EXTRACTOR",
            "status": "UNCONFIRMED",
            "geometry": {
                "type": "BBOX",
                "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                "coordinates": [10, 20, 35, 40],
            },
            "raw_value": "101동",
            "normalized_candidate": None,
            "extractor": "codex-vision",
            "extractor_version": "1.0.0",
            "annotation_id": None,
        },
        {
            "candidate_id": "CAND-VISUAL-2",
            "source_sha256": source_hash,
            "page": 1,
            "candidate_type": "TEXT_ELEMENT",
            "origin": "EXTRACTOR",
            "status": "UNCONFIRMED",
            "geometry": {
                "type": "BBOX",
                "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                "coordinates": [40, 20, 65, 40],
            },
            "raw_value": "102동",
            "normalized_candidate": None,
            "extractor": "codex-vision",
            "extractor_version": "1.0.0",
            "annotation_id": None,
        },
    ]
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
        "drawing_candidates": candidates,
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
            {"candidate_id": "CAND-VISUAL-1", "issue_ids": ["I1"]},
            {"candidate_id": "CAND-VISUAL-2", "issue_ids": ["I1"]},
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
                            "question": "이 도면이 설계기준에 적합한가",
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
                    "text": "목적조항은 관련 배경 자료다.",
                    "issue_ids": ["I1"],
                    "citation_ids": ["CIT-RELATED"],
                    "drawing_candidate_ids": ["CAND-VISUAL-1", "CAND-VISUAL-2"],
                }
            ]
        },
    )
    review_item: dict[str, object] = {
        "claim_id": "CL-I1-1",
        "status": "NOT_SATISFIED" if with_rule else "INDETERMINATE",
        "rule_ids": ["RULE-1"] if with_rule else [],
    }
    return {"run_id": run_id, "review_items": [review_item]}, workspace


def _render_model(*, abstain: bool = True, direct: bool = False) -> dict[str, object]:
    claims = [
        {
            "claim_id": "CL-I1-1",
            "text": "관련 배경 자료",
            "citations": [
                {
                    "citation_id": "CIT-1",
                    "document_name": "설계기준",
                    "page_number": 12,
                    "quote": "직접 비교값이 아닌 관련 문장",
                }
            ],
        }
    ]
    candidate = {
        "candidate_id": "CAND-1",
        "source_sha256": "a" * 64,
        "page": 1,
        "candidate_type": "TEXT_ELEMENT",
        "origin": "EXTRACTOR",
        "status": "UNCONFIRMED",
        "geometry": {
            "type": "BBOX",
            "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
            "coordinates": [10.0, 20.0, 80.0, 90.0],
        },
        "raw_value": "101동",
        "normalized_candidate": None,
        "extractor": "codex-vision",
        "extractor_version": "1.0.0",
        "annotation_id": None,
        "issue_ids": ["I1"],
        "issue_questions": ["이 도면이 설계기준에 적합한가"],
        "claims": [
            {
                "claim_id": "CL-I1-1",
                "text": "관련 배경 자료",
                "issue_ids": ["I1"],
                "citation_ids": ["CIT-1"],
                "relation": "direct" if direct else "related",
            }
        ],
        "review_statuses": ["NOT_SATISFIED"] if direct else [],
        "tone": "issue" if direct else "observation",
        "display_value": "101동",
    }
    model: dict[str, object] = {
        "status": "ABSTAIN" if abstain else "READY_FOR_HUMAN_REVIEW",
        "display_status": "ABSTAIN" if abstain else "READY_FOR_HUMAN_REVIEW",
        "abstention_reasons": ["직접 비교 가능한 기준 근거가 부족합니다."] if abstain else [],
        "claims": claims,
        "case_visual_review": {
            "status": "VISUAL_ANALYSIS_VALIDATED",
            "attachment_count": 1,
            "candidate_count": 1,
            "pages": [
                {
                    "asset_key": "ATT-1-p1",
                    "attachment_id": "ATT-1",
                    "document_name": "배치-test.pdf",
                    "source_sha256": "a" * 64,
                    "page": 1,
                    "width": 100.0,
                    "height": 120.0,
                    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                    "image_sha256": "b" * 64,
                    "data_uri": "data:image/png;base64,ZmFrZQ==",
                    "candidates": [candidate],
                }
            ],
            "findings": [
                {
                    "finding_id": "VF-1",
                    "title": "동·건축물 식별",
                    "category": "building_identity",
                    "status": "not_comparable" if not direct else "mismatch",
                    "page_asset_key": "ATT-1-p1",
                    "candidate_ids": ["CAND-1"],
                    "issue_ids": ["I1"],
                    "subject_value": "101동",
                    "focus_bbox": [10.0, 20.0, 80.0, 90.0],
                    "direct_claim_ids": ["CL-I1-1"] if direct else [],
                    "related_claim_ids": [] if direct else ["CL-I1-1"],
                }
            ],
        },
    }
    return model


def test_projection_separates_direct_and_related_references(tmp_path: Path) -> None:
    view_model, workspace = _projection_fixture(tmp_path, with_rule=False)

    result = build_case_visual_projection(view_model, workspace_root=workspace)

    assert result is not None
    candidates = result["pages"][0]["candidates"]
    assert all(item["claims"][0]["relation"] == "related" for item in candidates)
    assert result["findings"][0]["status"] == "not_comparable"


def test_projection_groups_ocr_fragments_into_semantic_finding(tmp_path: Path) -> None:
    view_model, workspace = _projection_fixture(tmp_path, with_rule=False)

    result = build_case_visual_projection(view_model, workspace_root=workspace)

    assert result is not None
    findings = result["findings"]
    assert len(findings) == 1
    assert findings[0]["category"] == "building_identity"
    assert findings[0]["title"] == "동·건축물 식별"
    assert findings[0]["candidate_ids"] == ["CAND-VISUAL-1", "CAND-VISUAL-2"]
    assert "101동" in findings[0]["subject_value"]
    assert "102동" in findings[0]["subject_value"]
    assert "이 도면이 설계기준에 적합한가" not in findings[0]["subject_value"]


def test_renderer_never_emits_opaque_unstyled_svg_helper_rect() -> None:
    html = render_case_visual_review(_render_model())

    assert '<rect class="case-visual-shape"' not in html
    assert 'fill="none"' in html


def test_renderer_has_direct_reference_empty_state_and_related_reference_disclosure() -> None:
    html = render_case_visual_review(_render_model(direct=False))

    assert "직접 대조 가능한 기준을 찾지 못했습니다." in html
    assert "관련 근거" in html
    assert "직접 비교 가능한 기준 없음" in html


def test_renderer_keeps_not_comparable_separate_from_needs_check() -> None:
    html = render_case_visual_review(_render_model(direct=False))

    assert "비교 불가" in html
    assert 'data-finding-status="not_comparable"' in html
    assert 'data-case-filter="not_comparable"' in html
    assert 'data-case-filter="needs_check"' in html


def test_renderer_shows_compact_abstain_summary_without_repeating_issue_question() -> None:
    model = _render_model(abstain=True)
    html = render_case_visual_review(model)

    assert "현재 자료로 적합성 판정 불가" in html
    assert html.count("이 도면이 설계기준에 적합한가") == 0


def test_renderer_implements_selected_only_and_finding_autofocus() -> None:
    html = render_case_visual_review(_render_model())

    assert 'data-case-overlay-mode="selected"' in html
    assert "focusSubjectFinding" in html
    assert "scrollIntoView" in html


def test_visual_workspace_uses_click_only_decision_drawer() -> None:
    html = render_additional_review(_render_model())

    assert 'data-case-decision-open' in html
    assert 'data-visual-decision-open="true"' in html
    assert "#decision-form:hover" not in html


def test_renderer_defers_raster_decode_to_active_page() -> None:
    html = render_case_visual_review(_render_model())

    assert 'data-case-page-src="data:image/png;base64,ZmFrZQ=="' in html
    assert 'src="data:image/png;base64,ZmFrZQ=="' not in html
    assert "ensurePageRaster" in html
