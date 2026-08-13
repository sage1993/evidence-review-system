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


def test_explicit_expansion_uses_user_origin_not_model_origin() -> None:
    from ansim_review.review_question import canonical_query_request

    request = canonical_query_request("주차장", ["별표 2"])

    assert request["expansions"] == [{"text": "별표 2", "origin": "user"}]


def test_builder_preserves_supplied_calculation_and_approved_rule_bindings() -> None:
    from ansim_review.review_question import build_review_run_request

    calculation = {
        "calculation_result_id": "CALC1",
        "status": "SUCCESS",
        "formula_id": "F1",
        "formula_version": "1.0.0",
        "inputs": {},
        "substitution": None,
        "raw_result": None,
        "display_result": None,
        "comparison": None,
        "formula_manifest_hash": "c" * 64,
        "result_hash": "d" * 64,
        "error_codes": [],
    }
    rule = {
        "rule_result_id": "RULE1",
        "rule_id": "R1",
        "rule_version": "1.0.0",
        "status": "SATISFIED",
        "citations": [],
        "missing_inputs": [],
        "calculation_result_ids": ["CALC1"],
        "reason_codes": [],
        "result_hash": "e" * 64,
    }

    request = build_review_run_request(
        _bundle(),
        calculations=[calculation],
        rules=[rule],
        approved_rule_result_ids=["RULE1"],
    )

    assert request["calculations"] == [calculation]
    assert request["rules"] == [rule]
    assert request["approved_rule_result_ids"] == ["RULE1"]


def test_builder_does_not_assign_full_confidence_to_zero_evidence() -> None:
    from ansim_review.review_question import build_review_run_request

    bundle = _bundle()
    bundle["hits"] = []

    request = build_review_run_request(bundle)
    factors = request["confidence_input"]["factors"]

    assert factors["source completeness"]["value"] == "0.0"
    assert factors["traceability"]["value"] == "0.0"
    assert factors["input completeness"]["value"] == "0.0"
    assert all(
        factor["source"] == "retrieval:evidence_availability"
        for factor in factors.values()
    )


def test_zero_evidence_only_reduces_evidence_dependent_factors() -> None:
    from ansim_review.review_question import build_review_run_request

    bundle = _bundle()
    bundle["hits"] = []

    request = build_review_run_request(bundle)
    factors = request["confidence_input"]["factors"]
    unaffected = {
        "parse quality",
        "human review status",
        "rule coverage",
        "calculation validity",
        "Track B agreement",
        "source freshness",
        "unresolved conflict factor",
    }

    assert {name for name, factor in factors.items() if factor["value"] == "0.0"} == {
        "source completeness",
        "traceability",
        "input completeness",
    }
    assert all(factors[name]["value"] == "1.0" for name in unaffected)


def test_builder_keeps_full_initial_confidence_for_traceable_evidence() -> None:
    from ansim_review.review_question import build_review_run_request

    request = build_review_run_request(_bundle())
    factors = request["confidence_input"]["factors"]

    assert all(factor["value"] == "1.0" for factor in factors.values())
    assert all(
        factor["source"] == "retrieval:evidence_availability"
        for factor in factors.values()
    )
