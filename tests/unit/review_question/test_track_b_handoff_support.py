from __future__ import annotations

import json
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.review_run import prepare_review_run, submit_track_a


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
        "evidence": [
            {
                "citation": citation,
                "text": "주차장 설치 기준은 40%이다.",
            }
        ],
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


def _track_a(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "claims": [
            {
                "claim_id": "CL1",
                "text": "주차장 설치 기준은 40%이다.",
                "citation_ids": ["CIT-E1"],
                "numeric_tokens": ["40%"],
                "calculation_result_ids": [],
                "rule_references": [],
            }
        ],
        "citations": ["CIT-E1"],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "인용 근거를 독립 감사한다.",
    }


def _prepared(tmp_path: Path):
    request_path = tmp_path / "request.json"
    request_path.write_bytes(dump_bytes(_request()))
    return prepare_review_run(tmp_path / "workspace", request_path)


def test_track_b_next_action_points_to_audit_bundle_with_evidence_support(
    tmp_path: Path,
) -> None:
    prepared = _prepared(tmp_path)
    output = tmp_path / "track-a.json"
    output.write_bytes(dump_bytes(_track_a(prepared.run_id)))

    submitted = submit_track_a(
        tmp_path / "workspace",
        prepared.run_id,
        output,
    )

    next_action = json.loads(
        submitted.next_action_path.read_text(encoding="utf-8")
    )
    assert next_action["input_bundle"] == "track-b-bundle.json"

    bundle_path = prepared.run_directory / "track-b-bundle.json"
    assert bundle_path.is_file()
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert bundle["format"] == "evidence-review/track-b-bundle"
    assert bundle["version"] == 1
    assert bundle["run_id"] == prepared.run_id
    assert [item["claim_id"] for item in bundle["claims"]] == ["CL1"]
    assert bundle["evidence_support"] == [
        {
            "citation": {
                "citation_id": "CIT-E1",
                "document_id": "DOC1",
                "revision_id": "REV1",
                "page_number": 1,
                "evidence_id": "E1",
                "bbox": [0, 0, 10, 10],
                "source_hash": "a" * 64,
            },
            "text": "주차장 설치 기준은 40%이다.",
        }
    ]
