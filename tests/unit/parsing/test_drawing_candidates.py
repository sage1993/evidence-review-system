from pathlib import Path

import pytest

from ansim_review.contracts.drawing import Geometry
from ansim_review.parsing.drawing_candidates import (
    candidate_from_raw_element,
    create_manual_candidate,
    extractor_candidate_id,
    load_candidate,
    manual_candidate_id,
    persist_candidate,
)
from ansim_review.parsing.odl_adapter import RawElement


def raw_text_element() -> RawElement:
    return RawElement(
        element_id="DOC-REV-P0001-E00001",
        document_id="DOC",
        revision_id="REV",
        page_number=1,
        parser_order=0,
        element_type="text",
        source_path=("children", 0),
        raw_payload={"type": "text", "content": "8M"},
        raw_payload_hash="b" * 64,
        raw_bbox=(1.0, 2.0, 3.0, 4.0),
        raw_text="8M",
    )


def geometries() -> tuple[Geometry, ...]:
    return (
        Geometry(
            type="POINT",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=(10.0, 20.0),
        ),
        Geometry(
            type="BBOX",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=(10.0, 20.0, 30.0, 40.0),
        ),
        Geometry(
            type="LINESTRING",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=((10.0, 20.0), (30.0, 40.0)),
        ),
        Geometry(
            type="POLYGON",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=(
                (0.0, 0.0),
                (10.0, 0.0),
                (10.0, 10.0),
                (0.0, 0.0),
            ),
        ),
    )


def manual_candidate(geometry: Geometry | None = None):
    return create_manual_candidate(
        case_id="CASE-001",
        source_sha256="a" * 64,
        page=1,
        annotation_id="ANN-001",
        candidate_type="VEHICLE_ENTRANCE",
        geometry=geometry or geometries()[2],
        raw_value=None,
        normalized_candidate=None,
    )


def test_extractor_candidate_id_is_stable() -> None:
    first = extractor_candidate_id(
        "CASE-001", "a" * 64, 1, "opendataloader", "1", "E-17"
    )
    second = extractor_candidate_id(
        "CASE-001", "a" * 64, 1, "opendataloader", "1", "E-17"
    )
    assert first == second
    assert first.startswith("CAND-")


def test_manual_id_uses_annotation_identity() -> None:
    assert manual_candidate_id("CASE-001", "ANN-ROAD-01") == manual_candidate_id(
        "CASE-001", "ANN-ROAD-01"
    )


def test_raw_text_element_becomes_neutral_extractor_candidate() -> None:
    candidate = candidate_from_raw_element(
        case_id="CASE-001",
        source_sha256="a" * 64,
        raw=raw_text_element(),
        extractor="opendataloader",
        extractor_version="1.0",
        coordinate_system="PDF_BOTTOM_LEFT_POINTS",
    )
    assert candidate.candidate_type == "TEXT_ELEMENT"
    assert candidate.origin == "EXTRACTOR"
    assert candidate.status == "UNCONFIRMED"
    assert candidate.geometry.type == "BBOX"
    assert candidate.raw_value == "8M"
    assert candidate.normalized_candidate is None


def test_unknown_parser_type_is_not_given_domain_meaning() -> None:
    raw = raw_text_element()
    unknown = RawElement(
        element_id=raw.element_id,
        document_id=raw.document_id,
        revision_id=raw.revision_id,
        page_number=raw.page_number,
        parser_order=raw.parser_order,
        element_type="site_boundary",
        source_path=raw.source_path,
        raw_payload=raw.raw_payload,
        raw_payload_hash=raw.raw_payload_hash,
        raw_bbox=raw.raw_bbox,
        raw_text=raw.raw_text,
    )
    with pytest.raises(ValueError, match="unsupported neutral parser element type"):
        candidate_from_raw_element(
            case_id="CASE-001",
            source_sha256="a" * 64,
            raw=unknown,
            extractor="opendataloader",
            extractor_version="1.0",
            coordinate_system="PDF_BOTTOM_LEFT_POINTS",
        )


@pytest.mark.parametrize("geometry", geometries())
def test_manual_candidates_support_m0_geometry(geometry: Geometry) -> None:
    candidate = manual_candidate(geometry)
    assert candidate.origin == "REVIEWER_MANUAL"
    assert candidate.status == "CREATED"
    assert candidate.annotation_id == "ANN-001"
    assert candidate.geometry == geometry


def test_candidate_repository_is_create_only(tmp_path: Path) -> None:
    candidate = manual_candidate()
    entry = persist_candidate(tmp_path, candidate)
    assert entry.relative_path == f"candidates/{candidate.candidate_id}.json"
    assert load_candidate(tmp_path, candidate.candidate_id) == candidate
    with pytest.raises(FileExistsError):
        persist_candidate(tmp_path, candidate)
