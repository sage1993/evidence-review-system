"""Exact finalized evidence binding for ReviewMatter work."""

from __future__ import annotations

from pathlib import Path

from evidence_review.contracts.validation import expect_int, expect_sha256
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.review_matter.contracts import ReviewMatter
from evidence_review.review_matter.events import MatterEvent, append_matter_event
from evidence_review.review_matter.store import MatterRevisionConflict, MatterStore


def bind_finalized_evidence(
    store: MatterStore,
    *,
    matter_id: str,
    expected_revision: int,
    evidence_db: Path,
) -> ReviewMatter:
    """Bind one Matter to a validated, exact finalized evidence artifact."""
    try:
        provenance = finalized_evidence_provenance(Path(evidence_db))
        snapshot_hash = expect_sha256(
            provenance["evidence_snapshot_hash"], "evidence_snapshot_hash"
        )
        database_sha = expect_sha256(
            provenance["evidence_db_sha256"], "evidence_db_sha256"
        )
        schema_version = expect_int(provenance["schema_version"], "schema_version")
        if schema_version < 1:
            raise ValueError("schema_version must be positive")
    except Exception as error:
        raise ValueError("MATTER_EVIDENCE_BINDING_INVALID") from error

    current = store.load(matter_id)
    if current.revision != expected_revision:
        raise MatterRevisionConflict("MATTER_REVISION_CONFLICT")
    existing = store.get_evidence_binding(matter_id)
    if (
        existing is not None
        and existing["evidence_snapshot_hash"] == snapshot_hash
        and existing["evidence_db_sha256"] == database_sha
        and existing["schema_version"] == schema_version
    ):
        return store.load(matter_id)

    kind = "EVIDENCE_BOUND" if existing is None else "EVIDENCE_REBOUND"
    event = MatterEvent(
        kind=kind,
        payload={
            "evidence_snapshot_hash": snapshot_hash,
            "evidence_db_sha256": database_sha,
            "schema_version": schema_version,
            "bound_revision": expected_revision + 1,
        },
    )
    return append_matter_event(store, matter_id, expected_revision, event).matter
