from evidence_review.abstention.finalizer import review_packet_document
from evidence_review.contracts.codecs import decode_review_packet
from evidence_review.contracts.review import IssueResult, ReviewPacket


def test_review_packet_decodes_claim_issue_ids_and_issue_results() -> None:
    packet = decode_review_packet(
        {
            "run_id": "RUN-1",
            "status": "READY_FOR_HUMAN_REVIEW",
            "human_decision": None,
            "question": "복합 검토",
            "claims": [
                {
                    "claim_id": "CL-1",
                    "text": "근거 있음",
                    "citation_ids": ["CIT-1"],
                    "numeric_tokens": [],
                    "issue_ids": ["I1"],
                }
            ],
            "calculations": [],
            "rules": [],
            "confidence": None,
            "abstention_reasons": [],
            "snapshot_sha256": "a" * 64,
            "missing_inputs": ["I2 근거 부족"],
            "issue_results": [
                {
                    "issue_id": "I1",
                    "status": "RESOLVED",
                    "evidence_ids": ["E1"],
                    "covered_roles": ["rule"],
                    "missing_roles": [],
                    "gap_codes": [],
                    "covered_facet_ids": ["minimum-area-threshold"],
                    "missing_facet_ids": [],
                    "comparison_ids": ["CMP-123"],
                },
                {
                    "issue_id": "I2",
                    "status": "UNRESOLVED",
                    "evidence_ids": [],
                    "covered_roles": [],
                    "missing_roles": ["rule"],
                    "gap_codes": ["RETRIEVAL_MISS"],
                },
            ],
        }
    )

    assert packet.claims[0].issue_ids == ("I1",)
    assert packet.issue_results[0].status == "RESOLVED"
    assert packet.issue_results[0].covered_facet_ids == ("minimum-area-threshold",)
    assert packet.issue_results[0].missing_facet_ids == ()
    assert packet.issue_results[0].comparison_ids == ("CMP-123",)
    assert packet.issue_results[1].gap_codes == ("RETRIEVAL_MISS",)
    assert packet.issue_results[1].covered_facet_ids == ()
    assert packet.issue_results[1].comparison_ids == ()


def test_review_packet_serializes_optional_issue_lineage() -> None:
    packet = ReviewPacket(
        run_id="RUN-1",
        status="READY_FOR_HUMAN_REVIEW",
        human_decision=None,
        question="검토",
        claims=(),
        calculations=(),
        rules=(),
        confidence=None,
        abstention_reasons=(),
        issue_results=(
            IssueResult(
                issue_id="I2",
                status="CONDITIONAL",
                covered_facet_ids=("distance-normal-threshold",),
                missing_facet_ids=(),
                comparison_ids=("CMP-1",),
            ),
        ),
        _serialized_lineage_fields=("issue_results",),
    )

    document = review_packet_document(packet)
    assert document["issue_results"] == [
        {
            "issue_id": "I2",
            "status": "CONDITIONAL",
            "evidence_ids": [],
            "covered_roles": [],
            "missing_roles": [],
            "gap_codes": [],
            "covered_facet_ids": ["distance-normal-threshold"],
            "comparison_ids": ["CMP-1"],
        }
    ]
