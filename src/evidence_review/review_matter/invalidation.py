"""Conservative source-dependency invalidation for Matter work."""

from __future__ import annotations

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.validation import expect_sha256
from evidence_review.review_matter.contracts import ReviewMatter
from evidence_review.review_matter.events import MatterEvent, append_matter_event
from evidence_review.review_matter.impact import evaluate_source_change_impact
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
        source_dependencies: dict[str, set[str]] = {}
        for dependency in dependencies:
            source_dependencies.setdefault(dependency["issue_id"], set()).add(
                dependency["source_key"]
            )
        matching = [item for item in dependencies if item["source_key"] == source_key]
        matching_hashes = {item["source_hash"] for item in matching}
        if len(matching_hashes) != 1:
            issue_ids = tuple(issue.issue_id for issue in matter.issues)
        else:
            report = evaluate_source_change_impact(
                before={"source_id": source_key, "sha256": matching_hashes.pop()},
                after={"source_id": source_key, "sha256": new_source_hash},
                dependencies=source_dependencies,
            )
            if report.status == "UNCHANGED":
                return matter
            direct_stale = set(report.stale_issue_ids)
            known_dependency_issues = set(source_dependencies)
            direct_stale.update(
                issue.issue_id
                for issue in matter.issues
                if issue.issue_id not in known_dependency_issues
            )
            issue_ids = tuple(
                issue.issue_id
                for issue in matter.issues
                if issue.issue_id in direct_stale
            )
            stale_issue_ids = set(issue_ids)
            while True:
                downstream = {
                    issue.issue_id
                    for issue in matter.issues
                    if any(dependency in stale_issue_ids for dependency in issue.depends_on)
                }
                if downstream <= stale_issue_ids:
                    break
                stale_issue_ids.update(downstream)
            issue_ids = tuple(
                issue.issue_id
                for issue in matter.issues
                if issue.issue_id in stale_issue_ids
            )
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
