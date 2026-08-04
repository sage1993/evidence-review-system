from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from ansim_review.contracts.drawing import DrawingCandidate, Geometry
from ansim_review.drawing_review.html_renderer import render_annotation_html
from ansim_review.drawing_review.local_server import serve_annotation_workspace
from ansim_review.drawing_review.view_model import (
    DrawingPage,
    build_drawing_review_view_model,
)
from ansim_review.parsing.drawing_binding import bind_confirmed_inputs
from ansim_review.parsing.drawing_candidates import load_candidate, persist_candidate
from ansim_review.parsing.drawing_confirmation import load_and_verify_confirmation
from ansim_review.parsing.drawing_inputs import (
    ConfirmedInputBuildRequest,
    build_confirmed_input,
)
from ansim_review.parsing.drawing_source import (
    DrawingIntakePolicy,
    ingest_drawing_source,
)


def _post(url: str, origin: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        url + "/actions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Origin": origin,
        },
    )
    with urlopen(request, timeout=5) as response:
        assert response.status == 201
        result = json.loads(response.read())
    assert isinstance(result, dict)
    return result


def test_manual_annotation_browser_flow_reaches_engine_binding(tmp_path: Path) -> None:
    source = tmp_path / "site-plan.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"drawing-fixture")
    case_dir = tmp_path / "cases" / "CASE-001"
    attachment = ingest_drawing_source(
        source,
        case_dir,
        "ATT-001",
        "CASE_DRAWING",
        DrawingIntakePolicy(),
    )
    page = DrawingPage(
        source_sha256=attachment.sha256,
        page=1,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        width=1000.0,
        height=800.0,
    )
    extractor_candidate = DrawingCandidate(
        candidate_id="CAND-ROAD-WIDTH",
        source_sha256=attachment.sha256,
        page=1,
        candidate_type="ROAD_WIDTH_TEXT",
        origin="EXTRACTOR",
        status="UNCONFIRMED",
        geometry=Geometry(
            type="BBOX",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=(100.0, 120.0, 300.0, 180.0),
        ),
        raw_value="8.0",
        normalized_candidate="8.0",
        extractor="fixture",
        extractor_version="1",
        annotation_id=None,
    )
    extractor_entry = persist_candidate(case_dir, extractor_candidate)
    model = build_drawing_review_view_model(page, (extractor_candidate,))
    html = render_annotation_html(model, source.read_bytes(), "image/png")

    with serve_annotation_workspace(
        html=html,
        case_dir=case_dir,
        page=page,
        candidate_entries={extractor_candidate.candidate_id: extractor_entry},
        token="T" * 32,
    ) as server:
        with urlopen(server.url, timeout=5) as response:
            rendered = response.read().decode("utf-8")
            assert "CAND-ROAD-WIDTH" in rendered
            assert "data-annotation-overlay" in rendered

        accepted_response = _post(
            server.url,
            server.origin,
            {
                "action": "ACCEPTED",
                "candidate_id": extractor_candidate.candidate_id,
                "reviewer": "kim-sh",
                "confirmed_at": "2026-08-03T22:20:00+09:00",
                "confirmed_value": None,
                "unit": None,
                "geometry": None,
            },
        )
        created_response = _post(
            server.url,
            server.origin,
            {
                "action": "CREATED",
                "annotation_id": "ANN-SETBACK",
                "candidate_type": "SETBACK_LINE",
                "reviewer": "kim-sh",
                "confirmed_at": "2026-08-03T22:21:00+09:00",
                "confirmed_value": "12.0",
                "unit": "m",
                "geometry": {
                    "type": "LINESTRING",
                    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                    "coordinates": [[100.0, 400.0], [900.0, 400.0]],
                },
            },
        )
        assert len(server.results) == 2

    accepted_entry = server.results[0].confirmation_entry
    accepted_confirmation = load_and_verify_confirmation(case_dir, accepted_entry)
    accepted_input = build_confirmed_input(
        ConfirmedInputBuildRequest(
            input_id="INPUT-ROAD-WIDTH",
            field="road_width_m",
            value="8.0",
            unit="m",
            candidate=extractor_candidate,
            effective_status="ACCEPTED",
            confirmation=accepted_confirmation,
            confirmation_entry=accepted_entry,
        )
    )

    created_candidate_data = created_response["candidate"]
    assert isinstance(created_candidate_data, dict)
    created_candidate_id = created_candidate_data["artifact_id"]
    assert isinstance(created_candidate_id, str)
    created_candidate = load_candidate(case_dir, created_candidate_id)
    created_entry = server.results[1].candidate_entry
    assert created_entry is not None
    created_confirmation_entry = server.results[1].confirmation_entry
    created_confirmation = load_and_verify_confirmation(
        case_dir,
        created_confirmation_entry,
    )
    created_input = build_confirmed_input(
        ConfirmedInputBuildRequest(
            input_id="INPUT-SETBACK",
            field="setback_m",
            value="12.0",
            unit="m",
            candidate=created_candidate,
            effective_status="CREATED",
            confirmation=created_confirmation,
            confirmation_entry=created_confirmation_entry,
        )
    )

    bound = bind_confirmed_inputs(
        case_dir,
        (accepted_input, created_input),
        {attachment.sha256: attachment},
        candidate_entries={
            extractor_candidate.candidate_id: extractor_entry,
            created_candidate.candidate_id: created_entry,
        },
    )
    assert bound["road_width_m"].value == "8.0"
    assert bound["setback_m"].value == "12.0"

    with pytest.raises(ValueError, match="cannot bind"):
        build_confirmed_input(
            ConfirmedInputBuildRequest(
                input_id="INPUT-UNCONFIRMED",
                field="unconfirmed_m",
                value="8.0",
                unit="m",
                candidate=extractor_candidate,
                effective_status="UNCONFIRMED",
                confirmation=accepted_confirmation,
                confirmation_entry=accepted_entry,
            )
        )

    accepted_confirmation_data = accepted_response["confirmation"]
    assert isinstance(accepted_confirmation_data, dict)
    assert accepted_confirmation_data["artifact_id"] == accepted_entry.artifact_id
