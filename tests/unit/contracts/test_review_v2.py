from __future__ import annotations

import importlib
from types import ModuleType

import pytest


def _review_v2() -> ModuleType:
    try:
        return importlib.import_module("evidence_review.contracts.review_v2")
    except ModuleNotFoundError:
        pytest.fail("review packet v2 contract module is missing")


def _citation() -> dict[str, object]:
    return {
        "citation_id": "CIT-1",
        "document_id": "LAW1",
        "revision_id": "REV1",
        "page_number": 1,
        "evidence_id": "E1",
        "bbox": [1, 2, 3, 4],
        "source_hash": "a" * 64,
    }


def _payload() -> dict[str, object]:
    return {
        "format": "ansim/review-packet",
        "version": 2,
        "run_id": "RUN-1",
        "case_id": "CASE-1",
        "question": "도로 폭은 기준을 충족하는가?",
        "finalizer_status": "READY_FOR_HUMAN_REVIEW",
        "snapshot_sha256": "b" * 64,
        "rule_manifest_sha256": "c" * 64,
        "formula_manifest_sha256": "d" * 64,
        "claims": [
            {
                "claim_id": "CL-1",
                "text": "도로 폭은 8 m이다.",
                "citation_ids": ["CIT-1"],
                "numeric_tokens": ["8"],
                "issue_ids": [],
            }
        ],
        "evidence": [
            {
                "evidence_id": "E1",
                "citation": _citation(),
                "quote": "도로 폭 8 m",
                "numeric_tokens": ["8"],
            }
        ],
        "drawing_evidence": [],
        "confirmed_inputs": [],
        "calculations": [],
        "rule_evaluations": [],
        "exceptions": [],
        "conflicts": [],
        "confidence": None,
        "abstention_reasons": [],
        "human_decision": None,
        "compatibility_source_version": None,
    }


def test_v2_rejects_non_null_human_decision() -> None:
    review_v2 = _review_v2()
    payload = _payload()
    payload["human_decision"] = "SATISFIED"
    with pytest.raises(ValueError, match="human_decision must be null"):
        review_v2.decode_review_packet_v2(payload)


def test_v2_requires_explicit_human_decision_and_collections() -> None:
    review_v2 = _review_v2()
    for field in ("human_decision", "evidence", "drawing_evidence"):
        payload = _payload()
        del payload[field]
        with pytest.raises(ValueError, match=f"missing required fields: {field}"):
            review_v2.decode_review_packet_v2(payload)


def test_v2_requires_non_empty_case_id() -> None:
    review_v2 = _review_v2()
    payload = _payload()
    payload["case_id"] = ""
    with pytest.raises(ValueError, match="case_id must not be empty"):
        review_v2.decode_review_packet_v2(payload)


def test_v2_rejects_claim_without_citations() -> None:
    review_v2 = _review_v2()
    payload = _payload()
    claims = payload["claims"]
    assert isinstance(claims, list)
    claims[0]["citation_ids"] = []
    with pytest.raises(ValueError, match="claim must contain at least one citation"):
        review_v2.decode_review_packet_v2(payload)


def test_v2_rejects_unknown_fields() -> None:
    review_v2 = _review_v2()
    payload = _payload()
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        review_v2.decode_review_packet_v2(payload)


def test_v2_rejects_invalid_manifest_hash() -> None:
    review_v2 = _review_v2()
    payload = _payload()
    payload["rule_manifest_sha256"] = "invalid"
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        review_v2.decode_review_packet_v2(payload)


def test_v2_rejects_unregistered_numeric_token() -> None:
    review_v2 = _review_v2()
    payload = _payload()
    claims = payload["claims"]
    assert isinstance(claims, list)
    claims[0]["numeric_tokens"] = ["9"]
    with pytest.raises(ValueError, match="unregistered numeric token"):
        review_v2.decode_review_packet_v2(payload)


def test_v2_accepts_partially_resolved_finalizer_status() -> None:
    review_v2 = _review_v2()
    payload = _payload()
    payload["finalizer_status"] = "PARTIALLY_RESOLVED"

    packet = review_v2.decode_review_packet_v2(payload)

    assert packet.finalizer_status == "PARTIALLY_RESOLVED"


def test_v2_preserves_claim_issue_ids_through_document_round_trip() -> None:
    review_v2 = _review_v2()
    payload = _payload()
    claims = payload["claims"]
    assert isinstance(claims, list)
    claims[0]["issue_ids"] = ["I1", "I2"]

    packet = review_v2.decode_review_packet_v2(payload)
    document = review_v2.review_packet_v2_document(packet)

    document_claims = document["claims"]
    assert isinstance(document_claims, list)
    assert document_claims[0]["issue_ids"] == ["I1", "I2"]
    round_tripped = review_v2.decode_review_packet_v2(document)
    assert round_tripped.claims[0].issue_ids == ("I1", "I2")


def test_v2_document_round_trips() -> None:
    review_v2 = _review_v2()
    packet = review_v2.decode_review_packet_v2(_payload())
    expected = _payload()
    expected["format"] = "evidence-review/review-packet"
    assert review_v2.review_packet_v2_document(packet) == expected
