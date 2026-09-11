"""Exact, non-authoritative Matter-to-visual-case lineage boundary."""

from __future__ import annotations

from dataclasses import dataclass

from evidence_review.case_visual import VisualCase, visual_case_from_attachments
from evidence_review.contracts.drawing import (
    DrawingCandidate,
    decode_drawing_candidate,
    drawing_candidate_document,
)
from evidence_review.review_matter.store import MatterRevisionConflict, MatterStore


@dataclass(frozen=True, slots=True)
class VisualAttachmentBinding:
    """One exact visual attachment identity retained for Matter work."""

    attachment_id: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class VisualMatterBinding:
    """A revision-pinned visual context; not evidence or confirmation authority."""

    matter_id: str
    matter_revision: int
    visual_case: VisualCase
    attachments: tuple[VisualAttachmentBinding, ...]
    candidates: tuple[DrawingCandidate, ...]


def bind_visual_case_to_matter(
    store: MatterStore,
    *,
    matter_id: str,
    expected_revision: int,
    visual_case: VisualCase,
    candidates: tuple[DrawingCandidate, ...] = (),
) -> VisualMatterBinding:
    """Validate an exact visual case for one unchanged Matter revision.

    This boundary deliberately creates no candidate confirmation or promoted input.
    """
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise ValueError("expected_revision is required")
    matter = store.load(matter_id)
    if matter.revision != expected_revision:
        raise MatterRevisionConflict("MATTER_REVISION_CONFLICT")
    if not isinstance(visual_case, VisualCase):
        raise ValueError("VISUAL_SOURCE_BINDING_MISMATCH")
    try:
        validated_case = visual_case_from_attachments(visual_case.attachments)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("VISUAL_SOURCE_BINDING_MISMATCH") from error
    if validated_case.case_id != visual_case.case_id:
        raise ValueError("VISUAL_SOURCE_BINDING_MISMATCH")

    source_hashes = {item.sha256 for item in validated_case.attachments}
    validated_candidates = tuple(
        decode_drawing_candidate(drawing_candidate_document(item))
        for item in candidates
    )
    candidate_ids = [item.candidate_id for item in validated_candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("VISUAL_SOURCE_BINDING_MISMATCH")
    if any(
        item.case_id != validated_case.case_id
        or item.source_sha256 not in source_hashes
        for item in validated_candidates
    ):
        raise ValueError("VISUAL_SOURCE_BINDING_MISMATCH")

    return VisualMatterBinding(
        matter_id=matter.matter_id,
        matter_revision=matter.revision,
        visual_case=validated_case,
        attachments=tuple(
            VisualAttachmentBinding(
                attachment_id=item.attachment_id,
                source_sha256=item.sha256,
            )
            for item in validated_case.attachments
        ),
        candidates=validated_candidates,
    )


__all__ = [
    "VisualAttachmentBinding",
    "VisualMatterBinding",
    "bind_visual_case_to_matter",
]
