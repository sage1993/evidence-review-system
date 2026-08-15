from __future__ import annotations

import copy

import pytest

from evidence_review.contracts.question_plan import (
    MAX_ISSUES,
    MAX_LEGAL_ANCHORS,
    MAX_SEARCH_REQUESTS,
    decode_question_plan,
    question_plan_document,
)

QUESTION = (
    "산업집적활성화 및 공장설립에 관한 법률에 따라 기존 건축물을 신축하지 않고 "
    "지식산업센터로 운영할 때 제28조의2제1항에 따른 설립승인을 받을 수 있는지?"
)


def _valid_plan() -> dict[str, object]:
    return {
        "format": "evidence-review/question-plan",
        "version": 1,
        "original_question": QUESTION,
        "facts": [{"id": "F1", "text": "신축하지 않는다", "polarity": "negative"}],
        "assumptions": [
            {"id": "A1", "text": "구조·입주·시설 요건을 충족한다", "polarity": "positive"}
        ],
        "issues": [
            {"id": "I1", "question": "설립승인의 법정 요건은 무엇인가", "depends_on": []},
            {
                "id": "I2",
                "question": "기존 건축물 전환이 설립승인 대상이 되는가",
                "depends_on": ["I1"],
            },
        ],
        "legal_anchors": [
            {"text": "제28조의2제1항", "source": "user"},
            {"text": "산업집적법 시행령 제4조의6", "source": "planner"},
        ],
        "search_requests": [
            {
                "id": "S1",
                "issue_ids": ["I1"],
                "text": "지식산업센터 설립승인",
                "kind": "phrase",
                "source": "planner",
            },
            {
                "id": "S2",
                "issue_ids": ["I2"],
                "text": "제28조의2제1항",
                "kind": "legal_anchor",
                "source": "user",
            },
        ],
    }


def test_decode_question_plan_accepts_v1_and_encodes_canonically() -> None:
    raw = _valid_plan()
    raw["original_question"] = "  " + QUESTION.replace(" ", "   ") + "  "

    plan = decode_question_plan(raw, QUESTION)

    assert plan.original_question == QUESTION
    assert plan.facts[0].polarity == "negative"
    assert plan.issues[1].depends_on == ("I1",)
    assert question_plan_document(plan) == _valid_plan()


@pytest.mark.parametrize(
    "field",
    ["answer", "conclusion", "decision", "confidence", "status"],
)
def test_decode_question_plan_rejects_forbidden_or_unknown_top_level_fields(field: str) -> None:
    raw = _valid_plan()
    raw[field] = "forbidden"

    with pytest.raises(ValueError, match="unknown fields"):
        decode_question_plan(raw, QUESTION)


def test_decode_question_plan_rejects_unknown_nested_fields() -> None:
    raw = _valid_plan()
    search_requests = raw["search_requests"]
    assert isinstance(search_requests, list)
    search = search_requests[0]
    assert isinstance(search, dict)
    search["purpose"] = "not in v1 contract"

    with pytest.raises(ValueError, match="unknown fields"):
        decode_question_plan(raw, QUESTION)


@pytest.mark.parametrize(
    ("field", "limit", "factory"),
    [
        (
            "issues",
            MAX_ISSUES,
            lambda index: {"id": f"I{index}", "question": f"issue {index}", "depends_on": []},
        ),
        (
            "legal_anchors",
            MAX_LEGAL_ANCHORS,
            lambda index: {"text": f"planner anchor {index}", "source": "planner"},
        ),
        (
            "search_requests",
            MAX_SEARCH_REQUESTS,
            lambda index: {
                "id": f"S{index}",
                "issue_ids": ["I1"],
                "text": f"search {index}",
                "kind": "phrase",
                "source": "planner",
            },
        ),
    ],
)
def test_decode_question_plan_rejects_contract_bound_overflow(
    field: str, limit: int, factory: object
) -> None:
    raw = _valid_plan()
    make_item = factory
    assert callable(make_item)
    raw[field] = [make_item(index) for index in range(limit + 1)]

    with pytest.raises(ValueError, match="exceeds maximum"):
        decode_question_plan(raw, QUESTION)


@pytest.mark.parametrize("field", ["facts", "assumptions", "issues", "search_requests"])
def test_decode_question_plan_rejects_duplicate_ids(field: str) -> None:
    raw = _valid_plan()
    items = raw[field]
    assert isinstance(items, list)
    items.append(copy.deepcopy(items[0]))

    with pytest.raises(ValueError, match="duplicate id"):
        decode_question_plan(raw, QUESTION)


def test_decode_question_plan_rejects_fact_assumption_id_collision() -> None:
    raw = _valid_plan()
    assumptions = raw["assumptions"]
    assert isinstance(assumptions, list)
    assumption = assumptions[0]
    assert isinstance(assumption, dict)
    assumption["id"] = "F1"

    with pytest.raises(ValueError, match="facts and assumptions contain duplicate id"):
        decode_question_plan(raw, QUESTION)


def test_decode_question_plan_rejects_unknown_issue_reference() -> None:
    raw = _valid_plan()
    requests = raw["search_requests"]
    assert isinstance(requests, list)
    request = requests[0]
    assert isinstance(request, dict)
    request["issue_ids"] = ["I404"]

    with pytest.raises(ValueError, match="unknown issue"):
        decode_question_plan(raw, QUESTION)


