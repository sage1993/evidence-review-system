from dataclasses import FrozenInstanceError

import pytest

from evidence_review.contracts.codecs import decode_citation, decode_review_packet


def _minimal_packet() -> dict[str, object]:
    return {
        "run_id": "RUN-0123456789ABCDEF0123",
        "status": "READY_FOR_HUMAN_REVIEW",
        "human_decision": None,
        "question": "대상지가 기준을 충족하는가?",
        "claims": [],
        "calculations": [],
        "rules": [],
        "confidence": None,
        "abstention_reasons": [],
    }


def test_machine_packet_rejects_decision() -> None:
    payload = _minimal_packet()
    payload["human_decision"] = "SATISFIED"

    with pytest.raises(ValueError, match="human_decision must be null"):
        decode_review_packet(payload)


def test_review_packet_is_frozen() -> None:
    packet = decode_review_packet(_minimal_packet())

    with pytest.raises(FrozenInstanceError):
        packet.status = "ABSTAIN"  # type: ignore[misc]


def test_unknown_finalizer_status_is_rejected() -> None:
    payload = _minimal_packet()
    payload["status"] = "DONE"

    with pytest.raises(ValueError, match="unsupported status"):
        decode_review_packet(payload)


def test_citation_decodes_resolved_source_identity() -> None:
    citation = decode_citation(
        {
            "citation_id": "C-1",
            "document_id": "LAW1",
            "revision_id": "LAW1-a1b2c3d4e5f6",
            "page_number": 3,
            "evidence_id": "LAW1-REV-P0003-E00001",
            "bbox": [10, 20, 30, 40],
            "source_hash": "a" * 64,
        }
    )

    assert citation.bbox.left == 10.0
    assert citation.page_number == 3


def test_boolean_page_number_is_rejected() -> None:
    with pytest.raises(ValueError, match="page_number must be an integer"):
        decode_citation(
            {
                "citation_id": "C-1",
                "document_id": "LAW1",
                "revision_id": "REV",
                "page_number": True,
                "evidence_id": "E1",
                "bbox": [0, 0, 1, 1],
                "source_hash": "a" * 64,
            }
        )
