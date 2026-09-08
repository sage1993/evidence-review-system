import sqlite3

import pytest

from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_matter.contracts import MatterIssue
from evidence_review.review_matter.events import list_matter_events
from evidence_review.review_matter.invalidation import register_issue_source_dependency
from evidence_review.review_matter.source_binding import bind_finalized_evidence
from evidence_review.review_matter.store import MatterRevisionConflict, MatterStore


def test_unfinalized_evidence_cannot_be_bound_to_matter(tmp_path) -> None:
    matter_db = tmp_path / "review-matters.sqlite"
    evidence_db = tmp_path / "evidence.sqlite"
    evidence_db.write_bytes(b"not-a-finalized-sqlite")
    store = MatterStore(matter_db)
    store.create(matter_id="MATTER-001", title="Review")
    with pytest.raises(ValueError, match="MATTER_EVIDENCE_BINDING_INVALID"):
        bind_finalized_evidence(
            store,
            matter_id="MATTER-001",
            expected_revision=1,
            evidence_db=evidence_db,
        )
    assert store.load("MATTER-001").revision == 1
    assert store.get_evidence_binding("MATTER-001") is None


def _finalized_database(path, source_hash: str, title: str) -> None:
    with EvidenceStore(path, create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-1", "title": title},),
                revisions=(
                    {
                        "id": "REV-1",
                        "document_id": "DOC-1",
                        "source_hash": source_hash,
                        "byte_size": 10,
                        "page_count": 1,
                    },
                ),
                pages=(
                    {
                        "id": "PAGE-1",
                        "revision_id": "REV-1",
                        "page_number": 1,
                        "width": 600.0,
                        "height": 800.0,
                    },
                ),
                elements=(
                    {
                        "id": "ELEMENT-1",
                        "page_id": "PAGE-1",
                        "element_type": "paragraph",
                        "raw_json": {"text": title},
                        "raw_text": title,
                        "normalized_text": title,
                        "raw_payload_hash": "d" * 64,
                        "bbox": [10.0, 10.0, 500.0, 30.0],
                        "parser_order": 0,
                    },
                ),
            ),
        )
        finalize_evidence_database(store)


def test_finalized_binding_stores_exact_provenance_without_writing_evidence(
    tmp_path,
) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    _finalized_database(evidence_db, "a" * 64, "Original")
    before = evidence_db.read_bytes()
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(matter_id="MATTER-001", title="Review")

    bound = bind_finalized_evidence(
        store,
        matter_id="MATTER-001",
        expected_revision=1,
        evidence_db=evidence_db,
    )
    provenance = finalized_evidence_provenance(evidence_db)
    assert bound.revision == 2
    assert store.get_evidence_binding("MATTER-001") == {
        "evidence_snapshot_hash": provenance["evidence_snapshot_hash"],
        "evidence_db_sha256": provenance["evidence_db_sha256"],
        "schema_version": provenance["schema_version"],
        "bound_revision": 2,
    }
    assert evidence_db.read_bytes() == before
    assert [event.kind for event in list_matter_events(store, "MATTER-001")] == [
        "EVIDENCE_BOUND"
    ]
    assert bind_finalized_evidence(
        store,
        matter_id="MATTER-001",
        expected_revision=2,
        evidence_db=evidence_db,
    ).revision == 2


def test_sidecar_backed_evidence_cannot_be_bound(tmp_path) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    _finalized_database(evidence_db, "a" * 64, "Original")
    sidecar = evidence_db.with_name(evidence_db.name + "-wal")
    sidecar.write_bytes(b"sidecar")
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(matter_id="MATTER-001", title="Review")

    with pytest.raises(ValueError, match="MATTER_EVIDENCE_BINDING_INVALID"):
        bind_finalized_evidence(
            store,
            matter_id="MATTER-001",
            expected_revision=1,
            evidence_db=evidence_db,
        )
    assert store.load("MATTER-001").revision == 1
    assert store.get_evidence_binding("MATTER-001") is None


def test_stale_logical_snapshot_cannot_be_bound(tmp_path) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    _finalized_database(evidence_db, "a" * 64, "Original")
    with sqlite3.connect(evidence_db) as connection:
        connection.execute(
            "UPDATE snapshot_meta SET value = ? WHERE key = 'snapshot_hash'",
            ("f" * 64,),
        )
        connection.commit()

    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(matter_id="MATTER-001", title="Review")
    with pytest.raises(ValueError, match="MATTER_EVIDENCE_BINDING_INVALID"):
        bind_finalized_evidence(
            store,
            matter_id="MATTER-001",
            expected_revision=1,
            evidence_db=evidence_db,
        )
    assert store.load("MATTER-001").revision == 1
    assert store.get_evidence_binding("MATTER-001") is None


def test_rebinding_changed_evidence_stales_dependent_issue(tmp_path) -> None:
    first_db = tmp_path / "first.sqlite"
    second_db = tmp_path / "second.sqlite"
    _finalized_database(first_db, "a" * 64, "Original")
    _finalized_database(second_db, "b" * 64, "Revised")
    store = MatterStore(tmp_path / "review-matters.sqlite")
    created = store.create(
        matter_id="MATTER-001",
        title="Review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Is the source current?",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
    )
    assert created.revision == 1
    first = bind_finalized_evidence(
        store,
        matter_id="MATTER-001",
        expected_revision=1,
        evidence_db=first_db,
    )
    dependent = register_issue_source_dependency(
        store,
        "MATTER-001",
        first.revision,
        "ISSUE-001",
        "DOC-1",
        "a" * 64,
    )
    rebound = bind_finalized_evidence(
        store,
        matter_id="MATTER-001",
        expected_revision=dependent.revision,
        evidence_db=second_db,
    )
    assert rebound.issues[0].work_state == "STALE"
    assert [event.kind for event in list_matter_events(store, "MATTER-001")] == [
        "EVIDENCE_BOUND",
        "SOURCE_DEPENDENCY_REGISTERED",
        "EVIDENCE_REBOUND",
    ]
    with pytest.raises(MatterRevisionConflict, match="MATTER_REVISION_CONFLICT"):
        bind_finalized_evidence(
            store,
            matter_id="MATTER-001",
            expected_revision=first.revision,
            evidence_db=second_db,
        )
