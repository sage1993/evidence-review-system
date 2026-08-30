from __future__ import annotations

import json
from pathlib import Path

from evidence_review.contracts.question_plan import (
    QuestionFact,
    QuestionIssue,
    QuestionPlan,
    SearchRequest,
)
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.planned_review_question import prepare_planned_review_question
from evidence_review.retrieval.index import build_fts_index


def _plan() -> QuestionPlan:
    original = (
        "역 승강장 경계에서 300m 떨어진 1,500㎡ 부지에서 안심주택 사업을 "
        "추진할 수 있는가?"
    )
    return QuestionPlan(
        original_question=original,
        facts=(
            QuestionFact(
                id="F1",
                text="대상 부지는 역 승강장 경계에서 300m 떨어져 있다.",
                polarity="positive",
            ),
            QuestionFact(
                id="F2",
                text="대상 부지 면적은 1,500㎡이다.",
                polarity="positive",
            ),
        ),
        assumptions=(),
        issues=(
            QuestionIssue(
                id="I2",
                question=(
                    "역 승강장 경계에서 300m 떨어진 부지가 역세권 거리 기준을 "
                    "충족하거나 조건부 검토 대상이 되는가?"
                ),
                depends_on=(),
                required_evidence_roles=("rule",),
            ),
        ),
        legal_anchors=(),
        search_requests=(
            SearchRequest(
                id="S2",
                issue_ids=("I2",),
                text="역세권 승강장 경계 거리 기준",
                kind="concept_relation",
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
                documents=({"id": "DOC-1", "title": "안심주택 기준"},),
                revisions=(
                    {
                        "id": "REV-1",
                        "document_id": "DOC-1",
                        "source_hash": "a" * 64,
                        "byte_size": 20,
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
                        "id": "E-AREA",
                        "page_id": "P-1",
                        "element_type": "paragraph",
                        "raw_json": {"text": "사업대상지 최소 면적은 1,000㎡ 이상이다."},
                        "raw_text": "사업대상지 최소 면적은 1,000㎡ 이상이다.",
                        "normalized_text": "사업대상지 최소 면적은 1,000㎡ 이상이다.",
                        "raw_payload_hash": "b" * 64,
                        "bbox": [10.0, 40.0, 500.0, 60.0],
                        "parser_order": 1,
                    },
                    {
                        "id": "E-DIST",
                        "page_id": "P-1",
                        "element_type": "paragraph",
                        "raw_json": {
                            "text": (
                                "역세권 승강장 경계 거리 기준은 250m 이내를 원칙으로 "
                                "하며 통합심의를 거치는 경우 350m 이내까지 검토할 수 있다."
                            )
                        },
                        "raw_text": (
                            "역세권 승강장 경계 거리 기준은 250m 이내를 원칙으로 하며 "
                            "통합심의를 거치는 경우 350m 이내까지 검토할 수 있다."
                        ),
                        "normalized_text": (
                            "역세권 승강장 경계 거리 기준은 250m 이내를 원칙으로 하며 "
                            "통합심의를 거치는 경우 350m 이내까지 검토할 수 있다."
                        ),
                        "raw_payload_hash": "c" * 64,
                        "bbox": [10.0, 70.0, 500.0, 100.0],
                        "parser_order": 2,
                    },
                ),
                clauses=(
                    {
                        "id": "C-AREA",
                        "revision_id": "REV-1",
                        "title": "사업대상지 최소 면적",
                        "raw_text": "사업대상지 최소 면적은 1,000㎡ 이상이다.",
                        "normalized_text": "사업대상지 최소 면적은 1,000㎡ 이상이다.",
                        "review_status": "AUTOMATIC",
                    },
                    {
                        "id": "C-DIST",
                        "revision_id": "REV-1",
                        "title": "역세권 승강장 경계 거리 기준",
                        "raw_text": (
                            "역세권 승강장 경계 거리 기준은 250m 이내를 원칙으로 하며 "
                            "통합심의를 거치는 경우 350m 이내까지 검토할 수 있다."
                        ),
                        "normalized_text": (
                            "역세권 승강장 경계 거리 기준은 250m 이내를 원칙으로 하며 "
                            "통합심의를 거치는 경우 350m 이내까지 검토할 수 있다."
                        ),
                        "review_status": "AUTOMATIC",
                    },
                ),
                links=(
                    {
                        "id": "L-AREA",
                        "source_id": "C-AREA",
                        "target_id": "E-AREA",
                        "relation_type": "source_element",
                    },
                    {
                        "id": "L-DIST",
                        "source_id": "C-DIST",
                        "target_id": "E-DIST",
                        "relation_type": "source_element",
                    },
                ),
            ),
        )
        build_fts_index(store.require_connection())
    return workspace


def test_planned_review_persists_generated_facet_query_and_comparison_lineage(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)

    prepared = prepare_planned_review_question(workspace, _plan())
    run_directory = workspace / "runs" / prepared.run_id
    plan_document = json.loads(
        (run_directory / "question-plan.json").read_text(encoding="utf-8")
    )
    request = json.loads(
        (run_directory / "review-request.json").read_text(encoding="utf-8")
    )
    trace = json.loads(
        (run_directory / "retrieval-trace.json").read_text(encoding="utf-8")
    )

    request_ids = [item["id"] for item in plan_document["search_requests"]]
    assert request_ids == ["S2", "FACET-I2-minimum-area-threshold"]

    facet_coverage = request["inputs"]["facet_coverage"]
    assert facet_coverage == [
        {
            "issue_id": "I2",
            "covered_facet_ids": [
                "minimum-area-threshold",
                "distance-normal-threshold",
                "distance-conditional-threshold",
            ],
            "missing_facet_ids": [],
            "evidence_by_facet": [
                {"facet_id": "minimum-area-threshold", "evidence_ids": ["E-AREA"]},
                {"facet_id": "distance-normal-threshold", "evidence_ids": ["E-DIST"]},
                {
                    "facet_id": "distance-conditional-threshold",
                    "evidence_ids": ["E-DIST"],
                },
            ],
        }
    ]
    assert trace["issues"][0]["facet_coverage"] == facet_coverage

    comparisons = {
        item["facet_id"]: item
        for item in request["inputs"]["fact_rule_comparisons"]
        if item["issue_id"] == "I2"
    }
    assert set(comparisons) == {
        "minimum-area-threshold",
        "distance-normal-threshold",
        "distance-conditional-threshold",
    }
    assert comparisons["minimum-area-threshold"]["fact_value"] == "1500"
    assert comparisons["minimum-area-threshold"]["threshold_value"] == "1000"
    assert comparisons["minimum-area-threshold"]["satisfied"] is True
    assert comparisons["distance-normal-threshold"]["fact_value"] == "300"
    assert comparisons["distance-normal-threshold"]["threshold_value"] == "250"
    assert comparisons["distance-normal-threshold"]["satisfied"] is False
    assert comparisons["distance-conditional-threshold"]["threshold_value"] == "350"
    assert comparisons["distance-conditional-threshold"]["satisfied"] is True

    issue_coverage = request["inputs"]["issue_coverage"][0]
    assert issue_coverage["status"] == "CONDITIONAL"
    assert issue_coverage["covered_facet_ids"] == facet_coverage[0]["covered_facet_ids"]
    assert issue_coverage["missing_facet_ids"] == []
    assert set(issue_coverage["comparison_ids"]) == {
        item["comparison_id"] for item in comparisons.values()
    }
    assert {
        item["comparison_id"] for item in trace["issues"][0]["comparisons"]
    } == set(issue_coverage["comparison_ids"])
