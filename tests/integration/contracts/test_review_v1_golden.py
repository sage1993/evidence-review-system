import json
from pathlib import Path

from ansim_review.abstention.finalizer import review_packet_document
from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.codecs import decode_review_packet
from ansim_review.contracts.review import ReviewPacket

FIXTURES = Path(__file__).parents[2] / "golden" / "contracts"


def test_v1_golden_packets_round_trip_byte_equivalent() -> None:
    for name in ("review-packet-v1-ready.json", "review-packet-v1-abstain.json"):
        raw = (FIXTURES / name).read_bytes()
        packet = decode_review_packet(json.loads(raw))
        assert dump_bytes(review_packet_document(packet)) == raw


def test_new_v1_packet_emits_lineage_fields_even_when_defaults_are_empty() -> None:
    packet = ReviewPacket(
        run_id="RUN-NEW",
        status="READY_FOR_HUMAN_REVIEW",
        human_decision=None,
        question="검토 질문",
        claims=(),
        calculations=(),
        rules=(),
        confidence=None,
        abstention_reasons=(),
    )

    document = review_packet_document(packet)

    assert "snapshot_sha256" in document
    assert document["snapshot_sha256"] is None
    assert "missing_inputs" in document
    assert document["missing_inputs"] == []