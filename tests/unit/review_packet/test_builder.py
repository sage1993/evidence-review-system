import json
import sqlite3
from pathlib import Path

from ansim_review.review_packet.builder import build_review_view_model


def _db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE retrieval_records (
          evidence_id TEXT PRIMARY KEY, evidence_type TEXT, document_id TEXT,
          revision_id TEXT, page_number INTEGER, bbox_json TEXT, source_hash TEXT,
          title TEXT, raw_text TEXT, normalized_text TEXT
        );
        CREATE TABLE visuals (
          id TEXT PRIMARY KEY, revision_id TEXT, page_number INTEGER, kind TEXT,
          relative_path TEXT, sha256 TEXT, bbox_json TEXT, duplicate_group TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO retrieval_records VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "E1",
            "clause",
            "DOC1",
            "REV1",
            3,
            json.dumps([10, 20, 110, 40]),
            "a" * 64,
            "제3조",
            "정확한 인용문",
            "정규화",
        ),
    )
    connection.commit()
    connection.close()


def test_view_model_resolves_all_required_sections_and_blank_decision(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    _db(database)
    packet = {
        "run_id": "RUN-0123456789ABCDEF0123",
        "status": "ABSTAIN",
        "human_decision": None,
        "question": "검토 질문",
        "claims": [
            {
                "claim_id": "C1",
                "text": "LLM 설명",
                "citation_ids": ["CIT-E1"],
                "numeric_tokens": [],
            }
        ],
        "calculations": [
            {
                "calculation_result_id": "CAL1",
                "status": "SUCCESS",
                "formula_id": "RATIO",
                "formula_version": "1",
                "inputs": {},
                "substitution": "30/320",
                "raw_result": "0.09375",
                "display_result": "9.375%",
                "comparison": "BELOW_THRESHOLD",
                "formula_manifest_hash": "b" * 64,
                "result_hash": "c" * 64,
                "error_codes": [],
            }
        ],
        "rules": [
            {
                "rule_result_id": "RR1",
                "rule_id": "RULE1",
                "rule_version": "1",
                "status": "NOT_SATISFIED",
                "citations": [],
                "missing_inputs": [],
                "calculation_result_ids": ["CAL1"],
                "reason_codes": [],
                "result_hash": "d" * 64,
            }
        ],
        "confidence": {
            "policy_version": "1",
            "score": "0.6500",
            "level": "LOW",
            "factors": [
                {
                    "name": "traceability",
                    "value": "1.0000",
                    "weight": "0.15",
                    "contribution": "0.1500",
                    "source": "evidence",
                }
            ],
            "hard_gate_failures": ["UNRESOLVED_CONFLICT"],
        },
        "abstention_reasons": ["UNRESOLVED_CONFLICT"],
    }
    model = build_review_view_model(packet, database)
    claims = model["claims"]
    calculations = model["calculations"]
    rules = model["rules"]
    confidence = model["confidence"]
    assert isinstance(claims, list)
    assert isinstance(calculations, list)
    assert isinstance(rules, list)
    assert isinstance(confidence, dict)
    assert model["human_decision"] is None
    assert model["decision_options"] == []
    citation = claims[0]["citations"][0]
    assert citation["quote"] == "정확한 인용문"
    assert citation["document_id"] == "DOC1"
    assert citation["page_number"] == 3
    assert citation["bbox"] == [10.0, 20.0, 110.0, 40.0]
    assert calculations[0]["display_result"] == "9.375%"
    assert rules[0]["rule_version"] == "1"
    assert confidence["factors"][0]["source"] == "evidence"
    assert model["exceptions"] == []
    assert model["conflicts"] == ["UNRESOLVED_CONFLICT"]
    assert model["abstention_reasons"] == ["UNRESOLVED_CONFLICT"]
