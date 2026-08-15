"""QuestionPlan-bound review preparation using deterministic issue-aware retrieval."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.coverage import apply_issue_coverage_factors
from evidence_review.contracts.next_action import next_action_document
from evidence_review.contracts.question_plan import QuestionPlan, question_plan_document
from evidence_review.contracts.run_context import compute_run_id_from_request
from evidence_review.evidence.store import EvidenceStore
from evidence_review.issue_coverage_binding import bind_issue_coverage_to_review_request
from evidence_review.observability.run_metrics import append_stage, finish_stage, start_stage
from evidence_review.question_planning import (
    bind_question_plan_to_review_request,
    bind_retrieval_lineage_to_review_request,
    issue_retrieval_bundle_document,
    query_request_from_plan,
)
from evidence_review.retrieval.bundle import build_evidence_bundle
from evidence_review.retrieval.coverage import CoverageReport, evaluate_issue_coverage
from evidence_review.retrieval.graph import MissingReference
from evidence_review.retrieval.index import require_fresh_index
from evidence_review.retrieval.issue_bundle import IssueRetrievalBundle, retrieve_issue_bundle
from evidence_review.retrieval.reference_projection import (
    apply_reference_lineage_to_bundle_document,
)
from evidence_review.retrieval.trace import retrieval_trace_document
from evidence_review.review_question import (
    PreparedReviewQuestion,
    _evidence_database,
    _initialize_events,
    _mapping,
    _prepare_from_document,
    _resume_state,
    _track_a_action,
    _write_or_identical,
    build_review_run_request,
)


def _reference_missing_by_issue(
    bundle: IssueRetrievalBundle,
) -> dict[str, tuple[MissingReference, ...]]:
    grouped: dict[str, list[MissingReference]] = {}
    for item in bundle.reference_missing:
        grouped.setdefault(item.issue_id, []).append(item.reference)
    return {
        issue_id: tuple(values)
        for issue_id, values in sorted(grouped.items())
    }


def prepare_planned_review_question(
    workspace: Path,
    question_plan: QuestionPlan,
    user_expansions: Sequence[str] = (),
    *,
    calculations: Sequence[object] = (),
    rules: Sequence[object] = (),
    approved_rule_result_ids: Sequence[str] = (),
) -> PreparedReviewQuestion:
    """Retrieve and prepare a run whose identity is bound to a validated QuestionPlan.

    Normal planned runs use the issue-aware clause-first coordinator. Explicit
    legacy user expansion terms retain the prior retrieval path until those terms
    gain an issue-binding contract.
    """
    normalization_timer = start_stage()
    legacy_query_request = query_request_from_plan(
        question_plan,
        user_expansions=user_expansions,
    )
    normalization_metric = finish_stage("request-normalization", normalization_timer)

    coverage_report: CoverageReport | None = None
    trace_document: dict[str, object] | None = None
    retrieval_timer = start_stage()
    with EvidenceStore(_evidence_database(workspace)) as store:
        connection = store.require_connection()
        if user_expansions:
            bundle = build_evidence_bundle(connection, legacy_query_request)
        else:
            snapshot_hash = require_fresh_index(connection)
            issue_bundle = retrieve_issue_bundle(connection, question_plan)
            coverage_report = evaluate_issue_coverage(
                question_plan,
                issue_bundle,
                reference_missing_by_issue=_reference_missing_by_issue(issue_bundle),
            )
            bundle = issue_retrieval_bundle_document(
                question_plan,
                issue_bundle,
                snapshot_hash=snapshot_hash,
            )
            bundle = apply_reference_lineage_to_bundle_document(bundle, issue_bundle)
            trace_document = retrieval_trace_document(
                question_plan,
                issue_bundle,
                coverage_report,
            )
    retrieval_metric = finish_stage("retrieval", retrieval_timer)

    request_timer = start_stage()
    review_request = build_review_run_request(
        bundle,
        calculations=calculations,
        rules=rules,
        approved_rule_result_ids=approved_rule_result_ids,
    )
    review_request["question"] = question_plan.original_question
    review_request = bind_question_plan_to_review_request(review_request, question_plan)
    review_request = bind_retrieval_lineage_to_review_request(review_request, bundle)
    if coverage_report is not None:
        review_request = bind_issue_coverage_to_review_request(
            review_request,
            coverage_report,
        )
        review_request = apply_issue_coverage_factors(
            review_request,
            coverage_report,
        )
    request_metric = finish_stage("review-request-build", request_timer)

    run_id = compute_run_id_from_request(review_request)
    run_directory = workspace / "runs" / run_id
    resumed = run_directory.exists()
    prepare_timer = start_stage()
    if resumed:
        existing = run_directory / "review-request.json"
        if not existing.is_file() or existing.read_bytes() != dump_bytes(review_request):
            raise ValueError("existing immutable review run differs from question plan request")
        prepare_metric = finish_stage("prepare", prepare_timer, status="SKIPPED")
    else:
        _prepare_from_document(workspace, review_request)
        prepare_metric = finish_stage("prepare", prepare_timer)

    _write_or_identical(
        run_directory / "question-plan.json",
        question_plan_document(question_plan),
    )
    _write_or_identical(run_directory / "evidence-query.json", bundle)
    if trace_document is not None:
        _write_or_identical(run_directory / "retrieval-trace.json", trace_document)

    guidance_path: Path | None = None
    query_payload = _mapping(bundle["query"], "evidence_bundle.query")
    attempted = query_payload.get("attempted_terms", [])
    if not bundle["hits"] and attempted:
        guidance_path = run_directory / "retrieval-guidance.json"
        _write_or_identical(
            guidance_path,
            {
                "format": "evidence-review/retrieval-guidance",
                "version": 1,
                "query": query_payload["primary"],
                "attempted_terms": attempted,
                "authoritative_hit_count": 0,
            },
        )

    for metric in (
        normalization_metric,
        retrieval_metric,
        request_metric,
        prepare_metric,
    ):
        append_stage(run_directory, metric)

    if not resumed:
        _write_or_identical(
            run_directory / "next-action-track-a.json",
            next_action_document(_track_a_action(run_id)),
        )
        _initialize_events(run_directory)
    status, next_action_path = _resume_state(run_directory)
    return PreparedReviewQuestion(
        run_id=run_id,
        status=status,
        next_action_path=next_action_path,
        resumed=resumed,
        retrieval_guidance_path=guidance_path,
    )
