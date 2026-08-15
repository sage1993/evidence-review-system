from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.bundle import build_evidence_bundle
from evidence_review.retrieval.index import build_fts_index

_FIXTURE_DIR = (
    Path(__file__).parents[2] / "fixtures" / "real_review_retrieval_relevance"
)


def _load_json(name: str) -> dict[str, Any]:
    payload = json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _element(evidence_id: str, text: str, parser_order: int) -> dict[str, object]:
    hash_char = format(parser_order % 16, "x")
    return {
        "id": evidence_id,
        "revision_id": "REV-REAL-REVIEW",
        "page_id": "REV-REAL-REVIEW-P1",
        "page_number": 1,
        "element_type": "paragraph",
        "raw_json": {"text": text},
        "raw_text": text,
        "normalized_text": text,
        "raw_payload_hash": hash_char * 64,
        "bbox": [10.0, float(parser_order * 10), 500.0, float(parser_order * 10 + 8)],
        "parser_order": parser_order,
    }


def _snapshot(evidence_fixture: dict[str, Any]) -> EvidenceSnapshot:
    required = evidence_fixture["required"]
    forbidden = evidence_fixture["forbidden"]
    distractors = evidence_fixture["distractors"]
    assert isinstance(required, list)
    assert isinstance(forbidden, list)
    assert isinstance(distractors, list)

    records = [*required, *forbidden, *distractors]
    elements = tuple(
        _element(str(record["evidence_id"]), str(record["text"]), index)
        for index, record in enumerate(records, start=1)
    )
    clauses = tuple(
        {
            "id": str(record["clause_id"]),
            "revision_id": "REV-REAL-REVIEW",
            "title": str(record["title"]),
            "raw_text": str(record["text"]),
            "normalized_text": str(record["text"]),
            "review_status": "AUTOMATIC",
        }
        for record in required
    )
    return EvidenceSnapshot(
        documents=({"id": "DOC-REAL-REVIEW", "title": "안심주택 실제 검토 회귀 자료"},),
        revisions=(
            {
                "id": "REV-REAL-REVIEW",
                "document_id": "DOC-REAL-REVIEW",
                "source_hash": "a" * 64,
                "byte_size": 4096,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": "REV-REAL-REVIEW-P1",
                "revision_id": "REV-REAL-REVIEW",
                "page_number": 1,
                "width": 595.0,
                "height": 842.0,
            },
        ),
        elements=elements,
        clauses=clauses,
    )


def test_real_review_fixture_locks_seven_independent_issues() -> None:
    plan_payload = _load_json("question-plan.json")
    issue_payload = _load_json("expected-issues.json")
    original_question = plan_payload["original_question"]
    assert isinstance(original_question, str)

    plan = decode_question_plan(plan_payload, original_question)
    expected_issue_ids = {
        str(item["issue_id"])
        for item in issue_payload["issues"]
    }

    assert len(plan.issues) == 7
    assert {issue.id for issue in plan.issues} == expected_issue_ids
    assert {request.issue_ids[0] for request in plan.search_requests} == expected_issue_ids


def test_real_review_global_top_k_cannot_cover_all_required_issues(tmp_path: Path) -> None:
    plan_payload = _load_json("question-plan.json")
    evidence_fixture = _load_json("expected-evidence.json")
    original_question = plan_payload["original_question"]
    assert isinstance(original_question, str)

    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot(evidence_fixture))
        build_fts_index(store.require_connection())
        bundle = build_evidence_bundle(
            store.require_connection(),
            {
                "question": original_question,
                "synonym_manifest": {},
                "expansions": [],
                "limit": 5,
            },
        )

    hit_ids = {str(hit["evidence_id"]) for hit in bundle["hits"]}
    required_ids = {
        str(item["evidence_id"])
        for item in evidence_fixture["required"]
    }
    forbidden_ids = {
        str(item["evidence_id"])
        for item in evidence_fixture["forbidden"]
    }

    # RED by design on the current global Top-K implementation: seven independent
    # issue requirements cannot all survive a five-item globally fused result.
    assert required_ids <= hit_ids
    assert hit_ids.isdisjoint(forbidden_ids)
