from evidence_review.review_packet.visual_findings import build_semantic_visual_findings


def _candidate(
    candidate_id: str,
    bbox: list[float],
    value: str,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "candidate_type": "TEXT_ELEMENT",
        "geometry": {
            "type": "BBOX",
            "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
            "coordinates": bbox,
        },
        "raw_value": value,
        "normalized_candidate": None,
        "display_value": value,
        "issue_ids": ["I1"],
        "issue_questions": [],
        "claims": [],
        "review_statuses": [],
    }


def test_semantic_grouping_splits_distant_candidates_before_focus_bbox_union() -> None:
    pages = [
        {
            "asset_key": "ATT-1-p1",
            "width": 2000.0,
            "height": 1200.0,
            "candidates": [
                _candidate("CAND-1", [100.0, 100.0, 260.0, 140.0], "프로젝트 식별"),
                _candidate("CAND-2", [280.0, 102.0, 420.0, 142.0], "금천구 독산동"),
                _candidate("CAND-3", [1300.0, 720.0, 1540.0, 780.0], "사전자문 접수"),
            ],
        }
    ]

    findings = build_semantic_visual_findings(pages)

    assert len(findings) == 2
    assert findings[0]["candidate_ids"] == ["CAND-1", "CAND-2"]
    assert findings[0]["focus_bbox"] == [100.0, 100.0, 420.0, 142.0]
    assert findings[1]["candidate_ids"] == ["CAND-3"]
    assert findings[1]["focus_bbox"] == [1300.0, 720.0, 1540.0, 780.0]


def test_semantic_grouping_keeps_nearby_visual_ocr_fragments_together() -> None:
    pages = [
        {
            "asset_key": "ATT-1-p1",
            "width": 1000.0,
            "height": 800.0,
            "candidates": [
                _candidate("CAND-1", [100.0, 100.0, 220.0, 140.0], "프로젝트명"),
                _candidate("CAND-2", [240.0, 102.0, 360.0, 142.0], "신축공사"),
            ],
        }
    ]

    findings = build_semantic_visual_findings(pages)

    assert len(findings) == 1
    assert findings[0]["category"] == "visual_observation"
    assert findings[0]["candidate_ids"] == ["CAND-1", "CAND-2"]
    assert findings[0]["focus_bbox"] == [100.0, 100.0, 360.0, 142.0]
