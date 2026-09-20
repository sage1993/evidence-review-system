"""Canonical application boundary for mutable ReviewMatter work."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.validation import expect_string
from evidence_review.filesystem_trust import (
    verified_create_target_below,
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.navigation.models import NavigationResult
from evidence_review.navigation.promotion import promote_navigation_hit
from evidence_review.navigation.service import navigate_evidence
from evidence_review.review_matter.contracts import (
    MatterIssue,
    MatterIssueState,
    ReviewMatter,
    decode_matter_issue_state,
    decode_review_matter,
    review_matter_document,
)
from evidence_review.review_matter.contracts import _identifier as _validate_matter_id
from evidence_review.review_matter.events import MatterEvent, append_matter_event
from evidence_review.review_matter.formal_run_binding import (
    FormalRunBinding,
    list_formal_runs,
)
from evidence_review.review_matter.formalization import formalize_snapshot
from evidence_review.review_matter.invalidation import (
    invalidate_source_dependents as _invalidate_source_dependents,
)
from evidence_review.review_matter.snapshot import (
    FormalizationSnapshot,
    create_formalization_snapshot,
)
from evidence_review.review_matter.source_binding import bind_finalized_evidence
from evidence_review.review_matter.store import MatterNotFound, MatterStore
from evidence_review.review_question import PreparedReviewQuestion


def _expected_revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("expected_revision is required")
    return value


def _issue(
    *,
    issue_id: object,
    question: object,
    work_state: object,
    depends_on: Sequence[object],
    required_facet_ids: Sequence[object],
) -> MatterIssue:
    if isinstance(depends_on, (str, bytes, bytearray)):
        raise ValueError("depends_on must be a sequence")
    issue = MatterIssue(
        issue_id=validate_identifier(issue_id, "issue_id"),
        question=expect_string(question, "question"),
        work_state=decode_matter_issue_state(work_state, "work_state"),
        depends_on=tuple(
            validate_identifier(item, f"depends_on[{index}]")
            for index, item in enumerate(depends_on)
        ),
        required_facet_ids=tuple(
            validate_identifier(item, f"required_facet_ids[{index}]")
            for index, item in enumerate(required_facet_ids)
        ),
    )
    if issue.issue_id in issue.depends_on:
        raise ValueError("issue cannot depend on itself")
    return issue


@dataclass(frozen=True, slots=True)
class FormalizedMatter:
    """Immutable snapshot and newly prepared Formal Run identities."""

    snapshot: FormalizationSnapshot
    prepared: PreparedReviewQuestion


@dataclass(frozen=True, slots=True)
class ReviewMatterService:
    """Own ReviewMatter state transitions while keeping Formal Review immutable."""

    workspace: Path

    @classmethod
    def open(cls, workspace: Path) -> ReviewMatterService:
        return cls(verified_regular_directory(Path(workspace), field="workspace root"))

    def _existing_matter_path(self) -> Path:
        try:
            return verified_regular_file_below(
                self.workspace,
                ("matter.sqlite",),
                field="Matter store",
            )
        except FileNotFoundError as error:
            raise MatterNotFound("MATTER_NOT_FOUND") from error

    def _create_matter_path(self) -> Path:
        try:
            return verified_regular_file_below(
                self.workspace,
                ("matter.sqlite",),
                field="Matter store",
            )
        except FileNotFoundError:
            return verified_create_target_below(
                self.workspace,
                ("matter.sqlite",),
                field="Matter store",
            )

    def _evidence_database(self) -> Path:
        return verified_regular_file_below(
            self.workspace,
            ("evidence", "evidence.sqlite"),
            field="evidence database",
        )

    @contextmanager
    def _existing_store(self) -> Iterator[MatterStore]:
        with MatterStore(self._existing_matter_path()) as store:
            yield store

    @contextmanager
    def _create_store(self) -> Iterator[MatterStore]:
        with MatterStore(self._create_matter_path()) as store:
            yield store

    def _validated_matter_id(self, matter_id: str) -> str:
        return _validate_matter_id(matter_id, "matter_id")

    def create(self, *, matter_id: str, title: str) -> ReviewMatter:
        """Create one distinct mutable Matter at the explicitly supplied workspace."""
        validated_matter_id = self._validated_matter_id(matter_id)
        validated_title = expect_string(title, "title")
        with self._create_store() as store:
            return store.create(
                matter_id=validated_matter_id, title=validated_title
            )

    def status(self, *, matter_id: str) -> ReviewMatter:
        """Return mutable Matter work state without promoting it to Formal Review."""
        validated_matter_id = self._validated_matter_id(matter_id)
        with self._existing_store() as store:
            return store.load(validated_matter_id)

    def list_formal_runs(self, *, matter_id: str) -> tuple[FormalRunBinding, ...]:
        """Return only persisted, fully validated Formal Run lineage for one Matter."""
        validated_matter_id = self._validated_matter_id(matter_id)
        with self._existing_store() as store:
            return list_formal_runs(
                store,
                validated_matter_id,
                workspace_root=self.workspace,
            )

    def add_issue(
        self,
        *,
        matter_id: str,
        expected_revision: int,
        issue_id: str,
        question: str,
        work_state: MatterIssueState,
        depends_on: Sequence[str] = (),
        required_facet_ids: Sequence[str] = (),
    ) -> ReviewMatter:
        """Append one revision-checked issue event and return its new projection."""
        validated_matter_id = self._validated_matter_id(matter_id)
        issue = _issue(
            issue_id=issue_id,
            question=question,
            work_state=work_state,
            depends_on=depends_on,
            required_facet_ids=required_facet_ids,
        )
        with self._existing_store() as store:
            matter = store.load(validated_matter_id)
            decode_review_matter(
                review_matter_document(
                    ReviewMatter(
                        matter_id=matter.matter_id,
                        title=matter.title,
                        revision=matter.revision,
                        issues=(*matter.issues, issue),
                        source_bindings=matter.source_bindings,
                    )
                )
            )
            projection = append_matter_event(
                store,
                validated_matter_id,
                _expected_revision(expected_revision),
                MatterEvent(
                    kind="ISSUE_ADDED",
                    payload={
                        "issue_id": issue.issue_id,
                        "question": issue.question,
                        "work_state": issue.work_state,
                        "depends_on": list(issue.depends_on),
                        "required_facet_ids": list(issue.required_facet_ids),
                    },
                ),
            )
        return projection.matter

    def set_required_facets(
        self,
        *,
        matter_id: str,
        expected_revision: int,
        issue_id: str,
        required_facet_ids: Sequence[str],
    ) -> ReviewMatter:
        """Append explicit facet IDs to one legacy Matter issue."""
        facets = tuple(
            validate_identifier(item, f"required_facet_ids[{index}]")
            for index, item in enumerate(required_facet_ids)
        )
        if not facets or len(facets) != len(set(facets)):
            raise ValueError("required_facet_ids must be unique and non-empty")
        with self._existing_store() as store:
            projection = append_matter_event(
                store,
                self._validated_matter_id(matter_id),
                _expected_revision(expected_revision),
                MatterEvent(
                    kind="ISSUE_REQUIRED_FACETS_SET",
                    payload={"issue_id": validate_identifier(issue_id, "issue_id"), "required_facet_ids": list(facets)},
                ),
            )
        return projection.matter

    def bind_evidence(
        self, *, matter_id: str, expected_revision: int
    ) -> ReviewMatter:
        """Bind exact finalized evidence from the canonical workspace location."""
        validated_matter_id = self._validated_matter_id(matter_id)
        with self._existing_store() as store:
            store.load(validated_matter_id)
            return bind_finalized_evidence(
                store,
                matter_id=validated_matter_id,
                expected_revision=_expected_revision(expected_revision),
                evidence_db=self._evidence_database(),
            )

    def search(
        self, *, matter_id: str, query: str, limit: int = 20
    ) -> NavigationResult:
        """Navigate only the exact finalized evidence currently at this workspace."""
        self.status(matter_id=matter_id)
        return navigate_evidence(self._evidence_database(), query, limit=limit)

    def select_evidence(
        self,
        *,
        matter_id: str,
        expected_revision: int,
        query: str,
        evidence_id: str,
        limit: int = 20,
    ) -> ReviewMatter:
        """Re-run navigation and atomically promote one exact current hit."""
        validated_matter_id = self._validated_matter_id(matter_id)
        with self._existing_store() as store:
            store.load(validated_matter_id)
        result = self.search(
            matter_id=validated_matter_id, query=query, limit=limit
        )
        with self._existing_store() as store:
            projection = promote_navigation_hit(
                store,
                matter_id=validated_matter_id,
                expected_revision=_expected_revision(expected_revision),
                evidence_db=self._evidence_database(),
                navigation_result=result,
                evidence_id=validate_identifier(evidence_id, "evidence_id"),
            )
        return projection.matter

    def formalize(
        self, *, matter_id: str, expected_revision: int
    ) -> FormalizedMatter:
        """Freeze one exact Matter revision, then prepare its immutable Formal Run."""
        validated_matter_id = self._validated_matter_id(matter_id)
        with self._existing_store() as store:
            store.load(validated_matter_id)
            snapshot = create_formalization_snapshot(
                store,
                validated_matter_id,
                _expected_revision(expected_revision),
                self._evidence_database(),
            )
        return FormalizedMatter(
            snapshot=snapshot,
            prepared=formalize_snapshot(self.workspace, snapshot),
        )

    def invalidate_source_dependents(
        self,
        *,
        matter_id: str,
        expected_revision: int,
        source_key: str | None,
        new_source_hash: str,
        new_source_revision_id: str,
    ) -> ReviewMatter:
        """Apply one source revision through the existing Matter event authority."""
        validated_matter_id = self._validated_matter_id(matter_id)
        with self._existing_store() as store:
            store.load(validated_matter_id)
            return _invalidate_source_dependents(
                store,
                validated_matter_id,
                _expected_revision(expected_revision),
                source_key,
                new_source_hash,
                new_source_revision_id,
            )


__all__ = ["FormalizedMatter", "ReviewMatterService"]
