from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.codecs import decode_review_packet
from ansim_review.contracts.review_v2 import (
    ReviewPacketV2,
    decode_review_packet_v2,
    review_packet_v2_document,
)

FIXTURES = Path(__file__).parents[2] / "golden" / "contracts"


def _adapter() -> ModuleType:
    return importlib.import_module(
        "ansim_review.contracts.adapters.review_v1_to_v2"
    )


def _adapt_packet(packet_document: dict[str, object]) -> ReviewPacketV2:
    adapter = _adapter()
    packet = decode_review_packet(packet_document)
    adapted = adapter.adapt_review_packet_v1_to_v2(
        packet,
        case_id="CASE-LEGACY",
        snapshot_sha256="1" * 64,
        rule_manifest_sha256="2" * 64,
        formula_manifest_sha256="3" * 64,
    )
    assert isinstance(adapted, ReviewPacketV2)
    return adapted


def _adapt(name: str) -> ReviewPacketV2:
    document = json.loads((FIXTURES / name).read_bytes())
    assert isinstance(document, dict)
    return _adapt_packet(document)


def test_ready_v1_packet_adapts_without_inventing_drawing_evidence() -> None:
    adapted = _adapt("review-packet-v1-ready.json")
    document = review_packet_v2_document(adapted)

    assert document["format"] == "ansim/review-packet"
    assert document["version"] == 2
    assert document["finalizer_status"] == "READY_FOR_HUMAN_REVIEW"
    assert document["drawing_evidence"] == []
    assert document["confirmed_inputs"] == []
    assert document["evidence"] == []
    assert document["compatibility_source_version"] == 1
    assert document["human_decision"] is None


def test_abstain_v1_packet_preserves_abstention_reasons() -> None:
    adapted = _adapt("review-packet-v1-abstain.json")
    document = review_packet_v2_document(adapted)

    assert document["finalizer_status"] == "ABSTAIN"
    assert document["abstention_reasons"] == ["MISSING_REQUIRED_INPUT"]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("review-packet-v1-ready.json", "review-packet-v2-from-v1-ready.json"),
        ("review-packet-v1-abstain.json", "review-packet-v2-from-v1-abstain.json"),
    ],
)
def test_adapter_matches_canonical_golden_output(source: str, expected: str) -> None:
    actual = dump_bytes(review_packet_v2_document(_adapt(source)))
    assert actual == (FIXTURES / expected).read_bytes()


def test_adapter_output_is_byte_equivalent_across_repeated_runs() -> None:
    first = dump_bytes(
        review_packet_v2_document(_adapt("review-packet-v1-ready.json"))
    )
    second = dump_bytes(
        review_packet_v2_document(_adapt("review-packet-v1-ready.json"))
    )
    assert first == second


def test_compatibility_packet_preserves_legacy_numeric_tokens_without_invention() -> None:
    document = json.loads((FIXTURES / "review-packet-v1-ready.json").read_bytes())
    assert isinstance(document, dict)
    claims = document["claims"]
    assert isinstance(claims, list)
    claim = claims[0]
    assert isinstance(claim, dict)
    claim["numeric_tokens"] = ["8"]

    adapted_document = review_packet_v2_document(_adapt_packet(document))
    decoded = decode_review_packet_v2(adapted_document)

    assert decoded.claims[0].numeric_tokens == ("8",)
    assert decoded.evidence == ()
    assert decoded.compatibility_source_version == 1
