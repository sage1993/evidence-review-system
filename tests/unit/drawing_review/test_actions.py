from __future__ import annotations

from collections.abc import Mapping

import pytest

from ansim_review.drawing_review.actions import (
    ExistingCandidateAction,
    ManualCreateAction,
    decode_annotation_action,
)


def _existing_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "action": "ACCEPTED",
        "candidate_id": "CAND-001",
        "reviewer": "kim-sh",
        "confirmed_at": "2026-08-03T21:40:00+09:00",
        "confirmed_value": None,
        "unit": None,
        "geometry": None,
    }
    payload.update(overrides)
    return payload


def _manual_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "action": "CREATED",
        "annotation_id": "ANN-ROAD-WIDTH",
        "candidate_type": "ROAD_WIDTH_TEXT",
        "reviewer": "kim-sh",
        "confirmed_at": "2026-08-03T21:40:00+09:00",
        "confirmed_value": "8.0",
        "unit": "m",
        "geometry": {
            "type": "LINESTRING",
            "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
            "coordinates": [[100.0, 200.0], [900.0, 200.0]],
        },
    }
    payload.update(overrides)
    return payload


def test_decodes_existing_candidate_action() -> None:
    action = decode_annotation_action(_existing_payload())

    assert isinstance(action, ExistingCandidateAction)
    assert action.action == "ACCEPTED"
    assert action.candidate_id == "CAND-001"
    assert action.reviewer == "kim-sh"
    assert action.geometry is None


def test_decodes_edited_candidate_value_and_geometry() -> None:
    action = decode_annotation_action(
        _existing_payload(
            action="EDITED",
            confirmed_value="8.5",
            unit="m",
            geometry={
                "type": "BBOX",
                "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                "coordinates": [10.0, 20.0, 30.0, 40.0],
            },
        )
    )

    assert isinstance(action, ExistingCandidateAction)
    assert action.action == "EDITED"
    assert action.confirmed_value == "8.5"
    assert action.geometry is not None
    assert action.geometry.type == "BBOX"


def test_decodes_manual_create_without_browser_candidate_id() -> None:
    action = decode_annotation_action(_manual_payload())

    assert isinstance(action, ManualCreateAction)
    assert action.action == "CREATED"
    assert action.annotation_id == "ANN-ROAD-WIDTH"
    assert action.candidate_type == "ROAD_WIDTH_TEXT"
    assert action.geometry.type == "LINESTRING"


@pytest.mark.parametrize(
    "field,value",
    (
        ("source_sha256", "a" * 64),
        ("confirmation_id", "CONF-BROWSER"),
        ("output_path", "confirmations/browser.json"),
        ("relative_path", "../escape.json"),
    ),
)
def test_rejects_browser_owned_authority_fields(field: str, value: object) -> None:
    payload = _existing_payload()
    payload[field] = value

    with pytest.raises(ValueError, match="unknown fields"):
        decode_annotation_action(payload)


def test_rejects_manual_candidate_id() -> None:
    with pytest.raises(ValueError, match="unknown fields"):
        decode_annotation_action(_manual_payload(candidate_id="CAND-BROWSER"))


def test_rejects_existing_action_without_candidate_id() -> None:
    payload = _existing_payload()
    payload.pop("candidate_id")

    with pytest.raises(ValueError, match="candidate_id"):
        decode_annotation_action(payload)


def test_rejects_manual_create_without_geometry() -> None:
    with pytest.raises(ValueError, match="geometry"):
        decode_annotation_action(_manual_payload(geometry=None))


def test_rejects_non_path_safe_reviewer() -> None:
    with pytest.raises(ValueError, match="reviewer"):
        decode_annotation_action(_existing_payload(reviewer="../reviewer"))


def test_rejects_identifier_over_128_characters() -> None:
    with pytest.raises(ValueError, match="annotation_id"):
        decode_annotation_action(_manual_payload(annotation_id="A" * 129))


def test_rejects_timestamp_without_timezone() -> None:
    with pytest.raises(ValueError, match="explicit UTC offset"):
        decode_annotation_action(
            _existing_payload(confirmed_at="2026-08-03T21:40:00")
        )


@pytest.mark.parametrize(
    "payload,match",
    (
        (_existing_payload(action="ACCEPTED", confirmed_value="8.0", unit="m"), "ACCEPTED"),
        (_existing_payload(action="REJECTED", geometry={
            "type": "POINT",
            "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
            "coordinates": [1.0, 2.0],
        }), "REJECTED"),
        (_existing_payload(action="EDITED", confirmed_value=None, unit=None, geometry=None), "EDITED"),
        (_manual_payload(confirmed_value="8.0", unit=None), "unit"),
        (_manual_payload(confirmed_value=None, unit="m"), "confirmed_value"),
    ),
)
def test_rejects_invalid_action_payload_combinations(
    payload: Mapping[str, object], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        decode_annotation_action(payload)


def test_rejects_unsupported_action() -> None:
    with pytest.raises(ValueError, match="unsupported action"):
        decode_annotation_action(_existing_payload(action="APPROVED"))
