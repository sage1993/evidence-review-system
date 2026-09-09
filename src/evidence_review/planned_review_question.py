"""QuestionPlan-bound review preparation using deterministic issue-aware retrieval."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.case_visual import bind_case_visual_context_to_review_request
from evidence_review.confidence.coverage import apply_issue_coverage_factors
from evidence_review.contracts.attachments import ImmutableAttachment
from evidence_review.contracts.drawing import DrawingCandidate
from evidence_review.contracts.next_action import next_action_document
from evidence_review.contracts.question_plan import QuestionPlan, question_plan_document
from evidence_review.contracts.run_context import compute_run_id_from_request
from evidence_review.drawing_review.visual_pages import VisualPageAsset
from evidence_review.evidence.finalization import validate_finalized_evidence
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.filesystem_trust import verified_regular_directory
from evidence_review.issue_coverage_binding import bind_issue_coverage_to_review_request
from evidence_review.observability.run_metrics import append_stage, finish_stage, start_stage
from evidence_review.question_planning import (
    bind_question_plan_to_review_request,
    bind_retrieval_lineage_to_review_request,
    issue_retrieval_bundle_document,
)
from evidence_review.retrieval.coverage import evaluate_issue_coverage
from evidence_review.retrieval.facets import (
    augment_plan_with_facet_search_requests,
    bind_facet_coverage_to_review_request,
    evaluate_facet_coverage,
    facet_coverage_document,
)
from evidence_review.retrieval.index import require_fresh_index
from evidence_review.retrieval.issue_bundle import retrieve_issue_bundle
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
    _run_file,
    _track_a_action,
    _write_or_identical,
    build_review_run_request,
)
from evidence_review.rule_engine.fact_rule_comparison import (
    bind_comparisons_to_review_request,
    comparison_documents,
    conditional_issue_ids_from_comparisons,
    evaluate_fact_rule_comparisons,
)
from evidence_review.user_expansions import (
    apply_search_request_origins,
    plan_with_user_expansions,
)


def _prepare_review_scope(
    workspace: Path,
    question_plan: QuestionPlan,
    user_expansions: Sequence[str] = (),
    *,
    calculations: Sequence[object] = (),
    rules: Sequence[object] = (),
    approved_rule_result_ids: Sequence[str] = (),
    case_visual_attachments: Sequence[ImmutableAttachment] = (),
    drawing_candidates: Sequence[DrawingCandidate] = (),
    candidate_issue_ids: Mapping[str, Sequence[str]] | None = None,
    visual_page_assets: Sequence[VisualPageAsset] = (),
    visual_analysis_completed: bool = False,
    scope_origin: str = "PLANNER",
    scope_document: Mapping[str, object] | None = None,
) -> PreparedReviewQuestion:
    """Retrieve and prepare a run bound to an effective issue-aware QuestionPlan.

    Legacy CLI ``--expansion`` values remain supported, but each manual term is
    converted into an issue/role-bound SearchRequest before retrieval. Planned
    review never falls back to the legacy global retrieval path. Case-specific
    visual sources are bound under request inputs and never enter reference
    retrieval merely because a source is a PDF.
    """
    normalization_timer = start_stage()
    effective_plan = augment_plan_with_facet_search_requests(
        plan_with_user_expansions(question_plan, user_expansions)
    )
    normalization_metric = finish_stage("request-normalization", normalization_timer)

    retrieval_timer = start_stage()
    database = _evidence_database(workspace)
    with EvidenceStore(database, read_only=True) as store:
        connection = store.require_connection()
        validate_finalized_evidence(store)
        snapshot_hash = require_fresh_index(connection)
        issue_bundle = retrieve_issue_bundle(connection, effective_plan)
        facet_report = evaluate_facet_coverage(effective_plan, issue_bundle)
        fact_rule_comparisons = evaluate_fact_rule_comparisons(
            effective_plan,
            issue_bundle,
            facet_report,
        )
        coverage_report = evaluate_issue_coverage(
            effective_plan,
            issue_bundle,
            facet_report=facet_report,
            conditional_issue_ids=conditional_issue_ids_from_comparisons(
                fact_rule_comparisons,
                facet_report,
            ),
        )
        bundle = issue_retrieval_bundle_document(
            effective_plan,
            issue_bundle,
            snapshot_hash=snapshot_hash,
        )
        bundle = apply_reference_lineage_to_bundle_document(bundle, issue_bundle)
        bundle = apply_search_request_origins(bundle, effective_plan)
        facet_documents = facet_coverage_document(facet_report)
    provenance = finalized_evidence_provenance(database)
    bundle["snapshot_provenance"] = provenance
    trace_document = retrieval_trace_document(
        effective_plan,
        issue_bundle,
        coverage_report,
        snapshot_provenance=provenance,
        facet_coverage=facet_documents,
        comparisons=comparison_documents(fact_rule_comparisons),
    )
    retrieval_metric = finish_stage("retrieval", retrieval_timer)

    request_timer = start_stage()
    review_request = build_review_run_request(
        bundle,
        calculations=calculations,
        rules=rules,
        approved_rule_result_ids=approved_rule_result_ids,
    )
    review_request["question"] = effective_plan.original_question
    if scope_origin == "PLANNER":
        review_request = bind_question_plan_to_review_request(review_request, effective_plan)
    elif scope_origin == "EXPLICIT_USER":
        inputs_value = review_request.get("inputs")
        if not isinstance(inputs_value, dict):
            raise ValueError("review request inputs must be an object")
        inputs = dict(inputs_value)
        inputs["review_scope"] = dict(scope_document or {})
        review_request["inputs"] = inputs
    else:
        raise ValueError("unsupported ReviewScope origin")
    review_request = bind_retrieval_lineage_to_review_request(review_request, bundle)
    review_request = bind_issue_coverage_to_review_request(
        review_request,
        coverage_report,
    )
    review_request = bind_facet_coverage_to_review_request(
        review_request,
        facet_report,
    )
    review_request = bind_comparisons_to_review_request(
        review_request,
        fact_rule_comparisons,
        facet_report=facet_report,
    )
    review_request = apply_issue_coverage_factors(
        review_request,
        coverage_report,
    )
    review_request = bind_case_visual_context_to_review_request(
        review_request,
        case_visual_attachments,
        drawing_candidates,
        candidate_issue_ids=candidate_issue_ids,
        visual_page_assets=visual_page_assets,
        visual_analysis_completed=visual_analysis_completed,
    )
    request_metric = finish_stage("review-request-build", request_timer)

    run_id = compute_run_id_from_request(review_request)
    try:
        run_directory = verified_regular_directory(
            workspace / "runs" / run_id,
            field="run directory",
        )
    except FileNotFoundError:
        run_directory = workspace / "runs" / run_id
        resumed = False
    else:
        resumed = True
    prepare_timer = start_stage()
    if resumed:
        existing = _run_file(run_directory, "review-request.json")
        if existing.read_bytes() != dump_bytes(review_request):
            raise ValueError("existing immutable review run differs from question plan request")
        prepare_metric = finish_stage("prepare", prepare_timer, status="SKIPPED")
    else:
        _prepare_from_document(workspace, review_request)
        prepare_metric = finish_stage("prepare", prepare_timer)

    if scope_origin == "PLANNER":
        _write_or_identical(
            run_directory / "question-plan.json",
            question_plan_document(effective_plan),
        )
    else:
        _write_or_identical(run_directory / "review-scope.json", dict(scope_document or {}))
    _write_or_identical(run_directory / "evidence-query.json", bundle)
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
        run_directory=run_directory,
    )


def prepare_planned_review_question(
    workspace: Path,
    question_plan: QuestionPlan,
    user_expansions: Sequence[str] = (),
    *,
    calculations: Sequence[object] = (),
    rules: Sequence[object] = (),
    approved_rule_result_ids: Sequence[str] = (),
    case_visual_attachments: Sequence[ImmutableAttachment] = (),
    drawing_candidates: Sequence[DrawingCandidate] = (),
    candidate_issue_ids: Mapping[str, Sequence[str]] | None = None,
    visual_page_assets: Sequence[VisualPageAsset] = (),
    visual_analysis_completed: bool = False,
) -> PreparedReviewQuestion:
    """Compatibility adapter from a validated QuestionPlan to ReviewScope."""
    from evidence_review.review_matter.scope import review_scope_from_question_plan
    from evidence_review.scoped_review import prepare_scoped_review_question

    return prepare_scoped_review_question(
        workspace,
        review_scope_from_question_plan(question_plan),
        user_expansions,
        calculations=calculations,
        rules=rules,
        approved_rule_result_ids=approved_rule_result_ids,
        case_visual_attachments=case_visual_attachments,
        drawing_candidates=drawing_candidates,
        candidate_issue_ids=candidate_issue_ids,
        visual_page_assets=visual_page_assets,
        visual_analysis_completed=visual_analysis_completed,
    )
