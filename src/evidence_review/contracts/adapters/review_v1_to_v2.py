"""Deterministically adapt frozen Review Packet v1 data into the v2 envelope."""

from __future__ import annotations

from evidence_review.contracts.formats import REVIEW_PACKET_FORMAT
from evidence_review.contracts.review import ReviewPacket
from evidence_review.contracts.review_v2 import ReviewPacketV2
from evidence_review.contracts.validation import expect_sha256, expect_string


def adapt_review_packet_v1_to_v2(
    packet: ReviewPacket,
    *,
    case_id: str,
    snapshot_sha256: str,
    rule_manifest_sha256: str,
    formula_manifest_sha256: str,
) -> ReviewPacketV2:
    """Wrap v1 machine output without inventing v2-only evidence or drawing data."""
    return ReviewPacketV2(
        format=REVIEW_PACKET_FORMAT,
        version=2,
        run_id=packet.run_id,
        case_id=expect_string(case_id, "case_id"),
        question=packet.question,
        finalizer_status=packet.status,
        snapshot_sha256=expect_sha256(snapshot_sha256, "snapshot_sha256"),
        rule_manifest_sha256=expect_sha256(
            rule_manifest_sha256, "rule_manifest_sha256"
        ),
        formula_manifest_sha256=expect_sha256(
            formula_manifest_sha256, "formula_manifest_sha256"
        ),
        claims=packet.claims,
        evidence=(),
        drawing_evidence=(),
        confirmed_inputs=(),
        calculations=packet.calculations,
        rule_evaluations=packet.rules,
        exceptions=(),
        conflicts=(),
        confidence=packet.confidence,
        abstention_reasons=packet.abstention_reasons,
        human_decision=None,
        compatibility_source_version=1,
    )
