from __future__ import annotations

import importlib
from types import ModuleType

import pytest


def _drawing() -> ModuleType:
    try:
        return importlib.import_module("evidence_review.contracts.drawing")
    except ModuleNotFoundError:
        pytest.fail("drawing contract module is missing")


def _geometry(kind: str, coordinates: object) -> dict[str, object]:
    return {
        "type": kind,
        "coordinate_system": "PDF_BOTTOM_LEFT_POINTS",
        "coordinates": coordinates,
    }


def test_geometry_round_trips_point_bbox_linestring_polygon() -> None:
    drawing = _drawing()
    payloads = [
        _geometry("POINT", [1, 2]),
        _geometry("BBOX", [1, 2, 3, 4]),
        _geometry("LINESTRING", [[1, 2], [3, 4]]),
        _geometry("POLYGON", [[0, 0], [4, 0], [4, 4], [0, 0]]),
    ]
    for payload in payloads:
        geometry = drawing.decode_geometry(payload)
        assert drawing.geometry_document(geometry) == payload


def test_geometry_rejects_invalid_shapes() -> None:
    drawing = _drawing()
    with pytest.raises(ValueError, match="bbox coordinates are inverted"):
        drawing.decode_geometry(_geometry("BBOX", [3, 2, 1, 4]))
    with pytest.raises(ValueError, match="LINESTRING requires at least two positions"):
        drawing.decode_geometry(_geometry("LINESTRING", [[1, 2]]))
    with pytest.raises(ValueError, match="POLYGON ring must be closed"):
        drawing.decode_geometry(
            _geometry("POLYGON", [[0, 0], [4, 0], [4, 4], [0, 4]])
        )


def test_reviewer_created_candidate_is_distinguishable() -> None:
    drawing = _drawing()
    payload = {
        "candidate_id": "CASE-P1-C1",
        "source_sha256": "a" * 64,
        "page": 1,
        "candidate_type": "VEHICLE_ENTRANCE",
        "origin": "REVIEWER_MANUAL",
        "status": "CREATED",
        "geometry": _geometry("POINT", [10, 20]),
        "raw_value": None,
        "normalized_candidate": None,
        "extractor": None,
        "extractor_version": None,
        "annotation_id": "ANN-1",
    }
    candidate = drawing.decode_drawing_candidate(payload)
    assert drawing.drawing_candidate_document(candidate) == payload


def test_metadata_only_cannot_automatically_pass_quality_gate() -> None:
    drawing = _drawing()
    with pytest.raises(ValueError, match="METADATA_ONLY cannot produce PASS"):
        drawing.decode_drawing_quality(
            {
                "quality": "PASS",
                "physical_size_trust": "METADATA_ONLY",
                "reason_codes": [],
            }
        )


def _confirmed_input(candidate_status: str) -> dict[str, object]:
    return {
        "input_id": "INPUT-1",
        "field": "road_width_m",
        "value": "8.0",
        "unit": "m",
        "status": "CONFIRMED",
        "candidate_status": candidate_status,
        "source_sha256": "a" * 64,
        "page": 1,
        "evidence_id": "CASE-P1-C1",
        "geometry": _geometry("BBOX", [1, 2, 3, 4]),
        "confirmation_record": "confirmations/20260802-reviewer.json",
        "confirmation_sha256": "b" * 64,
    }


def test_unconfirmed_candidate_cannot_decode_as_confirmed_input() -> None:
    drawing = _drawing()
    with pytest.raises(ValueError, match="candidate status cannot bind"):
        drawing.decode_confirmed_input(_confirmed_input("UNCONFIRMED"))


def test_conflicting_candidate_cannot_decode_as_confirmed_input() -> None:
    drawing = _drawing()
    with pytest.raises(ValueError, match="candidate status cannot bind"):
        drawing.decode_confirmed_input(_confirmed_input("CONFLICT"))


def test_confirmed_input_round_trips_decimal_string() -> None:
    drawing = _drawing()
    payload = _confirmed_input("EDITED")
    confirmed = drawing.decode_confirmed_input(payload)
    assert drawing.confirmed_input_document(confirmed) == payload
