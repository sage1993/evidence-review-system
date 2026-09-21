"""Deterministic Matter event projection and rebuild helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.validation import (
    expect_int,
    expect_mapping,
    expect_sequence,
    expect_sha256,
    expect_string,
    reject_unknown,
    require_fields,
)
from evidence_review.review_matter.contracts import (
    MatterIssue,
    MatterSourceBinding,
    ReviewMatter,
    decode_matter_issue_state,
    decode_review_matter,
    review_matter_document,
)

if TYPE_CHECKING:
    from evidence_review.review_matter.events import MatterEvent
    from evidence_review.review_matter.store import MatterStore


@dataclass(frozen=True, slots=True)
class MatterProjection:
    """The materialized ReviewMatter state after one or more events."""

    matter: ReviewMatter

    @property
    def matter_id(self) -> str:
        return self.matter.matter_id

    @property
    def title(self) -> str:
        return self.matter.title

    @property
    def revision(self) -> int:
        return self.matter.revision

    @property
    def issues(self) -> tuple[MatterIssue, ...]:
        return self.matter.issues

    @property
    def source_bindings(self) -> tuple[MatterSourceBinding, ...]:
        return self.matter.source_bindings


def project_event(matter: ReviewMatter, event: MatterEvent) -> MatterProjection:
    """Apply one supported event to a Matter without performing I/O."""
    if event.kind == "ISSUE_ADDED":
        payload = expect_mapping(event.payload, "ISSUE_ADDED.payload")
        required = {"issue_id", "question", "work_state", "depends_on"}
        allowed = required | {"required_facet_ids"}
        require_fields(payload, required, "ISSUE_ADDED.payload")
        reject_unknown(payload, allowed, "ISSUE_ADDED.payload")
        issue_id = validate_identifier(payload.get("issue_id"), "issue_id")
        if issue_id in {issue.issue_id for issue in matter.issues}:
            raise ValueError("ISSUE_ADDED duplicate issue")
        issue = MatterIssue(
            issue_id=issue_id,
            question=expect_string(payload.get("question"), "question"),
            work_state=decode_matter_issue_state(payload.get("work_state"), "work_state"),
            depends_on=tuple(
                validate_identifier(item, "depends_on")
                for item in expect_sequence(payload.get("depends_on"), "depends_on")
            ),
            required_facet_ids=tuple(
                validate_identifier(item, "required_facet_ids")
                for item in expect_sequence(
                    payload.get("required_facet_ids", []), "required_facet_ids"
                )
            ),
        )
        updated = ReviewMatter(
            matter_id=matter.matter_id,
            title=matter.title,
            revision=matter.revision + 1,
            issues=(*matter.issues, issue),
            source_bindings=matter.source_bindings,
        )
        decode_review_matter(review_matter_document(updated))
        return MatterProjection(updated)
    if event.kind == "ISSUE_REQUIRED_FACETS_SET":
        payload = expect_mapping(event.payload, "ISSUE_REQUIRED_FACETS_SET.payload")
        fields = {"issue_id", "required_facet_ids"}
        require_fields(payload, fields, "ISSUE_REQUIRED_FACETS_SET.payload")
        reject_unknown(payload, fields, "ISSUE_REQUIRED_FACETS_SET.payload")
        issue_id = validate_identifier(payload.get("issue_id"), "issue_id")
        facet_ids = tuple(
            validate_identifier(item, "required_facet_ids")
            for item in expect_sequence(payload.get("required_facet_ids"), "required_facet_ids")
        )
        if not facet_ids or len(facet_ids) != len(set(facet_ids)):
            raise ValueError("ISSUE_REQUIRED_FACETS_SET requires unique non-empty facet ids")
        issues = []
        found = False
        for issue in matter.issues:
            if issue.issue_id != issue_id:
                issues.append(issue)
            elif issue.required_facet_ids:
                raise ValueError("ISSUE_REQUIRED_FACETS_SET issue already has facet ids")
            else:
                issues.append(replace(issue, required_facet_ids=facet_ids))
                found = True
        if not found:
            raise ValueError("ISSUE_REQUIRED_FACETS_SET unknown issue")
        return MatterProjection(replace(matter, revision=matter.revision + 1, issues=tuple(issues)))
    if event.kind == "TITLE_CHANGED":
        payload = expect_mapping(event.payload, "TITLE_CHANGED.payload")
        reject_unknown(payload, {"title"}, "TITLE_CHANGED.payload")
        title = expect_string(payload.get("title"), "TITLE_CHANGED.payload.title")
        updated = ReviewMatter(
            matter_id=matter.matter_id,
            title=title,
            revision=matter.revision + 1,
            issues=matter.issues,
            source_bindings=matter.source_bindings,
        )
        return MatterProjection(updated)
    if event.kind == "ISSUE_STATE_CHANGED":
        payload = expect_mapping(event.payload, "ISSUE_STATE_CHANGED.payload")
        reject_unknown(payload, {"issue_id", "work_state"}, "ISSUE_STATE_CHANGED.payload")
        issue_id = expect_string(payload.get("issue_id"), "issue_id")
        work_state = decode_matter_issue_state(payload.get("work_state"), "work_state")
        changed = False
        updated_issues: list[MatterIssue] = []
        for issue in matter.issues:
            if issue.issue_id == issue_id:
                changed = True
                updated_issues.append(
                    MatterIssue(
                        issue_id=issue.issue_id,
                        question=issue.question,
                        work_state=work_state,
                        depends_on=issue.depends_on,
                        required_facet_ids=issue.required_facet_ids,
                    )
                )
            else:
                updated_issues.append(issue)
        if not changed:
            raise ValueError("ISSUE_STATE_CHANGED references unknown issue")
        updated = ReviewMatter(
            matter_id=matter.matter_id,
            title=matter.title,
            revision=matter.revision + 1,
            issues=tuple(updated_issues),
            source_bindings=matter.source_bindings,
        )
        decode_review_matter(review_matter_document(updated))
        return MatterProjection(updated)
    if event.kind == "SOURCE_DEPENDENCY_REGISTERED":
        payload = expect_mapping(event.payload, "SOURCE_DEPENDENCY_REGISTERED.payload")
        required = {"issue_id", "source_key", "source_hash"}
        require_fields(payload, required, "SOURCE_DEPENDENCY_REGISTERED.payload")
        allowed = {*required, "source_revision_id"}
        reject_unknown(
            payload,
            allowed,
            "SOURCE_DEPENDENCY_REGISTERED.payload",
        )
        issue_id = validate_identifier(
            payload.get("issue_id"), "SOURCE_DEPENDENCY_REGISTERED.payload.issue_id"
        )
        if issue_id not in {issue.issue_id for issue in matter.issues}:
            raise ValueError("SOURCE_DEPENDENCY_REGISTERED references unknown issue")
        validate_identifier(
            payload.get("source_key"), "SOURCE_DEPENDENCY_REGISTERED.payload.source_key"
        )
        expect_sha256(
            payload.get("source_hash"), "SOURCE_DEPENDENCY_REGISTERED.payload.source_hash"
        )
        if "source_revision_id" in payload:
            validate_identifier(
                payload.get("source_revision_id"),
                "SOURCE_DEPENDENCY_REGISTERED.payload.source_revision_id",
            )
        updated = ReviewMatter(
            matter_id=matter.matter_id,
            title=matter.title,
            revision=matter.revision + 1,
            issues=matter.issues,
            source_bindings=matter.source_bindings,
        )
        return MatterProjection(updated)
    if event.kind in {"EVIDENCE_BOUND", "EVIDENCE_REBOUND"}:
        payload = expect_mapping(event.payload, f"{event.kind}.payload")
        required = {
            "evidence_snapshot_hash",
            "evidence_db_sha256",
            "schema_version",
            "bound_revision",
        }
        require_fields(payload, required, f"{event.kind}.payload")
        reject_unknown(
            payload,
            required,
            f"{event.kind}.payload",
        )
        expect_sha256(
            payload.get("evidence_snapshot_hash"),
            f"{event.kind}.payload.evidence_snapshot_hash",
        )
        expect_sha256(
            payload.get("evidence_db_sha256"),
            f"{event.kind}.payload.evidence_db_sha256",
        )
        schema_version = expect_int(
            payload.get("schema_version"), f"{event.kind}.payload.schema_version"
        )
        if schema_version < 1:
            raise ValueError(f"{event.kind}.payload.schema_version must be positive")
        bound_revision = expect_int(
            payload.get("bound_revision"), f"{event.kind}.payload.bound_revision"
        )
        if bound_revision != matter.revision + 1:
            raise ValueError(f"{event.kind}.payload.bound_revision mismatch")
        bound_issues: tuple[MatterIssue, ...] = matter.issues
        if event.kind == "EVIDENCE_REBOUND":
            bound_issues = tuple(
                MatterIssue(
                    issue_id=issue.issue_id,
                    question=issue.question,
                    work_state="STALE",
                    depends_on=issue.depends_on,
                    required_facet_ids=issue.required_facet_ids,
                )
                for issue in bound_issues
            )
        updated = ReviewMatter(
            matter_id=matter.matter_id,
            title=matter.title,
            revision=matter.revision + 1,
            issues=bound_issues,
            source_bindings=matter.source_bindings,
        )
        decode_review_matter(review_matter_document(updated))
        return MatterProjection(updated)
    if event.kind == "EVIDENCE_SELECTED":
        payload = expect_mapping(event.payload, "EVIDENCE_SELECTED.payload")
        require_fields(payload, {"source_binding"}, "EVIDENCE_SELECTED.payload")
        reject_unknown(payload, {"source_binding"}, "EVIDENCE_SELECTED.payload")
        from evidence_review.review_matter.contracts import (
            decode_matter_source_binding,
        )

        selected = decode_matter_source_binding(payload.get("source_binding"))
        same_id = next(
            (
                binding
                for binding in matter.source_bindings
                if binding.binding_id == selected.binding_id
            ),
            None,
        )
        if same_id is not None:
            if same_id == selected:
                return MatterProjection(matter)
            raise ValueError("EVIDENCE_SELECTED binding identity conflict")
        if any(
            binding.evidence_id == selected.evidence_id
            for binding in matter.source_bindings
        ):
            raise ValueError("EVIDENCE_SELECTED binding identity conflict")
        updated = ReviewMatter(
            matter_id=matter.matter_id,
            title=matter.title,
            revision=matter.revision + 1,
            issues=matter.issues,
            source_bindings=(*matter.source_bindings, selected),
        )
        decode_review_matter(review_matter_document(updated))
        return MatterProjection(updated)
    if event.kind == "ISSUES_INVALIDATED":
        payload = expect_mapping(event.payload, "ISSUES_INVALIDATED.payload")
        required = {"issue_ids", "source_key", "new_source_hash"}
        require_fields(payload, required, "ISSUES_INVALIDATED.payload")
        allowed = {*required, "new_source_revision_id"}
        reject_unknown(
            payload,
            allowed,
            "ISSUES_INVALIDATED.payload",
        )
        raw_issue_ids = expect_sequence(
            payload.get("issue_ids"), "ISSUES_INVALIDATED.payload.issue_ids"
        )
        if not raw_issue_ids:
            raise ValueError("ISSUES_INVALIDATED.payload.issue_ids must not be empty")
        issue_ids = tuple(
            validate_identifier(
                item, f"ISSUES_INVALIDATED.payload.issue_ids[{index}]"
            )
            for index, item in enumerate(raw_issue_ids)
        )
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError("ISSUES_INVALIDATED.payload.issue_ids contains duplicates")
        unknown_issue_ids = set(issue_ids) - {issue.issue_id for issue in matter.issues}
        if unknown_issue_ids:
            raise ValueError("ISSUES_INVALIDATED references unknown issue")
        source_key = payload.get("source_key")
        if source_key is not None:
            validate_identifier(source_key, "ISSUES_INVALIDATED.payload.source_key")
        expect_sha256(
            payload.get("new_source_hash"), "ISSUES_INVALIDATED.payload.new_source_hash"
        )
        if "new_source_revision_id" in payload:
            validate_identifier(
                payload.get("new_source_revision_id"),
                "ISSUES_INVALIDATED.payload.new_source_revision_id",
            )
        invalidated_issues = tuple(
            MatterIssue(
                issue_id=issue.issue_id,
                question=issue.question,
                work_state="STALE" if issue.issue_id in issue_ids else issue.work_state,
                depends_on=issue.depends_on,
                required_facet_ids=issue.required_facet_ids,
            )
            for issue in matter.issues
        )
        updated = ReviewMatter(
            matter_id=matter.matter_id,
            title=matter.title,
            revision=matter.revision + 1,
            issues=invalidated_issues,
            source_bindings=matter.source_bindings,
        )
        decode_review_matter(review_matter_document(updated))
        return MatterProjection(updated)
    raise ValueError(f"unsupported Matter event kind: {event.kind}")


def rebuild_projection(store: MatterStore, matter_id: str) -> MatterProjection:
    """Rebuild one projection from its immutable baseline and event journal."""
    from evidence_review.review_matter.events import decode_matter_event

    with store.transaction():
        row = store.connection.execute(
            "SELECT document_json FROM matter_baselines WHERE matter_id = ?",
            (matter_id,),
        ).fetchone()
        if row is None:
            raise ValueError("MATTER_BASELINE_NOT_FOUND")
        try:
            matter = decode_review_matter(json.loads(str(row["document_json"])))
        except json.JSONDecodeError as error:
            raise ValueError("MATTER_BASELINE_INVALID_JSON") from error
        expected_sequence = 1
        projection = MatterProjection(matter)
        rows = store.connection.execute(
            """
            SELECT sequence, matter_revision, event_json
            FROM matter_events
            WHERE matter_id = ?
            ORDER BY sequence
            """,
            (matter_id,),
        ).fetchall()
        store.connection.execute(
            "DELETE FROM matter_evidence_bindings WHERE matter_id = ?",
            (matter_id,),
        )
        store.connection.execute(
            "DELETE FROM matter_source_dependencies WHERE matter_id = ?",
            (matter_id,),
        )
        for row in rows:
            if row["sequence"] != expected_sequence:
                raise ValueError("MATTER_EVENT_SEQUENCE_GAP")
            event = decode_matter_event(json.loads(str(row["event_json"])))
            projection = project_event(projection.matter, event)
            if projection.revision != row["matter_revision"]:
                raise ValueError("MATTER_EVENT_REVISION_MISMATCH")
            store.apply_event_side_effects(matter_id, event)
            expected_sequence += 1
        if projection.matter_id != matter_id:
            raise ValueError("MATTER_BASELINE_ID_MISMATCH")
        store.apply_projection(projection.matter)
    return projection
