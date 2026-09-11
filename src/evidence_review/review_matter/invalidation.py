"""Conservative source-dependency invalidation for Matter work."""

from __future__ import annotations

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.validation import (
    expect_mapping,
    expect_sha256,
    reject_unknown,
    require_fields,
)
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
    source_revision_id: str,
) -> ReviewMatter:
    """Record exact source dependency identity as Matter work metadata."""
    matter = store.load(matter_id)
    if issue_id not in {issue.issue_id for issue in matter.issues}:
        raise ValueError("MATTER_ISSUE_NOT_FOUND")
    validate_identifier(issue_id, "issue_id")
    source_key = validate_identifier(source_key, "source_key")
    source_hash = expect_sha256(source_hash, "source_hash")
    source_revision_id = validate_identifier(source_revision_id, "source_revision_id")
    event = MatterEvent(
        kind="SOURCE_DEPENDENCY_REGISTERED",
        payload={
            "issue_id": issue_id,
            "source_key": source_key,
            "source_hash": source_hash,
            "source_revision_id": source_revision_id,
        },
    )
    return append_matter_event(store, matter_id, expected_revision, event).matter


def invalidate_source_dependents(
    store: MatterStore,
    matter_id: str,
    expected_revision: int,
    source_key: str | None,
    new_source_hash: str,
    new_source_revision_id: str,
) -> ReviewMatter:
    """Mark known or unknown-impact dependent issues stale conservatively."""
    new_source_hash = expect_sha256(new_source_hash, "new_source_hash")
    new_source_revision_id = validate_identifier(
        new_source_revision_id, "new_source_revision_id"
    )
    matter = store.load(matter_id)
    if matter.revision != expected_revision:
        raise MatterRevisionConflict("MATTER_REVISION_CONFLICT")
    dependencies = store.list_source_dependencies(matter_id)
    if source_key is None:
        issue_ids = tuple(issue.issue_id for issue in matter.issues)
    else:
        source_key = validate_identifier(source_key, "source_key")
        validated = _validated_source_dependencies(matter, dependencies)
        if validated is None:
            issue_ids = tuple(issue.issue_id for issue in matter.issues)
        else:
            source_dependencies, source_identities = validated
            before_identity = source_identities.get(source_key)
            if before_identity is None:
                issue_ids = tuple(issue.issue_id for issue in matter.issues)
            else:
                source_hash, source_revision_id = before_identity
                report = evaluate_source_change_impact(
                    before={
                        "source_id": source_key,
                        "sha256": source_hash,
                        "revision_id": source_revision_id,
                    },
                    after={
                        "source_id": source_key,
                        "sha256": new_source_hash,
                        "revision_id": new_source_revision_id,
                    },
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
            "new_source_revision_id": new_source_revision_id,
        },
    )
    return append_matter_event(store, matter_id, expected_revision, event).matter


def _validated_source_dependencies(
    matter: ReviewMatter, dependencies: object
) -> tuple[dict[str, set[str]], dict[str, tuple[str, str]]] | None:
    try:
        if not isinstance(dependencies, tuple):
            raise ValueError("dependencies must be an immutable record set")
        issue_ids = {issue.issue_id for issue in matter.issues}
        graph: dict[str, set[str]] = {}
        identities: dict[str, tuple[str, str]] = {}
        seen: set[tuple[str, str]] = set()
        for index, raw_dependency in enumerate(dependencies):
            dependency = expect_mapping(raw_dependency, f"dependencies[{index}]")
            required = {
                "issue_id",
                "source_key",
                "source_hash",
                "source_revision_id",
            }
            require_fields(dependency, required, f"dependencies[{index}]")
            reject_unknown(dependency, required, f"dependencies[{index}]")
            issue_id = validate_identifier(
                dependency.get("issue_id"), f"dependencies[{index}].issue_id"
            )
            if issue_id not in issue_ids:
                raise ValueError("dependency references unknown Matter issue")
            source_key = validate_identifier(
                dependency.get("source_key"), f"dependencies[{index}].source_key"
            )
            source_hash = expect_sha256(
                dependency.get("source_hash"), f"dependencies[{index}].source_hash"
            )
            source_revision_id = validate_identifier(
                dependency.get("source_revision_id"),
                f"dependencies[{index}].source_revision_id",
            )
            record_key = (issue_id, source_key)
            if record_key in seen:
                raise ValueError("duplicate source dependency record")
            seen.add(record_key)
            identity = (source_hash, source_revision_id)
            current = identities.setdefault(source_key, identity)
            if current != identity:
                raise ValueError("inconsistent source dependency identity")
            graph.setdefault(issue_id, set()).add(source_key)
        return graph, identities
    except ValueError:
        return None
