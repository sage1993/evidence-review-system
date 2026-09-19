import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_packet import builder
from evidence_review.review_packet.builder import build_review_view_model

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
        for element_id, text, bbox, parser_order in (
            ("E1", "정확한 인용문", [10, 20, 110, 40], 0),
            ("E2", "unused related citation", [20, 50, 100, 70], 1),
        ):
            connection.execute(
                """
                INSERT INTO elements(
                    id, page_id, element_type, raw_json, raw_text,
                    normalized_text, raw_payload_hash, bbox_json, parser_order
                ) VALUES(?, 'REV1-P3', 'paragraph', ?, ?, ?, ?, ?, ?)
                """,
                (
                    element_id,
                    json.dumps({"text": text}),
                    text,
                    text,
                    "a" * 64,
                    json.dumps(bbox),
                    parser_order,
                ),
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
        connection.execute(
            """
            INSERT INTO retrieval_records(
                evidence_id, evidence_type, document_id, revision_id, page_id,
                page_number, bbox_json, source_hash, title, raw_text,
                normalized_text
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "E2",
                "clause",
                "DOC1",
                "REV1",
                "REV1-P3",
                3,
                json.dumps([20, 50, 100, 70]),
                "a" * 64,
                "Section 3 related",
                "unused related citation",
                "unused related citation",
            ),
        )
        connection.execute(
            "INSERT INTO snapshot_meta(key, value) VALUES('snapshot_hash', ?)",
            ("a" * 64,),
        )
        connection.execute(
            "INSERT INTO retrieval_meta(key, value) VALUES('snapshot_hash', ?)",
            ("a" * 64,),
        )
        connection.commit()
        finalize_evidence_database(store)


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


def _v2_packet(database: Path | None = None) -> dict[str, object]:
    packet = _packet()
    packet.update(
        {
            "format": "evidence-review/review-packet",
            "version": 2,
            "case_id": "CASE-1",
            "finalizer_status": "ABSTAIN",
            "snapshot_sha256": "a" * 64,
            "rule_manifest_sha256": "b" * 64,
            "formula_manifest_sha256": "c" * 64,
            "evidence": [
                {
                    "evidence_id": "E1",
                    "citation": {
                        "citation_id": "CIT-E1",
                        "evidence_id": "E1",
                        "document_id": "DOC1",
                        "revision_id": "REV1",
                        "page_number": 3,
                        "bbox": [10, 20, 110, 40],
                        "source_hash": "a" * 64,
                    },
                    "quote": "정확한 인용문",
                    "numeric_tokens": [],
                }
            ],
            "drawing_evidence": [],
            "confirmed_inputs": [],
            "rule_evaluations": [],
            "exceptions": [],
            "conflicts": [],
        }
    )
    if database is not None:
        packet["snapshot_sha256"] = finalized_evidence_provenance(database)[
            "evidence_snapshot_hash"
        ]
    return packet


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
    assert citation["page_width"] == 120.0
    assert citation["page_height"] == 200.0
    assert citation["document_page_count"] == 3
    assert citation["reference"] == {
        "type": "TEXT",
        "table": None,
        "visual": None,
    }
    assert calculations[0]["display_result"] == "9.375%"
    assert rules[0]["rule_version"] == "1"
    assert confidence["factors"][0]["source"] == "evidence"
    assert model["exceptions"] == []
    assert model["conflicts"] == ["UNRESOLVED_CONFLICT"]
    assert model["abstention_reasons"] == ["UNRESOLVED_CONFLICT"]
    assert model["metadata"]["packet_sha256"] == hashlib.sha256(
        json.dumps(_packet(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert model["summary"]["citation_count"] == 1
    assert model["review_items"][0]["claim_id"] == "C1"
    assert model["decision"]["human_decision"] is None


def test_v2_citation_identity_ignores_projection_metadata_but_rejects_authority_change(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    _db(database)
    packet = _v2_packet(database)

    model = build_review_view_model(packet, database)

    citation = model["claims"][0]["citations"][0]
    assert citation["document_page_count"] == 3
    assert citation["reference"] == {
        "type": "TEXT",
        "table": None,
        "visual": None,
    }

    packet["evidence"][0]["citation"]["page_number"] = 2
    with pytest.raises(
        ValueError,
        match="citation identity does not match evidence database",
    ):
        build_review_view_model(packet, database)


def test_v2_packet_quote_is_display_authority(tmp_path: Path) -> None:
    database = tmp_path / "evidence.sqlite"
    _db(database)
    packet = _v2_packet(database)
    packet["evidence"][0]["quote"] = "PACKET QUOTE"

    model = build_review_view_model(packet, database)

    assert model["claims"][0]["citations"][0]["quote"] == "PACKET QUOTE"
    assert model["reference_citations"][0]["quote"] == "PACKET QUOTE"


def test_v2_packet_snapshot_must_match_evidence_database(tmp_path: Path) -> None:
    database = tmp_path / "evidence.sqlite"
    _db(database)
    packet = _v2_packet(database)
    packet["snapshot_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="snapshot does not match evidence database"):
        build_review_view_model(packet, database)


def test_v1_compatibility_does_not_require_packet_snapshot_match(tmp_path: Path) -> None:
    database = tmp_path / "evidence.sqlite"
    _db(database)
    packet = _packet()
    packet["snapshot_sha256"] = "f" * 64

    model = build_review_view_model(packet, database)

    assert model["claims"][0]["citations"][0]["quote"] == "정확한 인용문"


def test_view_model_projects_packet_missing_inputs_into_summary(tmp_path: Path) -> None:
    database = tmp_path / "evidence.sqlite"
    _db(database)
    packet = _packet()
    packet["snapshot_sha256"] = "a" * 64
    packet["missing_inputs"] = ["청소년문화의집 적용대상 확인"]
    packet["abstention_reasons"] = ["MISSING_REQUIRED_INPUT"]

    model = build_review_view_model(packet, database)

    assert model["summary"]["missing_input_count"] == 1
    assert model["metadata"]["snapshot_sha256"] == "a" * 64
    assert model["missing_inputs"] == ["청소년문화의집 적용대상 확인"]


def test_view_model_requires_explicit_v1_migration(tmp_path: Path) -> None:
    database = tmp_path / "evidence-v1.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(V1_SCHEMA.read_text(encoding="utf-8"))
    connection.close()

    with pytest.raises(RuntimeError, match="schema version 1"):
        build_review_view_model(_packet(), database)


def test_v2_exposes_resolved_reference_citations_in_deterministic_order(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    _db(database)
    packet = _v2_packet(database)
    evidence = packet["evidence"]
    assert isinstance(evidence, list)
    evidence.append(
        {
            "evidence_id": "E2",
            "citation": {
                "citation_id": "CIT-E2",
                "evidence_id": "E2",
                "document_id": "DOC1",
                "revision_id": "REV1",
                "page_number": 3,
                "bbox": [20, 50, 100, 70],
                "source_hash": "a" * 64,
            },
            "quote": "unused related citation",
            "numeric_tokens": [],
        }
    )

    model = build_review_view_model(packet, database)

    reference_citations = model["reference_citations"]
    assert [item["citation_id"] for item in reference_citations] == [
        "CIT-E1",
        "CIT-E2",
    ]
    related = next(
        item for item in reference_citations if item["citation_id"] == "CIT-E2"
    )
    assert related["document_page_count"] == 3
    assert related["reference"]["type"] == "TEXT"
    assert related["page_width"] == 120.0
    assert related["page_height"] == 200.0


def test_view_model_passes_verified_case_related_citations_to_visual_projection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence" / "evidence.sqlite"
    database.parent.mkdir(parents=True)
    _db(database)
    packet = _packet()
    run_dir = tmp_path / "runs" / packet["run_id"]
    run_dir.mkdir(parents=True)
    (run_dir / "track-a-bundle.json").write_text(
        json.dumps(
            {
                "evidence": [
                    {
                        "citation": {
                            "citation_id": "CIT-E2",
                            "evidence_id": "E2",
                            "document_id": "DOC1",
                            "revision_id": "REV1",
                            "page_number": 3,
                            "bbox": [20, 50, 100, 70],
                            "source_hash": "a" * 64,
                        },
                        "text": "unused related citation",
                        "issue_ids": ["I1"],
                        "role": "supporting_fact",
                    }
                ],
                "inputs": {"case_visual_context": {}},
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_projection(
        model: object,
        *,
        workspace_root: Path,
        supplemental_reference_citations: object,
    ) -> None:
        captured["workspace_root"] = workspace_root
        captured["supplemental_reference_citations"] = supplemental_reference_citations
        return None

    monkeypatch.setattr(builder, "build_case_visual_projection", fake_projection)

    builder.build_review_view_model(packet, database)

    supplemental = captured["supplemental_reference_citations"]
    assert isinstance(supplemental, list)
    assert [item["citation_id"] for item in supplemental] == ["CIT-E2"]
    assert supplemental[0]["quote"] == "unused related citation"
