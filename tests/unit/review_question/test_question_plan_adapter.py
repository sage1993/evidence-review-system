from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.question_planning import (
    bind_question_plan_to_review_request,
    query_request_from_plan,
)
from evidence_review.retrieval.query import normalize_query


def _plan():
    question = "에어컨 등 가전제품 설치기준 알려줘"
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 1,
            "original_question": question,
            "facts": [],
            "assumptions": [],
            "issues": [
                {"id": "I1", "question": "에어컨 설치기준은 무엇인가", "depends_on": []},
                {"id": "I2", "question": "실외기 설치조건은 무엇인가", "depends_on": []},
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S1",
                    "issue_ids": ["I1"],
                    "text": "에어컨 설치기준",
                    "kind": "phrase",
                    "source": "planner",
                },
                {
                    "id": "S2",
                    "issue_ids": ["I2"],
                    "text": "에어컨 실외기 설치",
                    "kind": "phrase",
                    "source": "planner",
                },
            ],
        },
        question,
    )


def test_query_request_from_plan_preserves_planner_lineage_and_user_expansions() -> None:
    request = query_request_from_plan(_plan(), user_expansions=("별표 2",))

    assert request["question"] == "에어컨 설치기준"
    assert request["expansions"] == [
        {
            "text": "에어컨 설치기준",
            "origin": "llm",
            "search_request_ids": ["S1"],
            "issue_ids": ["I1"],
        },
        {
            "text": "에어컨 실외기 설치",
            "origin": "llm",
            "search_request_ids": ["S2"],
            "issue_ids": ["I2"],
        },
        {"text": "별표 2", "origin": "user"},
    ]


def test_user_duplicate_outranks_planner_but_retains_planner_lineage() -> None:
    request = query_request_from_plan(_plan(), user_expansions=("  에어컨   설치기준 ",))
    normalized = normalize_query(
        request["question"],
        request["expansions"],
        request["synonym_manifest"],
    )

    term = next(item for item in normalized.terms if item.text == "에어컨 설치기준")
    assert term.origin == "user"
    assert term.search_request_ids == ("S1",)
    assert term.issue_ids == ("I1",)


def test_lineage_merges_when_multiple_planner_requests_normalize_to_same_term() -> None:
    normalized = normalize_query(
        "질문",
        expansions=(
            {
                "text": "설치 기준",
                "origin": "llm",
                "search_request_ids": ["S2"],
                "issue_ids": ["I2"],
            },
            {
                "text": " 설치   기준 ",
                "origin": "llm",
                "search_request_ids": ["S1"],
                "issue_ids": ["I1"],
            },
        ),
        synonym_manifest={},
    )

    term = next(item for item in normalized.terms if item.text == "설치 기준")
    assert term.origin == "llm"
    assert term.search_request_ids == ("S1", "S2")
    assert term.issue_ids == ("I1", "I2")


def test_bind_question_plan_to_review_request_adds_replay_identity_and_issues() -> None:
    plan = _plan()
    request = {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": plan.original_question,
        "inputs": {"snapshot_hash": "a" * 64},
    }

    bound = bind_question_plan_to_review_request(request, plan)

    assert request["inputs"] == {"snapshot_hash": "a" * 64}
    inputs = bound["inputs"]
    assert isinstance(inputs, dict)
    assert inputs["snapshot_hash"] == "a" * 64
    assert len(inputs["question_plan_sha256"]) == 64
    assert inputs["question_plan"] == {
        "issues": [
            {"id": "I1", "question": "에어컨 설치기준은 무엇인가", "depends_on": []},
            {"id": "I2", "question": "실외기 설치조건은 무엇인가", "depends_on": []},
        ],
        "facts": [],
        "assumptions": [],
        "legal_anchors": [],
    }


def test_bind_question_plan_to_review_request_rejects_question_mismatch() -> None:
    plan = _plan()
    request = {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": "다른 질문",
        "inputs": {"snapshot_hash": "a" * 64},
    }

    try:
        bind_question_plan_to_review_request(request, plan)
    except ValueError as error:
        assert "question" in str(error)
    else:
        raise AssertionError("question mismatch accepted")
