import pytest

from evidence_review.review_matter.contracts import MatterIssue
from evidence_review.review_matter.invalidation import (
    invalidate_source_dependents,
    register_issue_source_dependency,
)
from evidence_review.review_matter.source_binding import bind_finalized_evidence
from evidence_review.review_matter.store import MatterRevisionConflict, MatterStore


def test_source_binding_api_rejects_missing_finalized_evidence(tmp_path) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    evidence_db.write_bytes(b"not-a-finalized-sqlite")
    with pytest.raises(ValueError, match="MATTER_EVIDENCE_BINDING_INVALID"):
        bind_finalized_evidence(
            object(),  # type: ignore[arg-type]
            matter_id="MATTER-001",
            expected_revision=1,
            evidence_db=evidence_db,
        )


def test_invalidation_api_is_exposed() -> None:
    assert callable(register_issue_source_dependency)
    assert callable(invalidate_source_dependents)


def test_repeated_binding_still_rejects_a_stale_expected_revision(
    tmp_path, monkeypatch
) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(matter_id="MATTER-001", title="Review")
    provenance = {
        "evidence_snapshot_hash": "a" * 64,
        "evidence_db_sha256": "b" * 64,
        "schema_version": 4,
    }
    monkeypatch.setattr(
        "evidence_review.review_matter.source_binding.finalized_evidence_provenance",
        lambda _path: provenance,
    )

    first = bind_finalized_evidence(
        store,
        matter_id="MATTER-001",
        expected_revision=1,
        evidence_db=tmp_path / "evidence.sqlite",
    )
    assert first.revision == 2

    with pytest.raises(MatterRevisionConflict, match="MATTER_REVISION_CONFLICT"):
        bind_finalized_evidence(
            store,
            matter_id="MATTER-001",
            expected_revision=1,
            evidence_db=tmp_path / "evidence.sqlite",
        )


def test_changed_source_retains_issue_with_explicitly_separate_dependency(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(
        matter_id="MATTER-001",
        title="Review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Question one",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
            MatterIssue(
                issue_id="ISSUE-002",
                question="Question two",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
    )
    registered = register_issue_source_dependency(
        store,
        "MATTER-001",
        1,
        "ISSUE-001",
        "SOURCE-001",
        "a" * 64,
    )
    registered = register_issue_source_dependency(
        store,
        "MATTER-001",
        registered.revision,
        "ISSUE-002",
        "SOURCE-002",
        "c" * 64,
    )

    invalidated = invalidate_source_dependents(
        store,
        "MATTER-001",
        registered.revision,
        "SOURCE-001",
        "b" * 64,
    )

    assert [issue.work_state for issue in invalidated.issues] == [
        "STALE",
        "READY_TO_FORMALIZE",
    ]


def test_unchanged_source_identity_and_hash_is_a_no_op(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(
        matter_id="MATTER-001",
        title="Review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Question one",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
    )
    registered = register_issue_source_dependency(
        store,
        "MATTER-001",
        1,
        "ISSUE-001",
        "SOURCE-001",
        "a" * 64,
    )
    assert store.list_source_dependencies("MATTER-001") == (
        {
            "issue_id": "ISSUE-001",
            "source_key": "SOURCE-001",
            "source_hash": "a" * 64,
        },
    )

    unchanged = invalidate_source_dependents(
        store,
        "MATTER-001",
        registered.revision,
        "SOURCE-001",
        "a" * 64,
    )

    assert unchanged.revision == registered.revision
    assert unchanged.issues[0].work_state == "READY_TO_FORMALIZE"


def test_invalidation_rejects_a_stale_expected_revision(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(
        matter_id="MATTER-001",
        title="Review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Question one",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
    )
    register_issue_source_dependency(
        store,
        "MATTER-001",
        1,
        "ISSUE-001",
        "SOURCE-001",
        "a" * 64,
    )

    with pytest.raises(MatterRevisionConflict, match="MATTER_REVISION_CONFLICT"):
        invalidate_source_dependents(
            store,
            "MATTER-001",
            1,
            "SOURCE-001",
            "b" * 64,
        )
    assert store.load("MATTER-001").revision == 2
