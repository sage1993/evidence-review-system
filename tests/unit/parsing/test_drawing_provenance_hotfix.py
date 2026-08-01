from pathlib import Path

import pytest

from ansim_review.contracts.drawing import DrawingConfirmation, Geometry
from ansim_review.parsing.drawing_binding import bind_confirmed_inputs
from ansim_review.parsing.drawing_candidates import (
    create_manual_candidate,
    persist_candidate,
)
from ansim_review.parsing.drawing_confirmation import (
    persist_confirmation,
    validate_confirmation_for_candidate,
)
from ansim_review.parsing.drawing_inputs import (
    ConfirmedInputBuildRequest,
    build_confirmed_input,
)
from ansim_review.parsing.drawing_source import (
    DrawingIntakePolicy,
    ingest_drawing_source,
)


def _candidate(source_sha256: str):
    return create_manual_candidate(
        case_id="CASE-001",
        source_sha256=source_sha256,
        page=1,
        annotation_id="ANN-001",
        candidate_type="ROAD_WIDTH_TEXT",
        geometry=Geometry(
            type="LINESTRING",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=((1.0, 2.0), (3.0, 4.0)),
        ),
        raw_value="8.0",
        normalized_candidate="8.0",
    )


def test_accepted_confirmation_cannot_replace_candidate_value() -> None:
    candidate = _candidate("a" * 64)
    confirmation = DrawingConfirmation(
        confirmation_id="CONF-001",
        candidate_id=candidate.candidate_id,
        action="ACCEPTED",
        source_sha256=candidate.source_sha256,
        reviewer="김성현",
        confirmed_at="2026-08-02T01:30:00+09:00",
        confirmed_value="9.0",
        unit="m",
        geometry=None,
    )

    with pytest.raises(ValueError, match="ACCEPTED confirmation cannot replace"):
        validate_confirmation_for_candidate(candidate, confirmation)


def test_binding_rejects_tampered_candidate_artifact(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    source = tmp_path / "drawing.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    attachment = ingest_drawing_source(
        source,
        case_dir,
        "ATT-001",
        "CASE_DRAWING",
        DrawingIntakePolicy(),
    )
    candidate = _candidate(attachment.sha256)
    candidate_entry = persist_candidate(case_dir, candidate)
    confirmation = DrawingConfirmation(
        confirmation_id="CONF-001",
        candidate_id=candidate.candidate_id,
        action="ACCEPTED",
        source_sha256=attachment.sha256,
        reviewer="김성현",
        confirmed_at="2026-08-02T01:30:00+09:00",
        confirmed_value=None,
        unit=None,
        geometry=None,
    )
    confirmation_entry = persist_confirmation(
        case_dir,
        "kim-sh",
        candidate,
        confirmation,
    )
    confirmed = build_confirmed_input(
        ConfirmedInputBuildRequest(
            input_id="INPUT-ROAD-WIDTH",
            field="road_width_m",
            value="8.0",
            unit="m",
            candidate=candidate,
            effective_status="ACCEPTED",
            confirmation=confirmation,
            confirmation_entry=confirmation_entry,
        )
    )

    (case_dir / candidate_entry.relative_path).write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="candidate hash mismatch"):
        bind_confirmed_inputs(
            case_dir,
            [confirmed],
            {attachment.sha256: attachment},
            candidate_entries={candidate.candidate_id: candidate_entry},
        )
