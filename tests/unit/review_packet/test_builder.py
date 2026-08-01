import json
import sqlite3
from pathlib import Path

import pytest

from ansim_review.evidence.store import EvidenceStore
from ansim_review.review_packet.builder import build_review_view_model

V1_SCHEMA = Path("tests/fixtures/evidence/schema_v1.sql")


def _db(path: Path) -> None:
    with EvidenceStore(path, create=True) as store:
        connection = store.require_connection()
        connection.execute("INSERT INTO documents(id, title) VALUES('DOC1', 'Document')")
        connection.execute(
            """
            INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
            VALUES('REV1', 'DOC1', ?, 10, 3)
            """,
            ("a" * 64,),
        )
        connection.execute(
            """
            INSERT INTO pages(id, revision_id, page_number, width, height)
            VALUES('REV1-P3', 'REV1', 3, 120, 200)
            """
        )
        connection.execute(
            """
            INSERT INTO retrieval_records(
                evidence_id, evidence_type, document_id, revision_id, page_id,
                page_number, bbox_json, source_hash, title, raw_text,
                normalized_text
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "E1",
                "clause",
                "DOC1",
                "REV1",
                "REV1-P3",
                3,
                json.dumps([10, 20, 110, 40]),
                "a" * 64,
                "제3조",
                "정확한 인용문",
                "정규화",
            ),
        )
        connection.commit()


def _packet() -> dict[str, object]:
    return {
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


def test_view_model_resolves_all_required_sections_and_blank_decision(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    _db(database)
    model = build_review_view_model(_packet(), database)
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


def test_view_model_requires_explicit_v1_migration(tmp_path: Path) -> None:
    database = tmp_path / "evidence-v1.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(V1_SCHEMA.read_text(encoding="utf-8"))
    connection.close()

    with pytest.raises(RuntimeError, match="schema version 1"):
        build_review_view_model(_packet(), database)
