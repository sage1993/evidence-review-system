from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ansim_review.canonical_json import dump_bytes
from ansim_review.confidence.policy import FACTOR_WEIGHTS
from ansim_review.review_run import finalize_review_run, prepare_review_run


def _citation() -> dict[str, object]:
    return {
        "citation_id": "CIT-E1",
        "document_id": "DOC1",
        "revision_id": "REV1",
        "page_number": 1,
        "evidence_id": "E1",
        "bbox": [0, 0, 10, 10],
        "source_hash": "a" * 64,
    }


def _calculation() -> dict[str, object]:
    return {
        "calculation_result_id": "CALC1",
        "status": "SUCCESS",
        "formula_id": "FRONTAGE_RATIO",
        "formula_version": "1.0.0",
        "inputs": {
            "frontage_length_m": "30",
            "perimeter_length_m": "320",
            "threshold_ratio": "0.125",
        },
        "substitution": "30 / 320 = 0.09375",
        "raw_result": "0.09375",
        "display_result": "9.375%",
        "comparison": "BELOW_THRESHOLD",
        "formula_manifest_hash": "b" * 64,
        "result_hash": "d" * 64,
        "error_codes": [],
    }


def _rule() -> dict[str, object]:
    return {
        "rule_result_id": "RULE1",
        "rule_id": "ANSIM-TEST-RULE",
        "rule_version": "1.0.0",
        "status": "SATISFIED",
        "citations": [_citation()],
        "missing_inputs": [],
        "calculation_result_ids": ["CALC1"],
        "reason_codes": ["EVALUATED_TRUE"],
        "result_hash": "c" * 64,
    }


def _confidence_input() -> dict[str, object]:
    return {
        "factors": {
            name: {"value": "1.0", "source": f"fixture:{name}"}
            for name in FACTOR_WEIGHTS
        }
    }


def _request(question: str = "접면 기준 충족 여부") -> dict[str, object]:
    return {
        "format": "ansim/review-run-request",
        "version": 1,
        "question": question,
        "inputs": {"frontage": "30", "perimeter": "320"},
        "evidence": [
            {
                "citation": _citation(),
                "text": "접면 비율은 9.375%이다.",
            }
        ],
        "calculations": [_calculation()],
        "rules": [_rule()],
        "approved_rule_result_ids": ["RULE1"],
        "confidence_input": _confidence_input(),
    }


def _write_request(path: Path, question: str = "접면 기준 충족 여부") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dump_bytes(_request(question)))
    return path


def _workspace(path: Path) -> Path:
    path.mkdir(parents=True)
    evidence = path / "evidence"
    evidence.mkdir()
    connection = sqlite3.connect(evidence / "ansim-evidence.sqlite")
    connection.execute(
        """CREATE TABLE retrieval_records (
            evidence_id TEXT PRIMARY KEY,
            evidence_type TEXT NOT NULL,
            document_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            bbox_json TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            title TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            normalized_text TEXT NOT NULL
        )"""
    )
    connection.execute(
        "INSERT INTO retrieval_records VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "E1",
            "clause",
            "DOC1",
            "REV1",
            1,
            "[0,0,10,10]",
            "a" * 64,
            "접면 기준",
            "접면 비율은 9.375%이다.",
            "접면 비율은 9.375%이다.",
        ),
    )
    connection.commit()
    connection.close()
    return path


def _track_a(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "claims": [
            {
                "claim_id": "CL1",
                "text": "접면 비율은 9.375%이다.",
                "citation_ids": ["CIT-E1"],
                "numeric_tokens": ["9.375%"],
                "calculation_result_ids": ["CALC1"],
                "rule_references": [
                    {
                        "rule_result_id": "RULE1",
                        "result_hash": "c" * 64,
                        "status": "SATISFIED",
                    }
                ],
            }
        ],
        "citations": ["CIT-E1"],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "근거와 계산 결과를 정리한다.",
    }


def _track_b(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "claim_audits": [
            {
                "claim_id": "CL1",
                "disposition": "ACCEPT",
                "finding_codes": [],
                "notes": "",
            }
        ],
        "overall_disposition": "ACCEPT",
    }


def _write_tracks(root: Path, run_id: str) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    track_a = root / "track-a-output.json"
    track_b = root / "track-b-output.json"
    track_a.write_bytes(dump_bytes(_track_a(run_id)))
    track_b.write_bytes(dump_bytes(_track_b(run_id)))
    return track_a, track_b


