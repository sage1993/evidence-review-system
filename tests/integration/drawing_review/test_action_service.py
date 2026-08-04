from __future__ import annotations

from pathlib import Path

import pytest

from ansim_review.contracts.drawing import DrawingCandidate, Geometry
from ansim_review.drawing_review.actions import (
    ExistingCandidateAction,
    ManualCreateAction,
)
from ansim_review.drawing_review.service import record_annotation_action
from ansim_review.drawing_review.view_model import DrawingPage
from ansim_review.parsing.drawing_candidates import load_candidate, persist_candidate
from ansim_review.parsing.drawing_confirmation import load_and_verify_confirmation

SOURCE_HASH = "a" * 64


def _page(source_sha256: str = SOURCE_HASH) -> DrawingPage:
    return DrawingPage(
        source_sha256=source_sha256,
        page=1,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        width=1000.0,
        height=800.0,
    )


def _extractor_candidate(
    *,
    source_sha256: str = SOURCE_HASH,
    candidate_id: str = "CAND-EXISTING",
) -> DrawingCandidate:
    return DrawingCandidate(
        candidate_id=candidate_id,
        source_sha256=source_sha256,
        page=1,
        candidate_type="DIMENSION_TEXT",
        origin="EXTRACTOR",
        status="UNCONFIRMED",
        geometry=Geometry(
            type="BBOX",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=(100.0, 120.0, 300.0, 180.0),
        ),
        raw_value="8M",
        normalized_candidate="8 m",
        extractor="fixture",
        extractor_version="1",
        annotation_id=None,
    )


def _accepted(candidate_id: str = "CAND-EXISTING") -> ExistingCandidateAction:
    return ExistingCandidateAction(
        action="ACCEPTED",
        candidate_id=candidate_id,
        reviewer="kim-sh",
        confirmed_at="2026-08-03T21:50:00+09:00",
        confirmed_value=None,
        unit=None,
        geometry=None,
    )


def test_records_existing_candidate_acceptance(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    candidate = _extractor_candidate()
    candidate_entry = persist_candidate(case_dir, candidate)

    result = record_annotation_action(
        case_dir,
        _page(),
        {candidate.candidate_id: candidate_entry},
        _accepted(),
    )

    assert result.candidate_entry is None
    confirmation = load_and_verify_confirmation(
        case_dir,
        result.confirmation_entry,
    )
    assert confirmation.action == "ACCEPTED"
    assert confirmation.candidate_id == candidate.candidate_id
    assert confirmation.source_sha256 == SOURCE_HASH


def test_records_existing_candidate_rejection(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    candidate = _extractor_candidate()
    candidate_entry = persist_candidate(case_dir, candidate)
    action = ExistingCandidateAction(
        action="REJECTED",
        candidate_id=candidate.candidate_id,
        reviewer="kim-sh",
        confirmed_at="2026-08-03T21:51:00+09:00",
        confirmed_value=None,
        unit=None,
        geometry=None,
    )

    result = record_annotation_action(
        case_dir,
        _page(),
        {candidate.candidate_id: candidate_entry},
        action,
    )

    confirmation = load_and_verify_confirmation(case_dir, result.confirmation_entry)
    assert confirmation.action == "REJECTED"


def test_records_existing_candidate_edit(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    candidate = _extractor_candidate()
    candidate_entry = persist_candidate(case_dir, candidate)
    replacement = Geometry(
        type="BBOX",
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        coordinates=(110.0, 130.0, 320.0, 190.0),
    )
    action = ExistingCandidateAction(
        action="EDITED",
        candidate_id=candidate.candidate_id,
        reviewer="kim-sh",
        confirmed_at="2026-08-03T21:52:00+09:00",
        confirmed_value="8.5",
        unit="m",
        geometry=replacement,
    )

    result = record_annotation_action(
        case_dir,
        _page(),
        {candidate.candidate_id: candidate_entry},
        action,
    )

    confirmation = load_and_verify_confirmation(case_dir, result.confirmation_entry)
    assert confirmation.action == "EDITED"
    assert confirmation.confirmed_value == "8.5"
    assert confirmation.geometry == replacement


def test_records_manual_candidate_and_confirmation(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    geometry = Geometry(
        type="LINESTRING",
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        coordinates=((100.0, 200.0), (900.0, 200.0)),
    )
    action = ManualCreateAction(
        action="CREATED",
        annotation_id="ANN-ROAD-WIDTH",
        candidate_type="ROAD_WIDTH_TEXT",
        reviewer="kim-sh",
        confirmed_at="2026-08-03T21:53:00+09:00",
        confirmed_value="8.0",
        unit="m",
        geometry=geometry,
    )

    result = record_annotation_action(case_dir, _page(), {}, action)

    assert result.candidate_entry is not None
    candidate = load_candidate(case_dir, result.candidate_entry.artifact_id)
    assert candidate.origin == "REVIEWER_MANUAL"
    assert candidate.status == "CREATED"
    assert candidate.geometry == geometry
    confirmation = load_and_verify_confirmation(case_dir, result.confirmation_entry)
    assert confirmation.action == "CREATED"
    assert confirmation.candidate_id == candidate.candidate_id


def test_rejects_tampered_candidate_before_confirmation(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    candidate = _extractor_candidate()
    candidate_entry = persist_candidate(case_dir, candidate)
    candidate_path = case_dir / candidate_entry.relative_path
    candidate_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="candidate hash mismatch"):
        record_annotation_action(
            case_dir,
            _page(),
            {candidate.candidate_id: candidate_entry},
            _accepted(),
        )

    assert not (case_dir / "confirmations").exists()


def test_rejects_candidate_from_stale_source(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    candidate = _extractor_candidate(source_sha256="b" * 64)
    candidate_entry = persist_candidate(case_dir, candidate)

    with pytest.raises(ValueError, match="source_sha256"):
        record_annotation_action(
            case_dir,
            _page(),
            {candidate.candidate_id: candidate_entry},
            _accepted(),
        )


def test_rejects_manual_coordinate_mismatch_before_write(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    action = ManualCreateAction(
        action="CREATED",
        annotation_id="ANN-PDF",
        candidate_type="SITE_BOUNDARY",
        reviewer="kim-sh",
        confirmed_at="2026-08-03T21:54:00+09:00",
        confirmed_value=None,
        unit=None,
        geometry=Geometry(
            type="POLYGON",
            coordinate_system="PDF_BOTTOM_LEFT_POINTS",
            coordinates=(
                (10.0, 10.0),
                (50.0, 10.0),
                (50.0, 50.0),
                (10.0, 10.0),
            ),
        ),
    )

    with pytest.raises(ValueError, match="coordinate_system"):
        record_annotation_action(case_dir, _page(), {}, action)

    assert not (case_dir / "candidates").exists()


def test_duplicate_action_does_not_overwrite(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    candidate = _extractor_candidate()
    candidate_entry = persist_candidate(case_dir, candidate)
    entries = {candidate.candidate_id: candidate_entry}
    action = _accepted()

    first = record_annotation_action(case_dir, _page(), entries, action)
    first_bytes = (case_dir / first.confirmation_entry.relative_path).read_bytes()

    with pytest.raises(FileExistsError):
        record_annotation_action(case_dir, _page(), entries, action)

    assert (case_dir / first.confirmation_entry.relative_path).read_bytes() == first_bytes
