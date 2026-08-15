from evidence_review.contracts.codecs import decode_review_packet


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
    assert packet.issue_results[1].gap_codes == ("RETRIEVAL_MISS",)