def test_decode_question_plan_rejects_dependency_cycle() -> None:
    raw = _valid_plan()
    issues = raw["issues"]
    assert isinstance(issues, list)
    first = issues[0]
    assert isinstance(first, dict)
    first["depends_on"] = ["I2"]

    with pytest.raises(ValueError, match="dependency cycle"):
        decode_question_plan(raw, QUESTION)


def test_decode_question_plan_rejects_self_dependency() -> None:
    raw = _valid_plan()
    issues = raw["issues"]
    assert isinstance(issues, list)
    first = issues[0]
    assert isinstance(first, dict)
    first["depends_on"] = ["I1"]

    with pytest.raises(ValueError, match="must not depend on itself"):
        decode_question_plan(raw, QUESTION)


def test_decode_question_plan_rejects_duplicate_normalized_search_requests() -> None:
    raw = _valid_plan()
    requests = raw["search_requests"]
    assert isinstance(requests, list)
    requests.append(
        {
            "id": "S3",
            "issue_ids": ["I2"],
            "text": "  지식산업센터   설립승인 ",
            "kind": "phrase",
            "source": "planner",
        }
    )

    with pytest.raises(ValueError, match="duplicate normalized request"):
        decode_question_plan(raw, QUESTION)


def test_decode_question_plan_rejects_empty_search_text() -> None:
    raw = _valid_plan()
    requests = raw["search_requests"]
    assert isinstance(requests, list)
    request = requests[0]
    assert isinstance(request, dict)
    request["text"] = " \t\n "

    with pytest.raises(ValueError, match="must not be empty"):
        decode_question_plan(raw, QUESTION)


@pytest.mark.parametrize(
    ("path", "value", "match"),
    [
        (("facts", 0, "polarity"), "unknown", "unsupported"),
        (("legal_anchors", 0, "source"), "model", "unsupported"),
        (("search_requests", 0, "kind"), "keyword", "unsupported"),
        (("search_requests", 0, "source"), "system", "unsupported"),
    ],
)
def test_decode_question_plan_rejects_unsupported_literals(
    path: tuple[str, int, str], value: str, match: str
) -> None:
    raw = _valid_plan()
    collection = raw[path[0]]
    assert isinstance(collection, list)
    item = collection[path[1]]
    assert isinstance(item, dict)
    item[path[2]] = value

    with pytest.raises(ValueError, match=match):
        decode_question_plan(raw, QUESTION)


def test_decode_question_plan_matches_question_after_nfc_whitespace_normalization() -> None:
    expected = "가전제품 설치기준 알려줘"
    raw = _valid_plan()
    raw["original_question"] = "가전제품   설치기준\n알려줘"
    anchors = raw["legal_anchors"]
    assert isinstance(anchors, list)
    anchors.clear()

    plan = decode_question_plan(raw, expected)

    assert plan.original_question == expected


def test_decode_question_plan_rejects_original_question_mismatch() -> None:
    raw = _valid_plan()
    raw["original_question"] = "다른 질문"

    with pytest.raises(ValueError, match="does not match"):
        decode_question_plan(raw, QUESTION)


def test_decode_question_plan_rejects_user_anchor_not_in_question() -> None:
    raw = _valid_plan()
    anchors = raw["legal_anchors"]
    assert isinstance(anchors, list)
    anchors.append({"text": "제999조", "source": "user"})

    with pytest.raises(ValueError, match="not present"):
        decode_question_plan(raw, QUESTION)


def test_decode_question_plan_allows_planner_inferred_anchor_not_in_question() -> None:
    raw = _valid_plan()
    anchors = raw["legal_anchors"]
    assert isinstance(anchors, list)
    anchors.append({"text": "제999조", "source": "planner"})

    plan = decode_question_plan(raw, QUESTION)

    assert plan.legal_anchors[-1].source == "planner"


def test_decode_question_plan_rejects_dropped_user_numeric_literals() -> None:
    question = "역 승강장 경계에서 300m 떨어진 1,500㎡ 부지의 기준을 검토해줘"
    raw = {
        "format": "evidence-review/question-plan",
        "version": 1,
        "original_question": question,
        "facts": [],
        "assumptions": [],
        "issues": [{"id": "I1", "question": "부지 기준은 무엇인가", "depends_on": []}],
        "legal_anchors": [],
        "search_requests": [
            {
                "id": "S1",
                "issue_ids": ["I1"],
                "text": "부지 기준",
                "kind": "phrase",
                "source": "planner",
            }
        ],
    }

    with pytest.raises(ValueError, match="numeric literal"):
        decode_question_plan(raw, question)


def test_decode_question_plan_accepts_numeric_literals_preserved_in_structure() -> None:
    question = "역 승강장 경계에서 300m 떨어진 1,500㎡ 부지의 기준을 검토해줘"
    raw = {
        "format": "evidence-review/question-plan",
        "version": 1,
        "original_question": question,
        "facts": [
            {"id": "F1", "text": "역 승강장 경계에서 300m 떨어져 있다", "polarity": "positive"},
            {"id": "F2", "text": "부지 면적은 1500㎡이다", "polarity": "positive"},
        ],
        "assumptions": [],
        "issues": [{"id": "I1", "question": "부지 기준은 무엇인가", "depends_on": []}],
        "legal_anchors": [],
        "search_requests": [
            {
                "id": "S1",
                "issue_ids": ["I1"],
                "text": "부지 기준",
                "kind": "phrase",
                "source": "planner",
            }
        ],
    }

    plan = decode_question_plan(raw, question)

    assert [item.text for item in plan.facts] == [
        "역 승강장 경계에서 300m 떨어져 있다",
        "부지 면적은 1500㎡이다",
    ]
