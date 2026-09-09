from __future__ import annotations

from pathlib import Path

from evidence_review.contracts.question_plan import (
    QuestionFact,
    QuestionIssue,
    QuestionPlan,
    SearchRequest,
)
from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.planned_review_question import prepare_planned_review_question
from evidence_review.review_matter.scope import (
    build_explicit_review_scope,
    review_scope_document,
    review_scope_from_question_plan,
)
from evidence_review.scoped_review import prepare_scoped_review_question


def _plan() -> QuestionPlan:
    return QuestionPlan(
        original_question="Is the entrance wide enough?",
        facts=(QuestionFact("FACT-001", "entrance width", "positive"),),
        assumptions=(),
        issues=(QuestionIssue("ISSUE-001", "Is the entrance wide enough?", (), ("rule",)),),
        legal_anchors=(),
        search_requests=(
            SearchRequest(
                "SEARCH-001",
                ("ISSUE-001",),
                "entrance width",
                "phrase",
                "planner",
                "rule",
            ),
        ),
    )


def _workspace(root: Path) -> Path:
    evidence = root / "evidence" / "evidence.sqlite"
    evidence.parent.mkdir(parents=True)
    with EvidenceStore(evidence, create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-001", "title": "Reference"},),
                revisions=({
                    "id": "REV-001",
                    "document_id": "DOC-001",
                    "source_hash": "a" * 64,
                    "byte_size": 10,
                    "page_count": 1,
                },),
                pages=({
                    "id": "PAGE-001",
                    "revision_id": "REV-001",
                    "page_number": 1,
                    "width": 600.0,
                    "height": 800.0,
                },),
                elements=({
                    "id": "EVID-001",
                    "page_id": "PAGE-001",
                    "element_type": "paragraph",
                    "raw_json": {"text": "entrance width"},
                    "raw_text": "entrance width",
                    "normalized_text": "entrance width",
                    "raw_payload_hash": "d" * 64,
                    "bbox": [10.0, 10.0, 500.0, 30.0],
                    "parser_order": 0,
                },),
            ),
        )
        finalize_evidence_database(store)
    return root


def test_planner_adapter_and_scoped_path_produce_same_formal_request(
    tmp_path: Path,
) -> None:
    planner_workspace = _workspace(tmp_path / "planner")
    scoped_workspace = _workspace(tmp_path / "scoped")
    plan = _plan()

    planned = prepare_planned_review_question(planner_workspace, plan)
    scoped = prepare_scoped_review_question(
        scoped_workspace,
        review_scope_from_question_plan(plan),
    )

    assert (planned.run_id, planned.status) == (scoped.run_id, scoped.status)


def test_explicit_scope_does_not_create_planner_lineage(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "explicit")
    plan = _plan()
    scope = build_explicit_review_scope(
        question=plan.original_question,
        issues=plan.issues,
        facts=plan.facts,
        assumptions=plan.assumptions,
        legal_anchors=plan.legal_anchors,
        search_requests=plan.search_requests,
    )
    prepared = prepare_scoped_review_question(workspace, scope)
    assert prepared.run_directory is not None
    request = prepared.run_directory.joinpath("review-request.json").read_text(encoding="utf-8")
    assert "question_plan_sha256" not in request
    stored_scope = prepared.run_directory.joinpath("review-scope.json").read_text(encoding="utf-8")
    assert "EXPLICIT_USER" in stored_scope
    assert "review-scope" in str(review_scope_document(scope))
