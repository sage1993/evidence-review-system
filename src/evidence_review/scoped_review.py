"""Shared preparation boundary for planner and explicit ReviewScope inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from evidence_review.contracts.attachments import ImmutableAttachment
from evidence_review.contracts.drawing import DrawingCandidate
from evidence_review.drawing_review.visual_pages import VisualPageAsset
from evidence_review.review_matter.scope import (
    ReviewScope,
    decode_review_scope,
    question_plan_from_review_scope,
    review_scope_document,
)
from evidence_review.review_question import PreparedReviewQuestion


def prepare_scoped_review_question(
    workspace: Path,
    scope: ReviewScope,
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
    """Prepare one formal request from either planner or explicit scope."""
    if not isinstance(scope, ReviewScope):
        raise ValueError("scope must be a ReviewScope")
    validated_scope = decode_review_scope(review_scope_document(scope))
    from evidence_review.planned_review_question import _prepare_review_scope

    return _prepare_review_scope(
        workspace,
        question_plan_from_review_scope(validated_scope),
        user_expansions,
        calculations=calculations,
        rules=rules,
        approved_rule_result_ids=approved_rule_result_ids,
        case_visual_attachments=case_visual_attachments,
        drawing_candidates=drawing_candidates,
        candidate_issue_ids=candidate_issue_ids,
        visual_page_assets=visual_page_assets,
        visual_analysis_completed=visual_analysis_completed,
        scope_origin=validated_scope.origin,
        scope_document=review_scope_document(validated_scope),
    )
