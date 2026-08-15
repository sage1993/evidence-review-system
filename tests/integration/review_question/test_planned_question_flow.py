from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.planned_review_question import prepare_planned_review_question
from evidence_review.retrieval.index import build_fts_index

_FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "question_planner"
_CORPUS_PATH = _FIXTURE_ROOT / "issue_112_corpus.json"
_CASES_PATH = _FIXTURE_ROOT / "regression_questions.json"


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AssertionError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise AssertionError(f"{field} must be an array")
    return value


def _synthetic_snapshot() -> EvidenceSnapshot:
    corpus = _mapping(_load_json(_CORPUS_PATH), "corpus")
    elements_payload = _sequence(corpus.get("elements"), "corpus.elements")
    document_id = "DOC-QUESTION-PLANNER-SYNTHETIC"
    revision_id = "REV-QUESTION-PLANNER-SYNTHETIC"

    pages: list[dict[str, object]] = []
    elements: list[dict[str, object]] = []
    for index, item in enumerate(elements_payload):
        element = _mapping(item, f"corpus.elements[{index}]")
        evidence_id = element.get("id")
        text = element.get("text")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise AssertionError("synthetic evidence id must be a non-empty string")
        if not isinstance(text, str) or not text:
            raise AssertionError("synthetic evidence text must be a non-empty string")
        page_number = index + 1
        page_id = f"REV-QUESTION-PLANNER-SYNTHETIC-P{page_number:04d}"
        pages.append(
            {
                "id": page_id,
                "revision_id": revision_id,
                "page_number": page_number,
                "width": 595.0,
                "height": 842.0,
            }
        )
        elements.append(
            {
                "id": evidence_id,
                "revision_id": revision_id,
                "page_id": page_id,
                "page_number": page_number,
                "element_type": "clause",
                "raw_json": {"text": text},
                "raw_text": text,
                "normalized_text": text,
                "raw_payload_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "bbox": [10.0, 10.0, 500.0, 30.0],
                "parser_order": 0,
            }
        )

    return EvidenceSnapshot(
        documents=({"id": document_id, "title": "Synthetic question-planning corpus"},),
        revisions=(
            {
                "id": revision_id,
                "document_id": document_id,
                "source_hash": hashlib.sha256(b"synthetic-question-planning-corpus").hexdigest(),
                "byte_size": 1000,
                "page_count": len(pages),
            },
        ),
        pages=tuple(pages),
        elements=tuple(elements),
    )


def _workspace(path: Path) -> Path:
    evidence_directory = path / "evidence"
    evidence_directory.mkdir(parents=True)
    with EvidenceStore(evidence_directory / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _synthetic_snapshot())
        build_fts_index(store.require_connection())
    return path


def _cases() -> list[object]:
    payload = _mapping(_load_json(_CASES_PATH), "regression_cases")
    return _sequence(payload.get("cases"), "regression_cases.cases")


