from __future__ import annotations

from pathlib import Path

from ansim_review.contracts.drawing import DrawingCandidate, Geometry
from ansim_review.drawing_review.actions import decode_annotation_action
from ansim_review.drawing_review.service import record_annotation_action
from ansim_review.drawing_review.view_model import DrawingPage
from ansim_review.parsing.drawing_candidates import persist_candidate
from ansim_review.parsing.drawing_confirmation import load_and_verify_confirmation

SOURCE_HASH = "a" * 64


def test_unicode_reviewer_identity_uses_server_derived_path_token(
    tmp_path: Path,
) -> None:
    action = decode_annotation_action(
        {
            "action": "ACCEPTED",
            "candidate_id": "CAND-001",
            "reviewer": "김성현",
            "confirmed_at": "2026-08-03T22:30:00+09:00",
            "confirmed_value": None,
            "unit": None,
            "geometry": None,
        }
    )
    candidate = DrawingCandidate(
        candidate_id="CAND-001",
        source_sha256=SOURCE_HASH,
        page=1,
        candidate_type="DIMENSION_TEXT",
        origin="EXTRACTOR",
        status="UNCONFIRMED",
        geometry=Geometry(
            type="BBOX",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=(10.0, 20.0, 30.0, 40.0),
        ),
        raw_value="8.0",
        normalized_candidate="8.0",
        extractor="fixture",
        extractor_version="1",
        annotation_id=None,
    )
    case_dir = tmp_path / "cases" / "CASE-001"
    candidate_entry = persist_candidate(case_dir, candidate)
    page = DrawingPage(
        source_sha256=SOURCE_HASH,
        page=1,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        width=100.0,
        height=100.0,
    )

    result = record_annotation_action(
        case_dir,
        page,
        {candidate.candidate_id: candidate_entry},
        action,
    )

    confirmation = load_and_verify_confirmation(case_dir, result.confirmation_entry)
    assert confirmation.reviewer == "김성현"
    assert "김성현" not in result.confirmation_entry.relative_path
    assert "-REV-" in result.confirmation_entry.relative_path
