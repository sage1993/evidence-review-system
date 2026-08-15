import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.drawing import DrawingConfirmation, Geometry
from evidence_review.parsing.drawing_binding import EngineInputValue, bind_confirmed_inputs
from evidence_review.parsing.drawing_candidates import (
    create_manual_candidate,
    persist_candidate,
)
from evidence_review.parsing.drawing_confirmation import (
    drawing_confirmation_document,
    persist_confirmation,
)
from evidence_review.parsing.drawing_inputs import (
    ConfirmedInputBuildRequest,
    build_confirmed_input,
)
from evidence_review.parsing.drawing_source import (
    DrawingIntakePolicy,
    ingest_drawing_source,
)


def complete_case(tmp_path: Path):
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
            type="LINESTRING",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=((1.0, 2.0), (3.0, 4.0)),
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
    confirmation_entry = persist_confirmation(
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
            confirmation_entry=confirmation_entry,
        )
    )
    return (
        case_dir,
        attachment,
        confirmed,
        candidate_entry,
        confirmation_entry,
        confirmation,
    )


def rewrite_confirmation(case_dir: Path, entry, confirmation: DrawingConfirmation):
    payload = dump_bytes(drawing_confirmation_document(confirmation))
    (case_dir / entry.relative_path).write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def candidate_entries(confirmed, entry):
    return {confirmed.evidence_id: entry}


def test_binding_returns_deterministic_decimal_strings(tmp_path: Path) -> None:
    case_dir, attachment, confirmed, candidate_entry, _, _ = complete_case(tmp_path)
    result = bind_confirmed_inputs(
        case_dir,
        [confirmed],
        {attachment.sha256: attachment},
        candidate_entries=candidate_entries(confirmed, candidate_entry),
    )
    assert result == {
        "road_width_m": EngineInputValue(
            value="8.0", unit="m", input_id="INPUT-ROAD-WIDTH"
        )
    }


def test_binding_reverifies_confirmation_hash(tmp_path: Path) -> None:
    case_dir, attachment, confirmed, candidate_entry, confirmation_entry, _ = (
        complete_case(tmp_path)
    )
    confirmation_path = case_dir / confirmation_entry.relative_path
    confirmation_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="confirmation hash mismatch"):
        bind_confirmed_inputs(
            case_dir,
            [confirmed],
            {attachment.sha256: attachment},
            candidate_entries=candidate_entries(confirmed, candidate_entry),
        )


def test_binding_rejects_confirmation_action_mismatch(tmp_path: Path) -> None:
    case_dir, attachment, confirmed, candidate_entry, entry, confirmation = complete_case(
        tmp_path
    )
    modified = replace(confirmation, action="EDITED")
    digest = rewrite_confirmation(case_dir, entry, modified)
    confirmed = replace(confirmed, confirmation_sha256=digest)
    with pytest.raises(ValueError, match="confirmation action does not match"):
        bind_confirmed_inputs(
            case_dir,
            [confirmed],
            {attachment.sha256: attachment},
            candidate_entries=candidate_entries(confirmed, candidate_entry),
        )


def test_binding_rejects_confirmation_value_mismatch(tmp_path: Path) -> None:
    case_dir, attachment, confirmed, candidate_entry, entry, confirmation = complete_case(
        tmp_path
    )
    modified = replace(confirmation, confirmed_value="9.0")
    digest = rewrite_confirmation(case_dir, entry, modified)
    confirmed = replace(confirmed, confirmation_sha256=digest)
    with pytest.raises(ValueError, match="confirmation value does not match"):
        bind_confirmed_inputs(
            case_dir,
            [confirmed],
            {attachment.sha256: attachment},
            candidate_entries=candidate_entries(confirmed, candidate_entry),
        )


def test_binding_reverifies_source_hash(tmp_path: Path) -> None:
    case_dir, attachment, confirmed, candidate_entry, _, _ = complete_case(tmp_path)
    source_path = case_dir / "sources" / "drawings" / "ATT-001.png"
    source_path.write_bytes(source_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="immutable source verification failed"):
        bind_confirmed_inputs(
            case_dir,
            [confirmed],
            {attachment.sha256: attachment},
            candidate_entries=candidate_entries(confirmed, candidate_entry),
        )


def test_binding_rejects_missing_source_attachment(tmp_path: Path) -> None:
    case_dir, _, confirmed, candidate_entry, _, _ = complete_case(tmp_path)
    with pytest.raises(ValueError, match="source attachment is not registered"):
        bind_confirmed_inputs(
            case_dir,
            [confirmed],
            {},
            candidate_entries=candidate_entries(confirmed, candidate_entry),
        )


def test_binding_rejects_missing_candidate_entry(tmp_path: Path) -> None:
    case_dir, attachment, confirmed, _, _, _ = complete_case(tmp_path)
    with pytest.raises(ValueError, match="candidate entry is not registered"):
        bind_confirmed_inputs(
            case_dir,
            [confirmed],
            {attachment.sha256: attachment},
            candidate_entries={},
        )
