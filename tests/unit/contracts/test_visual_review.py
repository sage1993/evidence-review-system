from __future__ import annotations

import pytest

from evidence_review.contracts.visual_review import decode_visual_analysis_output


def _output() -> dict[str, object]:
    return {
        "format": "evidence-review/visual-analysis-output",
        "version": 1,
        "visual_analysis_id": "VIS-123",
        "observations": [],
    }


def test_empty_visual_observations_are_valid_completed_analysis() -> None:
    result = decode_visual_analysis_output(_output())
    assert result.visual_analysis_id == "VIS-123"
    assert result.observations == ()


def test_visual_output_rejects_conclusion_field() -> None:
    payload = _output()
    payload["conclusion"] = "적합"

    with pytest.raises(ValueError, match="unknown fields"):
        decode_visual_analysis_output(payload)


def test_visual_observation_requires_issue_lineage() -> None:
    payload = _output()
    payload["observations"] = [
        {
            "attachment_id": "ATT-1",
            "source_sha256": "a" * 64,
            "page": 1,
            "issue_ids": [],
            "candidate_type": "MAIN_ENTRY",
            "geometry": {
                "type": "BBOX",
                "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                "coordinates": [1, 1, 5, 5],
            },
            "raw_value": None,
            "normalized_candidate": None,
        }
    ]

    with pytest.raises(ValueError, match="issue_ids must not be empty"):
        decode_visual_analysis_output(payload)
