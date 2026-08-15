from pathlib import Path

import pytest

from evidence_review.contracts.drawing import DrawingConfirmation, Geometry
from evidence_review.parsing.drawing_binding import bind_confirmed_inputs
from evidence_review.parsing.drawing_candidates import (
    create_manual_candidate,
    persist_candidate,
)
from evidence_review.parsing.drawing_confirmation import persist_confirmation
from evidence_review.parsing.drawing_inputs import (
    ConfirmedInputBuildRequest,
    build_confirmed_input,
)
from evidence_review.parsing.drawing_source import (
    DrawingIntakePolicy,
    ingest_drawing_source,
)


def test_tampered_confirmation_blocks_engine_binding(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    source = tmp_path / "drawing.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    attachment = ingest_drawing_source(
        source, case_dir, "ATT-001", "CASE_DRAWING", DrawingIntakePolicy()
    )
    candidate = create_manual_candidate(
        case_id="CASE-001",
        source_sha256=attachment.sha256,
        page=1,
        annotation_id="ANN-001",
        candidate_type="ROAD_WIDTH_TEXT",
        geometry=Geometry(
            type="BBOX",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=(10.0, 20.0, 30.0, 40.0),
        ),
        raw_value=None,
        normalized_candidate=None,
    )
    candidate_entry = persist_candidate(case_dir, candidate)
    confirmation = DrawingConfirmation(
        confirmation_id="CONF-001",
        candidate_id=candidate.candidate_id,
        action="CREATED",
        source_sha256=attachment.sha256,
        reviewer="김성현",
        confirmed_at="2026-08-02T01:30:00+09:00",
        confirmed_value="8.0",
        unit="m",
        geometry=None,
    )
    entry = persist_confirmation(
        case_dir, "kim-sh", candidate, confirmation
    )
    confirmed = build_confirmed_input(
        ConfirmedInputBuildRequest(
            input_id="INPUT-ROAD-WIDTH",
            field="road_width_m",
            value="8.0",
            unit="m",
            candidate=candidate,
            effective_status="CREATED",
            confirmation=confirmation,
            confirmation_entry=entry,
        )
    )

    confirmation_path = case_dir / entry.relative_path
    confirmation_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="confirmation hash mismatch"):
        bind_confirmed_inputs(
            case_dir,
            [confirmed],
            {attachment.sha256: attachment},
            candidate_entries={candidate.candidate_id: candidate_entry},
        )
