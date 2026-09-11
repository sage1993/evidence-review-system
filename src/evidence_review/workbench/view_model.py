"""Deterministic presentation data for the mutable ReviewMatter Workbench."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from evidence_review.navigation.models import NavigationResult
from evidence_review.review_matter.contracts import MatterIssue, ReviewMatter
from evidence_review.review_matter.formal_run_binding import FormalRunBinding

WorkbenchVerificationState = Literal["UNVERIFIED", "NEEDS_CONFIRMATION"]

_WORK_STATE_LABELS = {
    "DRAFT": "검토 초안",
    "OPEN": "검토 시작 전",
    "IN_PROGRESS": "검토 중",
    "NEEDS_EVIDENCE": "근거 필요",
    "READY_TO_FORMALIZE": "정식화 준비됨",
    "STALE": "재확인 필요",
    "BLOCKED": "차단됨",
}
_VERIFICATION_LABELS = {
    "UNVERIFIED": "미확인",
    "NEEDS_CONFIRMATION": "확인 필요",
}


@dataclass(frozen=True, slots=True)
class DraftObservation:
    """A non-authoritative reviewer note shown only as mutable draft work."""

    issue_id: str
    text: str
    verification_state: WorkbenchVerificationState
    draft_label: str = "검토 초안"
    source_label: str = "검토자 초안 메모"


@dataclass(frozen=True, slots=True)
class FormalRunHistory:
    """A pointer to a distinct Formal Review run, never a Human Decision."""

    run_id: str
    snapshot_id: str
    matter_revision: int
    stage_label: str


def draft_observations_from_matter(matter: ReviewMatter) -> tuple[DraftObservation, ...]:
    """Project persisted DRAFT issue questions as explicitly generated draft work."""
    return tuple(
        DraftObservation(
            issue_id=issue.issue_id,
            text=issue.question,
            verification_state="UNVERIFIED",
            draft_label="생성된 초안 작업 항목",
            source_label="MatterIssue 질문에서 결정론적으로 생성됨",
        )
        for issue in matter.issues
        if issue.work_state == "DRAFT"
    )


def formal_run_history_from_bindings(
    bindings: Sequence[FormalRunBinding],
) -> tuple[FormalRunHistory, ...]:
    """Project only exact, already-validated Formal Run bindings for display."""
    return tuple(
        FormalRunHistory(
            run_id=binding.run_id,
            snapshot_id=binding.snapshot_id,
            matter_revision=binding.matter_revision,
            stage_label="검증된 정식 검토 이력",
        )
        for binding in bindings
    )


def _issue_document(issue: MatterIssue) -> dict[str, object]:
    return {
        "issue_id": issue.issue_id,
        "question": issue.question,
        "work_state_label": _WORK_STATE_LABELS[issue.work_state],
        "recheck_required": issue.work_state == "STALE",
    }


def _binding_document(matter: ReviewMatter) -> list[dict[str, object]]:
    return [
        {
            "binding_id": binding.binding_id,
            "provenance": {
                "document_id": binding.document_id,
                "revision_id": binding.revision_id,
                "page_number": binding.page_number,
                "evidence_id": binding.evidence_id,
                "bbox": list(binding.bbox),
                "source_hash": binding.source_hash,
                "evidence_snapshot_hash": binding.evidence_snapshot_hash,
                "evidence_db_sha256": binding.evidence_db_sha256,
            },
        }
        for binding in matter.source_bindings
    ]


def _navigation_document(
    result: NavigationResult | None, matter: ReviewMatter
) -> dict[str, object] | None:
    if result is None:
        return None
    bound_provenance = {
        (binding.evidence_snapshot_hash, binding.evidence_db_sha256)
        for binding in matter.source_bindings
    }
    return {
        "query": result.query,
        "evidence_snapshot_hash": result.evidence_snapshot_hash,
        "evidence_db_sha256": result.evidence_db_sha256,
        "recheck_required": (
            result.evidence_snapshot_hash,
            result.evidence_db_sha256,
        ) not in bound_provenance,
        "promotion_label": "탐색 결과 — 정식 근거로 확정되지 않음",
        "hits": [
            {
                "citation_id": hit.citation.citation_id,
                "evidence_id": hit.evidence_id,
                "document_id": hit.document_id,
                "revision_id": hit.revision_id,
                "page_number": hit.page_number,
                "bbox": [
                    hit.bbox.left,
                    hit.bbox.bottom,
                    hit.bbox.right,
                    hit.bbox.top,
                ],
                "source_hash": hit.source_hash,
                "title": hit.title,
                "text": hit.text,
            }
            for hit in result.hits
        ],
    }


def _draft_documents(
    observations: Sequence[DraftObservation], matter: ReviewMatter
) -> list[dict[str, object]]:
    issue_ids = {issue.issue_id for issue in matter.issues}
    documents: list[dict[str, object]] = []
    for observation in observations:
        if observation.issue_id not in issue_ids:
            raise ValueError("draft observation references an unknown MatterIssue")
        documents.append(
            {
                "issue_id": observation.issue_id,
                "text": observation.text,
                "verification_label": _VERIFICATION_LABELS[
                    observation.verification_state
                ],
                "draft_label": observation.draft_label,
                "source_label": observation.source_label,
            }
        )
    return documents


def _formalize_document(matter: ReviewMatter) -> dict[str, object]:
    blockers = [
        {"issue_id": issue.issue_id, "label": _WORK_STATE_LABELS[issue.work_state]}
        for issue in matter.issues
        if issue.work_state != "READY_TO_FORMALIZE"
    ]
    if not matter.source_bindings:
        blockers.append({"issue_id": "", "label": "선택 근거 없음"})
    return {
        "expected_revision": matter.revision,
        "enabled": bool(matter.issues) and not blockers,
        "blockers": blockers,
        "confirmation_label": f"현재 Matter revision {matter.revision}을(를) 정식화",
    }


def build_workbench_view_model(
    matter: ReviewMatter,
    *,
    navigation_result: NavigationResult | None = None,
    draft_observations: Sequence[DraftObservation] = (),
    formal_run_history: Sequence[FormalRunHistory] = (),
) -> dict[str, object]:
    """Project mutable Matter work without importing Formal Review authority."""
    return {
        "surface": "workbench",
        "matter_id": matter.matter_id,
        "title": matter.title,
        "revision": matter.revision,
        "issues": [_issue_document(issue) for issue in matter.issues],
        "evidence": _binding_document(matter),
        "navigation": _navigation_document(navigation_result, matter),
        "draft_observations": _draft_documents(draft_observations, matter),
        "formal_run_history": [
            {
                "run_id": entry.run_id,
                "snapshot_id": entry.snapshot_id,
                "matter_revision": entry.matter_revision,
                "stage_label": entry.stage_label,
            }
            for entry in formal_run_history
        ],
        "formalize": _formalize_document(matter),
    }
