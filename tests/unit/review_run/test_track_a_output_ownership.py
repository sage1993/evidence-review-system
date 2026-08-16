from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.review_run import TrackAContractError, _publish_validated_track_a


def _document(value: str) -> dict[str, object]:
    return {"run_id": "RUN-1", "claims": [], "marker": value}


def test_track_a_publish_reuses_identical_existing_canonical_output(tmp_path: Path) -> None:
    source = tmp_path / "attempt.json"
    destination = tmp_path / "track-a-output.json"
    document = _document("same")
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    source.write_bytes(encoded)
    destination.write_bytes(encoded)

    _publish_validated_track_a(source, destination, document)

    assert destination.read_bytes() == encoded


def test_track_a_publish_reports_typed_mismatch_instead_of_file_exists(tmp_path: Path) -> None:
    source = tmp_path / "attempt.json"
    destination = tmp_path / "track-a-output.json"
    source.write_text(json.dumps(_document("new")), encoding="utf-8")
    destination.write_text(json.dumps(_document("old")), encoding="utf-8")

    with pytest.raises(TrackAContractError) as raised:
        _publish_validated_track_a(source, destination, _document("new"))

    assert raised.value.reason_code == "TRACK_A_INPUT_MISMATCH"


def test_track_a_publish_reports_malformed_existing_canonical_output(tmp_path: Path) -> None:
    source = tmp_path / "attempt.json"
    destination = tmp_path / "track-a-output.json"
    source.write_text(json.dumps(_document("new")), encoding="utf-8")
    destination.write_text("{partial", encoding="utf-8")

    with pytest.raises(TrackAContractError) as raised:
        _publish_validated_track_a(source, destination, _document("new"))

    assert raised.value.reason_code == "TRACK_A_INPUT_MISMATCH"
