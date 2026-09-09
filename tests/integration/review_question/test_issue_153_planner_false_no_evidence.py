from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evidence_review.contracts.question_plan import (
    QuestionPlan,
    decode_question_plan,
)
from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.planned_review_question import prepare_planned_review_question
from evidence_review.retrieval.fallback import search_clause_with_fallback

USER_QUESTION = "안심주택 최소 대지면적"
PLANNER_REQUEST = (
    "안심주택의 최소 대지면적 또는 대지면적 하한을 정하는 "
    "법령·조례·지침·기준 조항을 검색한다."
)
ABSENT_QUESTION = "잠수함 계류시설 최소 수심 기준"
ABSENT_PLANNER_REQUEST = (
    "잠수함 계류시설 최소 수심 기준을 정하는 "
    "법령·조례·지침·기준 조항을 검색한다."
)
HEADING_ONLY_QUESTION = "안심주택 검토"
HEADING_ONLY_PLANNER_REQUEST = "안심주택 법령·조례·지침·기준 조항을 검색한다."


def _plan(question: str, search_request: str) -> QuestionPlan:
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [],
            "assumptions": [],
            "issues": [
                {
                    "id": "I1",
                    "question": question,
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                }
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S1",
                    "issue_ids": ["I1"],
                    "text": search_request,
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                }
            ],
        },
        question,
    )


def _workspace(path: Path) -> Path:
    database_path = path / "evidence" / "evidence.sqlite"
    database_path.parent.mkdir(parents=True)
    document_id = "DOC-ISSUE-153"
    revision_id = "REV-ISSUE-153"
    page_id = "PAGE-ISSUE-153-1"
    clause_id = "CLAUSE-ISSUE-153"
    evidence_id = "EVIDENCE-ISSUE-153"
    evidence_text = "안심주택 최소 대지면적은 1,000㎡ 이상이어야 한다."
    snapshot = EvidenceSnapshot(
        documents=({"id": document_id, "title": "안심주택 기준"},),
        revisions=(
            {
                "id": revision_id,
                "document_id": document_id,
                "source_hash": hashlib.sha256(b"issue-153-corpus").hexdigest(),
                "byte_size": 100,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": page_id,
                "revision_id": revision_id,
                "page_number": 1,
                "width": 595.0,
                "height": 842.0,
            },
        ),
        elements=(
            {
                "id": evidence_id,
                "revision_id": revision_id,
                "page_id": page_id,
                "page_number": 1,
                "element_type": "clause",
                "raw_json": {"text": evidence_text},
                "raw_text": evidence_text,
                "normalized_text": evidence_text,
                "raw_payload_hash": hashlib.sha256(evidence_text.encode()).hexdigest(),
                "bbox": [10.0, 10.0, 500.0, 30.0],
                "parser_order": 0,
            },
        ),
        clauses=(
            {
                "id": clause_id,
                "revision_id": revision_id,
                "title": "안심주택 최소 대지면적",
                "raw_text": evidence_text,
                "normalized_text": evidence_text,
                "review_status": "AUTOMATIC",
            },
        ),
        links=(
            {
                "id": "LINK-ISSUE-153",
                "source_id": clause_id,
                "target_id": evidence_id,
                "relation_type": "source_element",
            },
        ),
    )
    with EvidenceStore(database_path, create=True) as store:
        ingest_snapshot(store, snapshot)
        finalize_evidence_database(store)
    return path


def _evidence_query(run_directory: Path) -> dict[str, object]:
    return json.loads((run_directory / "evidence-query.json").read_text(encoding="utf-8"))


def test_planner_sentence_does_not_drop_existing_bounded_evidence(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "positive")

    with EvidenceStore(workspace / "evidence" / "evidence.sqlite", read_only=True) as store:
        direct_result = search_clause_with_fallback(
            store.require_connection(),
            USER_QUESTION,
        )
    assert {hit.clause_id for hit in direct_result.hits} == {"CLAUSE-ISSUE-153"}

    prepared = prepare_planned_review_question(
        workspace,
        _plan(USER_QUESTION, PLANNER_REQUEST),
    )
    run_directory = workspace / "runs" / prepared.run_id
    evidence_query = _evidence_query(run_directory)
    assert prepared.retrieval_guidance_path is None
    assert evidence_query["hits"]
    assert any(
        match["retrieval_query"] == USER_QUESTION
        for hit in evidence_query["hits"]
        for match in hit["matches"]
    )


def test_genuine_absence_remains_no_evidence(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "negative")

    prepared = prepare_planned_review_question(
        workspace,
        _plan(ABSENT_QUESTION, ABSENT_PLANNER_REQUEST),
    )
    assert prepared.retrieval_guidance_path is not None

    run_directory = workspace / "runs" / prepared.run_id
    evidence_query = _evidence_query(run_directory)
    assert evidence_query["hits"] == []


def test_genuine_absence_with_shared_subject_remains_no_evidence(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "shared-subject-negative")
    question = "안심주택 잠수함 계류시설 최소 수심 기준"
    search_request = "안심주택의 잠수함 계류시설 최소 수심 기준을 검색한다."

    prepared = prepare_planned_review_question(workspace, _plan(question, search_request))

    assert prepared.retrieval_guidance_path is not None
    run_directory = workspace / "runs" / prepared.run_id
    evidence_query = _evidence_query(run_directory)
    assert evidence_query["hits"] == []


def test_planner_request_retains_heading_scoped_fallback(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "heading-scoped-positive")

    prepared = prepare_planned_review_question(
        workspace,
        _plan(HEADING_ONLY_QUESTION, HEADING_ONLY_PLANNER_REQUEST),
    )

    assert prepared.retrieval_guidance_path is None
    run_directory = workspace / "runs" / prepared.run_id
    evidence_query = _evidence_query(run_directory)
    assert evidence_query["hits"]
    assert any(
        match["query_text"] == HEADING_ONLY_PLANNER_REQUEST
        and match["fallback_stage"] == "HEADING_SCOPED"
        for hit in evidence_query["hits"]
        for match in hit["matches"]
    )
