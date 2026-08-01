import json
from pathlib import Path

from ansim_review.abstention.finalizer import review_packet_document
from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.codecs import decode_review_packet

FIXTURES = Path(__file__).parents[2] / "golden" / "contracts"


def test_v1_golden_packets_round_trip_byte_equivalent() -> None:
    for name in ("review-packet-v1-ready.json", "review-packet-v1-abstain.json"):
        raw = (FIXTURES / name).read_bytes()
        packet = decode_review_packet(json.loads(raw))
        assert dump_bytes(review_packet_document(packet)) == raw
