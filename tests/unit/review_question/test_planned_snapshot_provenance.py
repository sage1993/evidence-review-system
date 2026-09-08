from __future__ import annotations

import json
from pathlib import Path

from evidence_review.contracts.question_plan import (
    QuestionIssue,
    QuestionPlan,
    SearchRequest,
)
from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.planned_review_question import prepare_planned_review_question


def _plan() -> QuestionPlan:
    question = "주차장 설치기준은 무엇인가"
    return QuestionPlan(
        original_question=question,
        facts=(),
        assumptions=(),
        issues=(
            QuestionIssue(
                id="I1",
                question=question,
                depends_on=(),
                required_evidence_roles=("rule",),
            ),
        ),
        legal_anchors=(),
        search_requests=(
            SearchRequest(
                id="S1",
                issue_ids=("I1",),
                text="주차장 설치기준",
                kind="phrase",
                source="planner",
                role="rule",
            ),
        ),
    )


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    evidence_dir = workspace / "evidence"
    evidence_dir.mkdir(parents=True)
    with EvidenceStore(evidence_dir / "evidence.sqlite", create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-1", "title": "주차 기준"},),
                revisions=(
                    {
                        "id": "REV-1",
                        "document_id": "DOC-1",
                        "source_hash": "a" * 64,
                        "byte_size": 10,
                        "page_count": 1,
                    },
                ),
                pages=(
                    {
                        "id": "P-1",
                        "revision_id": "REV-1",
                        "page_number": 1,
                        "width": 600.0,
                        "height": 800.0,
                    },
                ),
                elements=(
                    {
                        "id": "E-1",
                        "page_id": "P-1",
                        "element_type": "paragraph",
                        "raw_json": {"text": "주차장 설치기준은 제13조에 따른다."},
                        "raw_text": "주차장 설치기준은 제13조에 따른다.",
                        "normalized_text": "주차장 설치기준은 제13조에 따른다.",
                        "raw_payload_hash": "b" * 64,
                        "bbox": [10.0, 10.0, 500.0, 30.0],
                        "parser_order": 1,
                    },
                ),
                clauses=(
                    {
                        "id": "C-1",
                        "revision_id": "REV-1",
                        "title": "제13조",
                        "raw_text": "주차장 설치기준은 제13조에 따른다.",
                        "normalized_text": "주차장 설치기준은 제13조에 따른다.",
                        "review_status": "AUTOMATIC",
                    },
                ),
                links=(
                    {
                        "id": "L-1",
                        "source_id": "C-1",
                        "target_id": "E-1",
                        "relation_type": "source_element",
                    },
                ),
            ),
        )
        finalize_evidence_database(store)
    return workspace


def test_planned_review_binds_same_snapshot_provenance_to_request_and_trace(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)

    prepared = prepare_planned_review_question(workspace, _plan())
    run_directory = workspace / "runs" / prepared.run_id
    request = json.loads(
        (run_directory / "review-request.json").read_text(encoding="utf-8")
    )
    trace = json.loads(
        (run_directory / "retrieval-trace.json").read_text(encoding="utf-8")
    )

    provenance = request["inputs"]["evidence_snapshot_provenance"]
    assert provenance["evidence_snapshot_hash"] == request["inputs"]["snapshot_hash"]
    assert len(provenance["evidence_db_sha256"]) == 64
    assert trace["snapshot_provenance"] == provenance
