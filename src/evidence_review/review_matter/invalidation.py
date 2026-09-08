"""Conservative source-dependency invalidation for Matter work."""

from __future__ import annotations

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.validation import expect_sha256
from evidence_review.review_matter.contracts import ReviewMatter
from evidence_review.review_matter.events import MatterEvent, append_matter_event
from evidence_review.review_matter.store import MatterRevisionConflict, MatterStore


def register_issue_source_dependency(
    store: MatterStore,
    matter_id: str,
    expected_revision: int,
    issue_id: str,
    source_key: str,
    source_hash: str,
) -> ReviewMatter:
    """Record exact source dependency identity as Matter work metadata."""
    matter = store.load(matter_id)
    if issue_id not in {issue.issue_id for issue in matter.issues}:
        raise ValueError("MATTER_ISSUE_NOT_FOUND")
    validate_identifier(issue_id, "issue_id")
    source_key = validate_identifier(source_key, "source_key")
    source_hash = expect_sha256(source_hash, "source_hash")
    event = MatterEvent(
        kind="SOURCE_DEPENDENCY_REGISTERED",
        payload={
            "issue_id": issue_id,
            "source_key": source_key,
            "source_hash": source_hash,
        },
    )
    return append_matter_event(store, matter_id, expected_revision, event).matter


def invalidate_source_dependents(
    store: MatterStore,
    matter_id: str,
    expected_revision: int,
    source_key: str | None,
    new_source_hash: str,
) -> ReviewMatter:
    """Mark known or unknown-impact dependent issues stale conservatively."""
    new_source_hash = expect_sha256(new_source_hash, "new_source_hash")
    matter = store.load(matter_id)
    if matter.revision != expected_revision:
        raise MatterRevisionConflict("MATTER_REVISION_CONFLICT")
    dependencies = store.list_source_dependencies(matter_id)
    if source_key is None:
        issue_ids = tuple(issue.issue_id for issue in matter.issues)
    else:
        source_key = validate_identifier(source_key, "source_key")
        matching = [item for item in dependencies if item["source_key"] == source_key]
        if not matching:
            issue_ids = tuple(issue.issue_id for issue in matter.issues)
        elif all(item["source_hash"] == new_source_hash for item in matching):
            return matter
        else:
            issue_ids = tuple(
                issue.issue_id
                for issue in matter.issues
                if not any(
                    dependency["issue_id"] == issue.issue_id
                    for dependency in dependencies
                )
                or any(
                    dependency["issue_id"] == issue.issue_id
                    and dependency["source_key"] == source_key
                    and dependency["source_hash"] != new_source_hash
                    for dependency in matching
                )
            )
            if not issue_ids:
                return matter
    if not issue_ids:
        return matter
    event = MatterEvent(
        kind="ISSUES_INVALIDATED",
        payload={
            "issue_ids": list(issue_ids),
            "source_key": source_key,
            "new_source_hash": new_source_hash,
        },
    )
    return append_matter_event(store, matter_id, expected_revision, event).matter
