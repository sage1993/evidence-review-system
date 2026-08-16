"""Deterministic retrieval decision trace for issue-aware review runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from evidence_review.contracts.question_plan import QuestionPlan
from evidence_review.retrieval.coverage import CoverageReport
from evidence_review.retrieval.graph import ReferencePath
from evidence_review.retrieval.issue_bundle import IssueRetrievalBundle


def _reference_path_document(path: ReferencePath) -> list[dict[str, object]]:
    return [
        {
            "source_id": step.source_id,
            "target_id": step.target_id,
            "relation_type": step.relation_type,
            "depth": step.depth,
        }
        for step in path.steps
    ]


def retrieval_trace_document(
    plan: QuestionPlan,
    bundle: IssueRetrievalBundle,
    coverage: CoverageReport,
    *,
    snapshot_provenance: Mapping[str, object] | None = None,
    relevance_decisions: Sequence[Mapping[str, object]] = (),
    facet_coverage: Sequence[Mapping[str, object]] = (),
    comparisons: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    coverage_by_issue = {item.issue_id: item for item in coverage.issues}
    plan_issue_ids = [item.id for item in plan.issues]
    if set(coverage_by_issue) != set(plan_issue_ids):
        raise ValueError("coverage issue ids must exactly match question plan issues")

    candidate_rank = {
        candidate.clause.clause_id: index
        for index, candidate in enumerate(bundle.candidates, start=1)
    }
    issue_documents: list[dict[str, object]] = []
    for issue in plan.issues:
        support = coverage_by_issue[issue.id]
        fallback: list[dict[str, object]] = []
        bundled_relevance: list[dict[str, object]] = []
        for item in bundle.fallback_traces:
            if item.issue_id != issue.id:
                continue
            decision_documents = [
                {
                    "clause_id": decision.clause_id,
                    "accepted": decision.accepted,
                    "reason_codes": list(decision.reason_codes),
                }
                for decision in item.relevance_decisions
            ]
            fallback.append(
                {
                    "search_request_id": item.search_request_id,
                    "role": item.role,
                    "stage": item.stage.value,
                    "input_query": item.input_query,
                    "derived_query": item.derived_query,
                    "hit_count": item.hit_count,
                    "relevance_decisions": decision_documents,
                }
            )
            bundled_relevance.extend(
                {
                    "search_request_id": item.search_request_id,
                    "stage": item.stage.value,
                    "clause_id": decision.clause_id,
                    "accepted": decision.accepted,
                    "reason_codes": list(decision.reason_codes),
                }
                for decision in item.relevance_decisions
            )
        candidates: list[dict[str, object]] = []
        for candidate in bundle.candidates:
            matches = [item for item in candidate.matches if item.issue_id == issue.id]
            if not matches:
                continue
            candidates.append(
                {
                    "clause_id": candidate.clause.clause_id,
                    "selection_rank": candidate_rank[candidate.clause.clause_id],
                    "raw_score": format(candidate.clause.score, "f"),
                    "kept": True,
                    "evidence_ids": [item.evidence_id for item in candidate.evidence],
                    "evidence_budget_limited": candidate.evidence_budget_limited,
                    "matches": [
                        {
                            "search_request_id": item.search_request_id,
                            "role": item.role,
                            "query_text": item.query_text,
                            "retrieval_query": item.retrieval_query,
                            "fallback_stage": item.fallback_stage.value,
                        }
                        for item in matches
                    ],
                }
            )
        references = [
            {
                "evidence_id": item.evidence_id,
                "search_request_id": item.search_request_id,
                "role": item.role,
                "source_evidence_id": item.source_evidence_id,
                "path": _reference_path_document(item.path),
            }
            for item in bundle.reference_matches
            if item.issue_id == issue.id
        ]
        missing_references = [
            {
                "source_id": item.reference.source_id,
                "target_id": item.reference.target_id,
                "relation_type": item.reference.relation_type,
                "depth": item.reference.depth,
                "reason_code": item.reference.reason_code,
            }
            for item in bundle.reference_missing
            if item.issue_id == issue.id
        ]
        budget_drops = [
            {
                "search_request_id": item.search_request_id,
                "reason": item.reason,
                "clause_id": item.clause_id,
                "evidence_id": item.evidence_id,
                "kept": False,
            }
            for item in bundle.budget_drops
            if item.issue_id == issue.id
        ]
        external_relevance = [
            dict(item)
            for item in relevance_decisions
            if item.get("issue_id") == issue.id
        ]
        issue_documents.append(
            {
                "issue_id": issue.id,
                "question": issue.question,
                "required_evidence_roles": list(issue.required_evidence_roles),
                "fallback_attempts": fallback,
                "candidates": candidates,
                "references": references,
                "missing_references": missing_references,
                "budget_drops": budget_drops,
                "relevance_decisions": [*bundled_relevance, *external_relevance],
                "facet_coverage": [
                    dict(item)
                    for item in facet_coverage
                    if item.get("issue_id") == issue.id
                ],
                "comparisons": [
                    dict(item)
                    for item in comparisons
                    if item.get("issue_id") == issue.id
                ],
                "coverage": {
                    "status": support.status,
                    "evidence_ids": list(support.evidence_ids),
                    "covered_roles": list(support.covered_roles),
                    "missing_roles": list(support.missing_roles),
                    "gap_codes": list(support.gap_codes),
                },
            }
        )

    selected_evidence = []
    for index, hit in enumerate(bundle.selected_evidence, start=1):
        citation = hit.citation()
        selected_evidence.append(
            {
                "selection_rank": index,
                "evidence_id": hit.evidence_id,
                "citation_id": citation.citation_id,
                "evidence_type": hit.evidence_type,
                "document_id": hit.document_id,
                "revision_id": hit.revision_id,
                "page_number": hit.page_number,
                "bbox": [
                    citation.bbox.left,
                    citation.bbox.bottom,
                    citation.bbox.right,
                    citation.bbox.top,
                ],
                "source_hash": hit.source_hash,
                "score": format(hit.final_score, "f"),
                "final_score": format(hit.final_score, "f"),
                "kept": True,
            }
        )

    document: dict[str, object] = {
        "format": "evidence-review/retrieval-trace",
        "version": 2,
        "question": plan.original_question,
        "issues": issue_documents,
        "selected_evidence": selected_evidence,
    }
    if snapshot_provenance is not None:
        document["snapshot_provenance"] = dict(snapshot_provenance)
    return document
