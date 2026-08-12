from __future__ import annotations

import pytest


def _bundle() -> dict[str, object]:
    return {
        "snapshot_hash": "a" * 64,
        "query": {
            "primary": "주차장 설치 기준",
            "terms": [
                {"text": "주차장 설치 기준", "origin": "primary"},
                {"text": "기숙사", "origin": "llm"},
            ],
        },
        "hits": [
            {
                "evidence_id": "E1",
                "text": "기숙사는 별표 2를 적용한다.",
                "citation": {
                    "citation_id": "CIT-E1",
                    "document_id": "DOC1",
                    "revision_id": "REV1",
                    "page_number": 5,
                    "evidence_id": "E1",
                    "bbox": [1, 2, 3, 4],
                    "source_hash": "b" * 64,
                },
            }
        ],
    }


def test_builder_converts_retrieval_bundle_without_losing_citation_identity() -> None:
    from ansim_review.review_question import build_review_run_request

    request = build_review_run_request(_bundle())

    assert request["format"] == "evidence-review/review-run-request"
    assert request["question"] == "주차장 설치 기준"
    assert request["evidence"] == [
        {
            "citation": {
                "citation_id": "CIT-E1",
                "document_id": "DOC1",
                "revision_id": "REV1",
                "page_number": 5,
                "evidence_id": "E1",
                "bbox": [1, 2, 3, 4],
                "source_hash": "b" * 64,
            },
            "text": "기숙사는 별표 2를 적용한다.",
        }
    ]
    assert request["inputs"] == {"snapshot_hash": "a" * 64}
    assert request["calculations"] == []
    assert request["rules"] == []


def test_builder_refuses_a_hit_without_a_traceable_citation() -> None:
    from ansim_review.review_question import build_review_run_request

    bundle = _bundle()
    bundle["hits"] = [{"evidence_id": "E1", "text": "근거"}]

    with pytest.raises(ValueError, match="traceable citation"):
        build_review_run_request(bundle)
