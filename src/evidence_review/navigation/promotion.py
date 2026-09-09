"""Promotion of one validated navigation hit into Matter work state."""

from __future__ import annotations

import json
from decimal import Decimal
from math import isfinite
from pathlib import Path

from evidence_review.contracts.common import BBox, Citation
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.validation import expect_sha256
from evidence_review.evidence.finalization import validate_finalized_evidence
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.navigation.models import NavigationHit, NavigationResult
from evidence_review.review_matter.contracts import (
    MatterSourceBinding,
    matter_source_binding_document,
)
from evidence_review.review_matter.events import MatterEvent, append_matter_event
from evidence_review.review_matter.projection import MatterProjection
from evidence_review.review_matter.store import MatterRevisionConflict, MatterStore


def _stale() -> ValueError:
    return ValueError("NAVIGATION_RESULT_STALE")


def _binding_from_hit(result: NavigationResult, hit: NavigationHit) -> MatterSourceBinding:
    return MatterSourceBinding(
        binding_id=hit.evidence_id,
        document_id=hit.document_id,
        revision_id=hit.revision_id,
        page_number=hit.page_number,
        evidence_id=hit.evidence_id,
        bbox=(hit.bbox.left, hit.bbox.bottom, hit.bbox.right, hit.bbox.top),
        source_hash=hit.source_hash,
        evidence_snapshot_hash=result.evidence_snapshot_hash,
        evidence_db_sha256=result.evidence_db_sha256,
    )


def _current_retrieval_binding(database: Path, hit: NavigationHit) -> None:
    with EvidenceStore(database, read_only=True) as store:
        validate_finalized_evidence(store)
        row = store.require_connection().execute(
            """
            SELECT document_id, revision_id, page_number, bbox_json, source_hash
            FROM retrieval_records
            WHERE evidence_id = ?
            """,
            (hit.evidence_id,),
        ).fetchone()
    if row is None:
        raise _stale()
    try:
        bbox_payload = json.loads(str(row["bbox_json"]))
        if not isinstance(bbox_payload, list) or len(bbox_payload) != 4:
            raise ValueError("bbox")
        if any(
            isinstance(item, bool) or not isinstance(item, (int, float))
            for item in bbox_payload
        ):
            raise ValueError("bbox")
        bbox = BBox(*(float(item) for item in bbox_payload))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise _stale() from error
    if (
        str(row["document_id"]),
        str(row["revision_id"]),
        int(row["page_number"]),
        bbox,
        str(row["source_hash"]),
    ) != (
        hit.document_id,
        hit.revision_id,
        hit.page_number,
        hit.bbox,
        hit.source_hash,
    ):
        raise _stale()


def _validate_bbox(value: object) -> BBox:
    if not isinstance(value, BBox):
        raise _stale()
    coordinates = (value.left, value.bottom, value.right, value.top)
    if any(
        isinstance(coordinate, bool)
        or not isinstance(coordinate, (int, float))
        or not isfinite(coordinate)
        for coordinate in coordinates
    ):
        raise _stale()
    if value.left > value.right or value.bottom > value.top:
        raise _stale()
    return value


def _validate_identifier(value: object) -> str:
    try:
        return validate_identifier(value, "navigation result identifier")
    except ValueError as error:
        raise _stale() from error


def _validate_sha256(value: object) -> str:
    try:
        return expect_sha256(value, "navigation result hash")
    except ValueError as error:
        raise _stale() from error


