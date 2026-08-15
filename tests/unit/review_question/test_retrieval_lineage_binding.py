from evidence_review.question_planning import bind_retrieval_lineage_to_review_request


def test_bind_retrieval_lineage_exposes_only_cited_planned_matches() -> None:
    request = {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": "질문",
        "inputs": {"snapshot_hash": "a" * 64},
    }
    bundle = {
        "hits": [
            {
                "evidence_id": "E2",
                "citation": {"citation_id": "C2"},
                "matches": [
                    {
                        "search_request_id": "S2",
                        "issue_ids": ["I2"],
                        "query_text": "실외기 설치",
                        "origin": "llm",
                    }
                ],
            },
            {
                "evidence_id": "E1",
                "citation": {"citation_id": "C1"},
                "matches": [
                    {
                        "search_request_id": "S1",
                        "issue_ids": ["I1"],
                        "query_text": "에어컨 설치기준",
                        "origin": "user",
                    }
                ],
            },
            {"evidence_id": "E3", "citation": {"citation_id": "C3"}},
        ]
    }

    bound = bind_retrieval_lineage_to_review_request(request, bundle)

    inputs = bound["inputs"]
    assert isinstance(inputs, dict)
    assert inputs["retrieval_lineage"] == [
        {
            "evidence_id": "E1",
            "citation_id": "C1",
            "matches": [
                {
                    "search_request_id": "S1",
                    "issue_ids": ["I1"],
                    "query_text": "에어컨 설치기준",
                    "origin": "user",
                }
            ],
        },
        {
            "evidence_id": "E2",
            "citation_id": "C2",
            "matches": [
                {
                    "search_request_id": "S2",
                    "issue_ids": ["I2"],
                    "query_text": "실외기 설치",
                    "origin": "llm",
                }
            ],
        },
    ]
    assert request["inputs"] == {"snapshot_hash": "a" * 64}
