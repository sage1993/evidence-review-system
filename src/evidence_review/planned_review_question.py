"""QuestionPlan-bound review preparation using the existing deterministic runtime."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.next_action import next_action_document
from evidence_review.contracts.question_plan import QuestionPlan, question_plan_document
from evidence_review.contracts.run_context import compute_run_id_from_request
from evidence_review.evidence.store import EvidenceStore
from evidence_review.observability.run_metrics import append_stage, finish_stage, start_stage
from evidence_review.question_planning import (
    bind_question_plan_to_review_request,
    bind_retrieval_lineage_to_review_request,
    query_request_from_plan,
)
from evidence_review.retrieval.bundle import build_evidence_bundle
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


def prepare_planned_review_question(
    workspace: Path,
    question_plan: QuestionPlan,
    user_expansions: Sequence[str] = (),
    *,
    calculations: Sequence[object] = (),
    rules: Sequence[object] = (),
    approved_rule_result_ids: Sequence[str] = (),
) -> PreparedReviewQuestion:
    """Retrieve and prepare a run whose identity is bound to a validated QuestionPlan."""
    normalization_timer = start_stage()
    query_request = query_request_from_plan(
        question_plan,
        user_expansions=user_expansions,
    )
    normalization_metric = finish_stage("request-normalization", normalization_timer)

    retrieval_timer = start_stage()
    with EvidenceStore(_evidence_database(workspace)) as store:
        bundle = build_evidence_bundle(store.require_connection(), query_request)
    retrieval_metric = finish_stage("retrieval", retrieval_timer)

    request_timer = start_stage()
    review_request = build_review_run_request(
        bundle,
        calculations=calculations,
        rules=rules,
        approved_rule_result_ids=approved_rule_result_ids,
    )
    review_request = bind_question_plan_to_review_request(review_request, question_plan)
    review_request = bind_retrieval_lineage_to_review_request(review_request, bundle)
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