def _validate_page_number(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _stale()
    return value


def _validate_hit(value: object) -> NavigationHit:
    if not isinstance(value, NavigationHit):
        raise _stale()
    evidence_id = _validate_identifier(getattr(value, "evidence_id", None))
    document_id = _validate_identifier(getattr(value, "document_id", None))
    revision_id = _validate_identifier(getattr(value, "revision_id", None))
    page_number = _validate_page_number(getattr(value, "page_number", None))
    bbox = _validate_bbox(getattr(value, "bbox", None))
    source_hash = _validate_sha256(getattr(value, "source_hash", None))
    title = getattr(value, "title", None)
    text = getattr(value, "text", None)
    score = getattr(value, "score", None)
    citation = getattr(value, "citation", None)
    if not isinstance(title, str) or not isinstance(text, str):
        raise _stale()
    if not isinstance(score, Decimal) or not score.is_finite():
        raise _stale()
    if not isinstance(citation, Citation):
        raise _stale()
    citation_id = getattr(citation, "citation_id", None)
    if citation_id != f"CIT-{evidence_id}":
        raise _stale()
    if (
        _validate_identifier(getattr(citation, "evidence_id", None)),
        _validate_identifier(getattr(citation, "document_id", None)),
        _validate_identifier(getattr(citation, "revision_id", None)),
        _validate_page_number(getattr(citation, "page_number", None)),
        _validate_bbox(getattr(citation, "bbox", None)),
        _validate_sha256(getattr(citation, "source_hash", None)),
    ) != (
        evidence_id,
        document_id,
        revision_id,
        page_number,
        bbox,
        source_hash,
    ):
        raise _stale()
    return value


def _validate_result(result: NavigationResult, evidence_id: str) -> NavigationHit:
    if not isinstance(result, NavigationResult):
        raise _stale()
    if not isinstance(getattr(result, "query", None), str) or not result.query.strip():
        raise _stale()
    _validate_sha256(getattr(result, "evidence_snapshot_hash", None))
    _validate_sha256(getattr(result, "evidence_db_sha256", None))
    hits = getattr(result, "hits", None)
    if not isinstance(hits, tuple):
        raise _stale()
    selected_evidence_id = _validate_identifier(evidence_id)
    validated_hits = tuple(_validate_hit(hit) for hit in hits)
    matches = tuple(
        hit for hit in validated_hits if hit.evidence_id == selected_evidence_id
    )
    if len(matches) != 1:
        raise _stale()
    return matches[0]


def promote_navigation_hit(
    store: MatterStore,
    *,
    matter_id: str,
    expected_revision: int,
    evidence_db: Path,
    navigation_result: NavigationResult,
    evidence_id: str,
) -> MatterProjection:
    """Atomically persist one current, exact navigation selection as Matter work."""
    current = store.load(matter_id)
    if current.revision != expected_revision:
        raise ValueError("MATTER_REVISION_CONFLICT")
    hit = _validate_result(navigation_result, evidence_id)
    database = Path(evidence_db)
    try:
        provenance = finalized_evidence_provenance(database)
        if (
            provenance["evidence_snapshot_hash"] != navigation_result.evidence_snapshot_hash
            or provenance["evidence_db_sha256"] != navigation_result.evidence_db_sha256
        ):
            raise _stale()
        bound = store.get_evidence_binding(matter_id)
        if bound is None or (
            bound["evidence_snapshot_hash"] != navigation_result.evidence_snapshot_hash
            or bound["evidence_db_sha256"] != navigation_result.evidence_db_sha256
            or bound["schema_version"] != provenance["schema_version"]
        ):
            raise _stale()
        _current_retrieval_binding(database, hit)
        if finalized_evidence_provenance(database) != provenance:
            raise _stale()
    except ValueError as error:
        if str(error) == "NAVIGATION_RESULT_STALE":
            raise
        raise _stale() from error
    except Exception as error:
        raise _stale() from error

    binding = _binding_from_hit(navigation_result, hit)
    same_id = next(
        (item for item in current.source_bindings if item.binding_id == binding.binding_id),
        None,
    )
    if same_id is not None:
        if same_id == binding:
            return MatterProjection(current)
        raise ValueError("EVIDENCE_SELECTED_BINDING_CONFLICT")
    if any(item.evidence_id == binding.evidence_id for item in current.source_bindings):
        raise ValueError("EVIDENCE_SELECTED_BINDING_CONFLICT")
    try:
        return append_matter_event(
            store,
            matter_id,
            expected_revision,
            MatterEvent(
                kind="EVIDENCE_SELECTED",
                payload={"source_binding": matter_source_binding_document(binding)},
            ),
        )
    except MatterRevisionConflict as error:
        raise ValueError("MATTER_REVISION_CONFLICT") from error
