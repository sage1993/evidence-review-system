from __future__ import annotations

from evidence_review.review_packet.drawing_evidence import render_drawing_evidence


def _candidate(candidate_id: str, geometry: dict[str, object]) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "source_sha256": "c" * 64,
        "page": 1,
        "candidate_type": "SITE_BOUNDARY",
        "origin": "EXTRACTOR",
        "status": "UNCONFIRMED",
        "geometry": geometry,
        "raw_value": None,
        "normalized_candidate": None,
        "extractor": "drawing-extractor",
        "extractor_version": "1.0.0",
        "annotation_id": None,
    }


def test_render_review_packet_v2_embeds_drawing_and_all_geometry_types() -> None:
    packet = {
        "format": "evidence-review/review-packet",
        "version": 2,
        "run_id": "RUN-001",
        "case_id": "CASE-001",
        "question": "Is the site boundary confirmed?",
        "finalizer_status": "READY_FOR_HUMAN_REVIEW",
        "snapshot_sha256": "d" * 64,
        "rule_manifest_sha256": "e" * 64,
        "formula_manifest_sha256": "f" * 64,
        "claims": [],
        "evidence": [],
        "drawing_evidence": [
            _candidate(
                "POINT",
                {
                    "type": "POINT",
                    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                    "coordinates": [10, 20],
                },
            ),
            _candidate(
                "BBOX",
                {
                    "type": "BBOX",
                    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                    "coordinates": [20, 30, 120, 130],
                },
            ),
            _candidate(
                "LINE",
                {
                    "type": "LINESTRING",
                    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                    "coordinates": [[30, 40], [130, 140]],
                },
            ),
            _candidate(
                "POLYGON",
                {
                    "type": "POLYGON",
                    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                    "coordinates": [[40, 50], [140, 50], [140, 150], [40, 50]],
                },
            ),
        ],
        "confirmed_inputs": [],
        "calculations": [],
        "rule_evaluations": [],
        "exceptions": [],
        "conflicts": [],
        "confidence": None,
        "abstention_reasons": [],
        "human_decision": None,
        "compatibility_source_version": None,
    }

    html = render_drawing_evidence(
        packet,
        page_images={1: b"fixture-image"},
        page_dimensions={1: (200, 200)},
        mime="image/png",
    )

    assert "data:image/png;base64," in html
    assert 'data-candidate-id="POINT"' in html
    assert "<circle" in html
    assert "<rect" in html
    assert "<polyline" in html
    assert "<polygon" in html
    assert "human_decision" in html
    assert "http://" not in html
    assert "https://" not in html


def test_render_drawing_evidence_displays_verified_handoff_metadata() -> None:
    packet = {
        "format": "evidence-review/review-packet",
        "version": 2,
        "run_id": "RUN-001",
        "case_id": "CASE-001",
        "question": "Drawing calibration",
        "finalizer_status": "READY_FOR_HUMAN_REVIEW",
        "snapshot_sha256": "a" * 64,
        "rule_manifest_sha256": "b" * 64,
        "formula_manifest_sha256": "c" * 64,
        "claims": [], "evidence": [], "drawing_evidence": [],
        "confirmed_inputs": [], "calculations": [], "rule_evaluations": [],
        "exceptions": [], "conflicts": [], "confidence": None,
        "abstention_reasons": [], "human_decision": None,
        "compatibility_source_version": None,
    }
    html = render_drawing_evidence(
        packet,
        page_images={},
        page_dimensions={},
        display_metadata={
            "source_document": {
                "document_id": "DOC-SAMPLE",
                "revision_id": "REV-1",
                "page": 17,
                "source_sha256": "a" * 64,
            },
            "candidate_id": "CAND-SAMPLE",
            "confirmation_id": "CONF-SAMPLE",
            "calibration_id": "CAL-SAMPLE",
            "reviewer": "ksh",
            "confirmed_at": "2026-08-06T12:00:00+09:00",
            "calibration": {
                "axis": "x", "pixel_points": [[1200, 900], [8400, 900]],
                "real_length": "35.0", "unit": "m", "scale_x": "0.004",
                "scale_y": None, "formula_id": "DRAWING_SCALE",
                "formula_version": "1.0.0", "calculation_result_hash": "d" * 64,
            },
            "artifact_paths": {
                "candidate": "candidates/CAND-SAMPLE.json",
                "confirmation": "confirmations/CONF-SAMPLE.json",
                "calibration": "calibrations/CAL-SAMPLE.json",
            },
        },
    )

    assert "DOC-SAMPLE" in html
    assert "CAL-SAMPLE" in html
    assert "DRAWING_SCALE" in html
    assert "candidates/CAND-SAMPLE.json" in html
