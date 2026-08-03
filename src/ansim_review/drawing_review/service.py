"""Append-only application service for drawing annotation actions."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ansim_review.canonical_json import sha256_json
from ansim_review.contracts.drawing import (
    DrawingCandidate,
    DrawingConfirmation,
    geometry_document,
)
from ansim_review.drawing_review.actions import (
    AnnotationAction,
    ExistingCandidateAction,
    ManualCreateAction,
)
from ansim_review.drawing_review.view_model import (
    DrawingPage,
    build_drawing_review_view_model,
)
from ansim_review.parsing.drawing_candidates import (
    create_manual_candidate,
    load_candidate,
    persist_candidate,
)
from ansim_review.parsing.drawing_case import (
    CaseManifestEntry,
    case_artifact_path,
    validate_artifact_id,
)
from ansim_review.parsing.drawing_confirmation import persist_confirmation


@dataclass(frozen=True, slots=True)
class AnnotationActionResult:
    """New manifest entries produced by one append-only reviewer action."""

    candidate_entry: CaseManifestEntry | None
    confirmation_entry: CaseManifestEntry


def _verified_existing_candidate(
    case_dir: Path,
    candidate_id: str,
    entries: Mapping[str, CaseManifestEntry],
) -> DrawingCandidate:
    entry = entries.get(candidate_id)
    if entry is None:
        raise FileNotFoundError(f"candidate is not indexed: {candidate_id}")
    if entry.artifact_id != candidate_id:
        raise ValueError("candidate manifest identity mismatch")
    expected_path = f"candidates/{candidate_id}.json"
    if entry.relative_path != expected_path:
        raise ValueError("candidate manifest path mismatch")
    path = case_artifact_path(case_dir, entry.relative_path)
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        raise FileNotFoundError(f"candidate file is missing: {candidate_id}") from None
    if hashlib.sha256(payload).hexdigest() != entry.sha256:
        raise ValueError("candidate hash mismatch")
    return load_candidate(case_dir, candidate_id)


def _confirmation_id(
    candidate: DrawingCandidate,
    action: AnnotationAction,
) -> str:
    geometry = None if action.geometry is None else geometry_document(action.geometry)
    payload: dict[str, object] = {
        "candidate_id": candidate.candidate_id,
        "action": action.action,
        "reviewer": action.reviewer,
        "confirmed_at": action.confirmed_at,
        "confirmed_value": action.confirmed_value,
        "unit": action.unit,
        "geometry": geometry,
    }
    return f"CONF-{sha256_json(payload)[:24].upper()}"


def _reviewer_token(reviewer: str) -> str:
    digest = hashlib.sha256(reviewer.encode("utf-8")).hexdigest()[:20].upper()
    return f"REV-{digest}"


def _confirmation(
    candidate: DrawingCandidate,
    action: AnnotationAction,
) -> DrawingConfirmation:
    return DrawingConfirmation(
        confirmation_id=_confirmation_id(candidate, action),
        candidate_id=candidate.candidate_id,
        action=action.action,
        source_sha256=candidate.source_sha256,
        reviewer=action.reviewer,
        confirmed_at=action.confirmed_at,
        confirmed_value=action.confirmed_value,
        unit=action.unit,
        geometry=action.geometry,
    )


def _persist_action_confirmation(
    case_dir: Path,
    candidate: DrawingCandidate,
    action: AnnotationAction,
) -> CaseManifestEntry:
    return persist_confirmation(
        case_dir,
        _reviewer_token(action.reviewer),
        candidate,
        _confirmation(candidate, action),
    )


def _record_existing(
    case_dir: Path,
    page: DrawingPage,
    entries: Mapping[str, CaseManifestEntry],
    action: ExistingCandidateAction,
) -> AnnotationActionResult:
    candidate = _verified_existing_candidate(case_dir, action.candidate_id, entries)
    build_drawing_review_view_model(page, (candidate,))
    confirmation_entry = _persist_action_confirmation(case_dir, candidate, action)
    return AnnotationActionResult(
        candidate_entry=None,
        confirmation_entry=confirmation_entry,
    )


def _record_manual(
    case_dir: Path,
    page: DrawingPage,
    action: ManualCreateAction,
) -> AnnotationActionResult:
    case_id = validate_artifact_id(case_dir.name, "case_id")
    candidate = create_manual_candidate(
        case_id=case_id,
        source_sha256=page.source_sha256,
        page=page.page,
        annotation_id=action.annotation_id,
        candidate_type=action.candidate_type,
        geometry=action.geometry,
        raw_value=None,
        normalized_candidate=None,
    )
    build_drawing_review_view_model(page, (candidate,))
    candidate_entry = persist_candidate(case_dir, candidate)
    confirmation_entry = _persist_action_confirmation(case_dir, candidate, action)
    return AnnotationActionResult(
        candidate_entry=candidate_entry,
        confirmation_entry=confirmation_entry,
    )


def record_annotation_action(
    case_dir: Path,
    page: DrawingPage,
    candidate_entries: Mapping[str, CaseManifestEntry],
    action: AnnotationAction,
) -> AnnotationActionResult:
    """Record one action through existing create-only drawing repositories."""
    if isinstance(action, ExistingCandidateAction):
        return _record_existing(case_dir, page, candidate_entries, action)
    if isinstance(action, ManualCreateAction):
        return _record_manual(case_dir, page, action)
    raise TypeError("unsupported annotation action type")