@pytest.mark.parametrize("raw_case", _cases(), ids=lambda item: str(item["id"]))
def test_planned_questions_retrieve_bounded_evidence_with_lineage(
    raw_case: object,
    tmp_path: Path,
) -> None:
    case = _mapping(raw_case, "case")
    case_id = case.get("id")
    question = case.get("question")
    raw_plan = case.get("plan")
    expected_ids = case.get("expected_evidence_ids")
    expected_issue_count = case.get("expected_issue_count")
    if not isinstance(case_id, str) or not isinstance(question, str):
        raise AssertionError("case id/question must be strings")
    if not isinstance(expected_ids, list) or not all(isinstance(item, str) for item in expected_ids):
        raise AssertionError("expected_evidence_ids must be an array of strings")
    if not isinstance(expected_issue_count, int):
        raise AssertionError("expected_issue_count must be an integer")

    plan = decode_question_plan(raw_plan, question)
    workspace = _workspace(tmp_path / case_id)
    prepared = prepare_planned_review_question(workspace, plan)
    run_directory = workspace / "runs" / prepared.run_id

    assert prepared.status == "WAITING_TRACK_A"
    assert prepared.retrieval_guidance_path is None
    assert len(plan.issues) == expected_issue_count
    assert 1 <= len(plan.search_requests) <= 24

    stored_plan = _mapping(_load_json(run_directory / "question-plan.json"), "stored_plan")
    assert stored_plan == raw_plan

    evidence_query = _mapping(_load_json(run_directory / "evidence-query.json"), "evidence_query")
    hit_values = _sequence(evidence_query.get("hits"), "evidence_query.hits")
    ordered_hits = [_mapping(item, "evidence_query.hit") for item in hit_values]
    hits = {hit["evidence_id"]: hit for hit in ordered_hits}
    assert set(expected_ids) <= set(hits)

    assert ordered_hits[0]["evidence_id"] in expected_ids
    precision_window = ordered_hits[: len(expected_ids) + 2]
    precision_ids = {hit["evidence_id"] for hit in precision_window}
    assert set(expected_ids) <= precision_ids

    planned_terms = {request.text: request.id for request in plan.search_requests}
    query_payload = _mapping(evidence_query.get("query"), "evidence_query.query")
    terms = _sequence(query_payload.get("terms"), "evidence_query.query.terms")
    llm_terms = {
        term["text"]: term
        for term in (_mapping(item, "query_term") for item in terms)
        if term.get("origin") == "llm"
    }
    assert set(planned_terms) <= set(llm_terms)

    matched_request_ids: set[str] = set()
    for evidence_id in expected_ids:
        matches = _sequence(hits[evidence_id].get("matches"), f"hits.{evidence_id}.matches")
        for raw_match in matches:
            match = _mapping(raw_match, "match")
            search_request_id = match.get("search_request_id")
            if isinstance(search_request_id, str):
                matched_request_ids.add(search_request_id)
    assert matched_request_ids
    assert matched_request_ids <= {request.id for request in plan.search_requests}

    track_a = _mapping(_load_json(run_directory / "track-a-bundle.json"), "track_a")
    inputs = _mapping(track_a.get("inputs"), "track_a.inputs")
    plan_projection = _mapping(inputs.get("question_plan"), "track_a.inputs.question_plan")
    issues = _sequence(plan_projection.get("issues"), "track_a.inputs.question_plan.issues")
    assert len(issues) == expected_issue_count
    assert inputs.get("question_plan_sha256")

    lineage_items = _sequence(
        inputs.get("retrieval_lineage"), "track_a.inputs.retrieval_lineage"
    )
    lineage_by_evidence = {
        item["evidence_id"]: item
        for item in (_mapping(value, "retrieval_lineage.item") for value in lineage_items)
    }
    assert set(expected_ids) <= set(lineage_by_evidence)
    for evidence_id in expected_ids:
        assert _sequence(
            lineage_by_evidence[evidence_id].get("matches"),
            f"retrieval_lineage.{evidence_id}.matches",
        )


def test_issue_112_corpus_does_not_contain_the_full_reproduction_question() -> None:
    reproduction = "에어컨 등 가전제품 설치기준 알려줘"
    corpus = _CORPUS_PATH.read_text(encoding="utf-8")

    assert reproduction not in corpus


def test_complex_cases_preserve_decision_changing_numbers_and_negation() -> None:
    cases = [_mapping(item, "case") for item in _cases()]
    by_id = {str(case["id"]): case for case in cases}

    c1_plan = _mapping(by_id["C1"]["plan"], "C1.plan")
    c1_facts = json.dumps(c1_plan["facts"], ensure_ascii=False)
    assert all(token in c1_facts for token in ("1,800㎡", "350m", "45%"))

    c2_plan = _mapping(by_id["C2"]["plan"], "C2.plan")
    c2_facts = json.dumps(c2_plan["facts"], ensure_ascii=False)
    assert "400%" in c2_facts

    c3_plan = _mapping(by_id["C3"]["plan"], "C3.plan")
    c3_facts = json.dumps(c3_plan["facts"], ensure_ascii=False)
    assert all(token in c3_facts for token in ("4,800㎡", "300m"))
    assert "분양주택 없이" in c3_facts
    assert "negative" in c3_facts
