from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_drawing_annotation_workspace import main, prepare_workspace


def test_prepare_workspace_loads_candidate_fixture_and_embeds_page(tmp_path: Path) -> None:
    source = tmp_path / "site-plan.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    case_dir = tmp_path / "CASE-001"
    case_dir.mkdir()
    fixture = tmp_path / "candidates.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "candidate_id": "CAND-FIXTURE",
                    "source_sha256": "a" * 64,
                    "page": 1,
                    "candidate_type": "ROAD_WIDTH_TEXT",
                    "origin": "EXTRACTOR",
                    "status": "UNCONFIRMED",
                    "geometry": {
                        "type": "BBOX",
                        "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                        "coordinates": [10, 20, 30, 40],
                    },
                    "raw_value": "8.0",
                    "normalized_candidate": "8.0",
                    "extractor": "fixture",
                    "extractor_version": "1",
                    "annotation_id": None,
                }
            ]
        ),
        encoding="utf-8",
    )

    source_hash = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    fixture_payload = json.loads(fixture.read_text(encoding="utf-8"))
    fixture_payload[0]["source_sha256"] = source_hash
    fixture.write_text(json.dumps(fixture_payload), encoding="utf-8")

    html, entries = prepare_workspace(
        case_dir=case_dir,
        source=source,
        width=100,
        height=80,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        candidate_fixture=fixture,
    )

    assert "CAND-FIXTURE" in html
    assert entries["CAND-FIXTURE"].relative_path == "candidates/CAND-FIXTURE.json"


def test_prepare_workspace_rejects_conflicting_candidate_inputs(tmp_path: Path) -> None:
    source = tmp_path / "site-plan.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    manifest = tmp_path / "manifest.json"
    fixture = tmp_path / "fixture.json"
    manifest.write_text("[]", encoding="utf-8")
    fixture.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="one of candidate_manifest or candidate_fixture"):
        prepare_workspace(
            case_dir=tmp_path / "CASE-001",
            source=source,
            width=100,
            height=80,
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            candidate_manifest=manifest,
            candidate_fixture=fixture,
        )


def test_launcher_reports_invalid_page_dimensions_without_starting_server(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "site-plan.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    case_dir = tmp_path / "CASE-001"
    case_dir.mkdir()

    result = main(
        [
            "--case-dir",
            str(case_dir),
            "--source",
            str(source),
            "--width",
            "0",
            "--height",
            "80",
            "--coordinate-system",
            "IMAGE_TOP_LEFT_PIXELS",
        ]
    )

    assert result == 2
    assert "positive finite number" in capsys.readouterr().err
