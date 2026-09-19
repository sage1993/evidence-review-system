from evidence_review.review_packet.visual_findings import build_semantic_visual_findings


def test_visual_finding_preserves_field_level_value_unit_page_bbox_and_uncertainty() -> None:
    findings = build_semantic_visual_findings(
        [
            {
                "asset_key": "ATT-1-p7",
                "page": 7,
                "candidates": [
                    {
                        "candidate_id": "CAND-1",
                        "candidate_type": "DIMENSION_TEXT",
                        "display_value": "4.2 m",
                        "status": "UNCONFIRMED",
                        "geometry": {
                            "type": "BBOX",
                            "coordinates": [10, 20, 90, 120],
                        },
                    }
                ],
            }
        ]
    )

    observation = findings[0]["observations"][0]
    assert observation == {
        "candidate_id": "CAND-1",
        "label": "DIMENSION_TEXT",
        "value": "4.2 m",
        "unit": "m",
        "source_page": 7,
        "bbox": [10.0, 20.0, 90.0, 120.0],
        "uncertainty_state": "NOT_VERIFIED",
    }
