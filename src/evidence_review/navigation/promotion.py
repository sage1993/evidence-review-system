"""Explicit, revalidated promotion from navigation into Matter work state."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from evidence_review.contracts.common import BBox
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
from evidence_review.review_matter.store import MatterStore


def _stale(message: str = "NAVIGATION_RESULT_STALE") -> ValueError:
    return ValueError(message)


def _hit_matches_current_record(
    connection: sqlite3.Connection, hit: NavigationHit
) -> bool:
    row = connection.execute(
        """
        SELECT document_id, revision_id, page_number, bbox_json, source_hash
        FROM retrieval_records
        WHERE evidence_id = ?
        """,
        (hit.evidence_id,),
    ).fetchone()
    if row is None:
        return False
    try:
        raw_bbox = json.loads(str(row["bbox_json"]))
        if not isinstance(raw_bbox, list) or len(raw_bbox) != 4:
            return False
        bbox = BBox(*(float(item) for item in raw_bbox))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return (
        row["document_id"] == hit.document_id
        and row["revision_id"] == hit.revision_id
        and row["page_number"] == hit.page_number
        and row["source_hash"] == hit.source_hash
        and bbox == hit.bbox
    )


def promote_navigation_hit(
    store: MatterStore,
    *,
    matter_id: str,
    expected_revision: int,
    evidence_db: Path,
    navigation_result: NavigationResult,
    evidence_id: str,
) -> MatterProjection:
    """Promote one exact navigation hit after current-identity revalidation."""
    if not isinstance(navigation_result, NavigationResult):
        raise ValueError("navigation_result must be a NavigationResult")
    current = store.load(matter_id)
    if current.revision != expected_revision:
        raise ValueError("MATTER_REVISION_CONFLICT")
    hit = next((item for item in navigation_result.hits if item.evidence_id == evidence_id), None)
    if hit is None:
        raise ValueError("NAVIGATION_HIT_NOT_FOUND")
    try:
        with EvidenceStore(Path(evidence_db), read_only=True) as evidence_store:
            validate_finalized_evidence(evidence_store)
            if not _hit_matches_current_record(evidence_store.require_connection(), hit):
                raise _stale()
            provenance = finalized_evidence_provenance(Path(evidence_db))
    except Exception as error:
        raise _stale() from error

    snapshot_hash = provenance.get("evidence_snapshot_hash")
    database_sha = provenance.get("evidence_db_sha256")
    if (
        snapshot_hash != navigation_result.evidence_snapshot_hash
        or database_sha != navigation_result.evidence_db_sha256
    ):
        raise _stale()
    binding = store.get_evidence_binding(matter_id)
    if binding is None:
        raise ValueError("MATTER_EVIDENCE_NOT_BOUND")
    if (
        binding["evidence_snapshot_hash"] != snapshot_hash
        or binding["evidence_db_sha256"] != database_sha
    ):
        raise _stale()
    if hit.citation.source_hash != hit.source_hash:
        raise _stale()
    promoted = MatterSourceBinding(
        binding_id=f"BIND-NAV-{hit.evidence_id}",
        document_id=hit.document_id,
        revision_id=hit.revision_id,
        page_number=hit.page_number,
        evidence_id=hit.evidence_id,
        bbox=(hit.bbox.left, hit.bbox.bottom, hit.bbox.right, hit.bbox.top),
        source_hash=hit.source_hash,
        evidence_snapshot_hash=str(snapshot_hash),
        evidence_db_sha256=str(database_sha),
    )
    existing = next(
        (item for item in current.source_bindings if item.binding_id == promoted.binding_id),
        None,
    )
    if existing == promoted:
        return MatterProjection(current)
    if existing is not None:
        raise ValueError("NAVIGATION_BINDING_CONFLICT")
    event = MatterEvent(
        kind="EVIDENCE_SELECTED",
        payload={
            "binding": matter_source_binding_document(promoted),
            "bound_revision": expected_revision + 1,
        },
    )
    return append_matter_event(store, matter_id, expected_revision, event)
