"""Validate external visual observations and project them to DrawingCandidate records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from evidence_review.canonical_json import sha256_json
from evidence_review.contracts.attachments import ImmutableAttachment
from evidence_review.contracts.drawing import DrawingCandidate
from evidence_review.contracts.question_plan import QuestionPlan
from evidence_review.contracts.visual_review import (
    decode_visual_analysis_output,
    visual_observation_document,
)
from evidence_review.drawing_review.view_model import DrawingPage, build_drawing_review_view_model
from evidence_review.drawing_review.visual_pages import VisualPageAsset
from evidence_review.parsing.drawing_candidates import extractor_candidate_id

_EXTRACTOR = "codex-visual-analysis"
_EXTRACTOR_VERSION = "1"


@dataclass(frozen=True, slots=True)
class ValidatedVisualAnalysis:
    """Validated drawing candidates and their QuestionPlan issue lineage."""

    candidates: tuple[DrawingCandidate, ...]
    candidate_issue_ids: Mapping[str, tuple[str, ...]]


def validate_visual_analysis_output(
    value: object,
    *,
    expected_visual_analysis_id: str,
    question_plan: QuestionPlan,
    attachments: tuple[ImmutableAttachment, ...],
    pages: tuple[VisualPageAsset, ...],
) -> ValidatedVisualAnalysis:
    """Fail closed on source/page/issue/geometry mismatches."""
    output = decode_visual_analysis_output(value)
    if output.visual_analysis_id != expected_visual_analysis_id:
        raise ValueError("visual_analysis_id does not match prepared handoff")
    attachments_by_id = {item.attachment_id: item for item in attachments}
    if len(attachments_by_id) != len(attachments):
        raise ValueError("visual attachments contain duplicate attachment_id")
    pages_by_key = {(item.attachment_id, item.page): item for item in pages}
    if len(pages_by_key) != len(pages):
        raise ValueError("visual page assets contain duplicate page identity")
    known_issues = {item.id for item in question_plan.issues}

    candidates: list[DrawingCandidate] = []
    lineage: dict[str, tuple[str, ...]] = {}
    for observation in output.observations:
        attachment = attachments_by_id.get(observation.attachment_id)
        if attachment is None:
            raise ValueError("visual observation references unknown attachment")
        if observation.source_sha256 != attachment.sha256:
            raise ValueError("visual observation source_sha256 mismatch")
        unknown_issues = sorted(set(observation.issue_ids) - known_issues)
        if unknown_issues:
            raise ValueError(
                "visual observation references unknown issue: " + unknown_issues[0]
            )
        page = pages_by_key.get((observation.attachment_id, observation.page))
        if page is None:
            raise ValueError("visual observation references unknown page")
        if attachment.case_id is None or attachment.case_id != page.case_id:
            raise ValueError("visual observation case_id mismatch")
        if observation.geometry.coordinate_system != page.coordinate_system:
            raise ValueError("visual observation coordinate system mismatch")

        observation_document = visual_observation_document(observation)
        element_id = f"OBS-{sha256_json(observation_document)[:20].upper()}"
        candidate = DrawingCandidate(
            candidate_id=extractor_candidate_id(
                attachment.case_id,
                observation.source_sha256,
                observation.page,
                _EXTRACTOR,
                _EXTRACTOR_VERSION,
                element_id,
            ),
            source_sha256=observation.source_sha256,
            page=observation.page,
            candidate_type=observation.candidate_type,
            origin="EXTRACTOR",
            status="UNCONFIRMED",
            geometry=observation.geometry,
            raw_value=observation.raw_value,
            normalized_candidate=observation.normalized_candidate,
            extractor=_EXTRACTOR,
            extractor_version=_EXTRACTOR_VERSION,
            annotation_id=None,
            case_id=attachment.case_id,
        )
        build_drawing_review_view_model(
            DrawingPage(
                source_sha256=page.source_sha256,
                page=page.page,
                coordinate_system=page.coordinate_system,
                width=page.width,
                height=page.height,
            ),
            (candidate,),
        )
        if candidate.candidate_id in lineage:
            raise ValueError("visual analysis contains duplicate observation identity")
        lineage[candidate.candidate_id] = tuple(sorted(observation.issue_ids))
        candidates.append(candidate)

    candidates.sort(key=lambda item: item.candidate_id)
    return ValidatedVisualAnalysis(
        candidates=tuple(candidates),
        candidate_issue_ids={key: lineage[key] for key in sorted(lineage)},
    )


__all__ = ["ValidatedVisualAnalysis", "validate_visual_analysis_output"]