def test_prepare_is_deterministic_and_refuses_overwrite(tmp_path: Path) -> None:
    first_workspace = _workspace(tmp_path / "first-workspace")
    second_workspace = _workspace(tmp_path / "second-workspace")
    first_request = _write_request(tmp_path / "first-request.json")
    second_request = _write_request(tmp_path / "second-request.json")

    first = prepare_review_run(first_workspace, first_request)
    second = prepare_review_run(second_workspace, second_request)

    assert first.run_id == second.run_id
    assert (first.run_directory / "review-request.json").read_bytes() == (
        second.run_directory / "review-request.json"
    ).read_bytes()
    assert (first.run_directory / "track-a-bundle.json").read_bytes() == (
        second.run_directory / "track-a-bundle.json"
    ).read_bytes()
    assert (first.run_directory / "confidence-input.json").read_bytes() == (
        second.run_directory / "confidence-input.json"
    ).read_bytes()
    assert (first.run_directory / "prepare-status.json").read_bytes() == (
        second.run_directory / "prepare-status.json"
    ).read_bytes()

    with pytest.raises(FileExistsError):
        prepare_review_run(first_workspace, first_request)


def test_finalize_writes_packet_html_manifest_and_published_packet(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_run(
        workspace,
        _write_request(tmp_path / "request.json"),
    )
    track_a, track_b = _write_tracks(tmp_path, prepared.run_id)

    result = finalize_review_run(
        workspace,
        prepared.run_id,
        track_a,
        track_b,
        publish=True,
    )

    assert result.packet.status == "READY_FOR_HUMAN_REVIEW"
    assert result.packet.human_decision is None
    assert result.packet_path.is_file()
    assert result.review_html.is_file()
    assert (prepared.run_directory / "run-manifest.json").is_file()
    assert result.published_packet == workspace / "runs/final-review-packet.json"
    assert result.published_packet.read_bytes() == result.packet_path.read_bytes()
    published = json.loads(result.published_packet.read_text(encoding="utf-8"))
    assert published["human_decision"] is None
    html = result.review_html.read_text(encoding="utf-8")
    assert "Machine evaluation is not the final decision" in html
    assert "9.375%" in html


def test_finalize_refuses_existing_publication(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_run(
        workspace,
        _write_request(tmp_path / "first.json", "첫 번째 검토"),
    )
    first_a, first_b = _write_tracks(tmp_path / "first-tracks", first.run_id)
    finalize_review_run(
        workspace,
        first.run_id,
        first_a,
        first_b,
        publish=True,
    )

    second = prepare_review_run(
        workspace,
        _write_request(tmp_path / "second.json", "두 번째 검토"),
    )
    second_a, second_b = _write_tracks(tmp_path / "second-tracks", second.run_id)
    with pytest.raises(FileExistsError):
        finalize_review_run(
            workspace,
            second.run_id,
            second_a,
            second_b,
            publish=True,
        )


def test_prepare_rejects_invalid_request_before_creating_runs(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    request = _request()
    request["format"] = "invalid"
    request_path = tmp_path / "invalid.json"
    request_path.write_bytes(dump_bytes(request))

    with pytest.raises(ValueError, match="unsupported review-run request"):
        prepare_review_run(workspace, request_path)

    assert not (workspace / "runs").exists()


def test_prepare_rejects_unresolvable_citation_id_before_creating_runs(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    request = _request()
    evidence = request["evidence"]
    assert isinstance(evidence, list)
    citation = evidence[0]["citation"]
    assert isinstance(citation, dict)
    citation["citation_id"] = "CIT-DESCRIPTIVE-NAME"
    request_path = tmp_path / "invalid-citation.json"
    request_path.write_bytes(dump_bytes(request))

    with pytest.raises(
        ValueError,
        match="citation_id must equal CIT- followed by evidence_id",
    ):
        prepare_review_run(workspace, request_path)

    assert not (workspace / "runs").exists()


def test_finalize_requires_prepared_artifacts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    run_id = "RUN-0123456789ABCDEF0123"
    (workspace / "runs" / run_id).mkdir(parents=True)
    track_a, track_b = _write_tracks(tmp_path, run_id)

    with pytest.raises(FileNotFoundError):
        finalize_review_run(workspace, run_id, track_a, track_b)
