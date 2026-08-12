from __future__ import annotations

from pathlib import Path

import pytest

from ansim_review.canonical_json import dump_bytes
from ansim_review.confidence.policy import FACTOR_WEIGHTS
from ansim_review.review_run import prepare_review_run


def _request() -> dict[str, object]:
    citation = {
        "citation_id": "CIT-E1",
        "document_id": "DOC1",
        "revision_id": "REV1",
        "page_number": 1,
        "evidence_id": "E1",
        "bbox": [0, 0, 10, 10],
        "source_hash": "a" * 64,
    }
    return {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": "주차장 설치 기준",
        "inputs": {},
        "evidence": [{"citation": citation, "text": "기준은 40%이다."}],
        "calculations": [],
        "rules": [],
        "approved_rule_result_ids": [],
        "confidence_input": {
            "factors": {
                name: {"value": "1.0", "source": "fixture"}
                for name in FACTOR_WEIGHTS
            }
        },
    }


def _track_a(run_id: str, *, numeric_tokens: list[str]) -> dict[str, object]:
    return {
        "run_id": run_id,
        "claims": [
            {
                "claim_id": "CL1",
                "text": "기준은 40%이다.",
                "citation_ids": ["CIT-E1"],
                "numeric_tokens": numeric_tokens,
                "calculation_result_ids": [],
                "rule_references": [],
            }
        ],
        "citations": ["CIT-E1"],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "근거를 정리한다.",
    }


def _prepared(tmp_path: Path):
    request_path = tmp_path / "request.json"
    request_path.write_bytes(dump_bytes(_request()))
    return prepare_review_run(tmp_path / "workspace", request_path)


def test_track_a_numeric_token_error_does_not_create_track_b_action(tmp_path: Path) -> None:
    from ansim_review.review_run import submit_track_a

    prepared = _prepared(tmp_path)
    output = tmp_path / "track-a.json"
    output.write_bytes(dump_bytes(_track_a(prepared.run_id, numeric_tokens=[])))

    with pytest.raises(ValueError, match="NUMERIC_TOKEN_MISMATCH"):
        submit_track_a(tmp_path / "workspace", prepared.run_id, output)

    assert not (prepared.run_directory / "next-action-track-b.json").exists()
    assert not (prepared.run_directory / "track-a-output.json").exists()


def test_valid_track_a_creates_only_track_b_handoff(tmp_path: Path) -> None:
    from ansim_review.review_run import submit_track_a

    prepared = _prepared(tmp_path)
    output = tmp_path / "track-a.json"
    output.write_bytes(dump_bytes(_track_a(prepared.run_id, numeric_tokens=["40%"])))

    result = submit_track_a(tmp_path / "workspace", prepared.run_id, output)

    assert result.next_action_path.name == "next-action-track-b.json"
    assert (prepared.run_directory / "track-a-output.json").read_bytes() == output.read_bytes()
