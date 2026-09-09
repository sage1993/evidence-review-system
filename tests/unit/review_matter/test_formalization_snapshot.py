from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_matter.contracts import MatterIssue, MatterSourceBinding
from evidence_review.review_matter.source_binding import bind_finalized_evidence
from evidence_review.review_matter.store import MatterStore


def _snapshot_module():
    try:
        return importlib.import_module("evidence_review.review_matter.snapshot")
    except ModuleNotFoundError as error:
        pytest.fail(f"FORMALIZATION_SNAPSHOT_MODULE_MISSING: {error}")


def _evidence_database(path: Path, *, text: str = "Exact reference text") -> dict[str, object]:
    with EvidenceStore(path, create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-SNAP-1", "title": "Snapshot source"},),
                revisions=(
                    {
                        "id": "REV-SNAP-1",
                        "document_id": "DOC-SNAP-1",
                        "source_hash": "a" * 64,
                        "byte_size": len(text.encode("utf-8")),
                        "page_count": 1,
                    },
                ),
                pages=(
                    {
                        "id": "PAGE-SNAP-1",
                        "revision_id": "REV-SNAP-1",
                        "page_number": 1,
                        "width": 600.0,
                        "height": 800.0,
                    },
                ),
                elements=(
                    {
                        "id": "EVID-SNAP-1",
                        "page_id": "PAGE-SNAP-1",
                        "element_type": "paragraph",
                        "raw_json": {"text": text},
                        "raw_text": text,
                        "normalized_text": text,
                        "raw_payload_hash": "d" * 64,
                        "bbox": [10.0, 10.0, 500.0, 30.0],
                        "parser_order": 0,
                    },
                ),
            ),
        )
        finalize_evidence_database(store)
    return finalized_evidence_provenance(path)


def _matter_store(
    path: Path,
    provenance: dict[str, object],
    *,
    state: str = "READY_TO_FORMALIZE",
) -> MatterStore:
    store = MatterStore(path)
    store.create(
        matter_id="MATTER-SNAP-1",
        title="Snapshot review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-SNAP-1",
                question="Does the exact source support the review?",
                work_state=state,
                depends_on=(),
            ),
        ),
        source_bindings=(
            MatterSourceBinding(
                binding_id="BIND-SNAP-1",
                document_id="DOC-SNAP-1",
                revision_id="REV-SNAP-1",
                page_number=1,
                evidence_id="EVID-SNAP-1",
                bbox=(10.0, 10.0, 500.0, 30.0),
                source_hash="a" * 64,
                evidence_snapshot_hash=str(provenance["evidence_snapshot_hash"]),
                evidence_db_sha256=str(provenance["evidence_db_sha256"]),
            ),
        ),
    )
    bind_finalized_evidence(
        store,
        matter_id="MATTER-SNAP-1",
        expected_revision=1,
        evidence_db=Path(provenance["database_path"]),
    )
    return store


def test_formalization_snapshot_freezes_exact_matter_and_evidence_identity(tmp_path: Path) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    provenance = _evidence_database(evidence_db)
    provenance["database_path"] = str(evidence_db)
    store = _matter_store(tmp_path / "matter.sqlite", provenance)

    snapshot = _snapshot_module().create_formalization_snapshot(
        store, "MATTER-SNAP-1", 2, evidence_db
    )

    assert snapshot.matter_id == "MATTER-SNAP-1"
    assert snapshot.matter_revision == 2
    assert snapshot.evidence_snapshot_hash == provenance["evidence_snapshot_hash"]
    assert snapshot.evidence_db_sha256 == provenance["evidence_db_sha256"]
    assert snapshot.selected_evidence[0].text == "Exact reference text"
    assert snapshot.review_scope.origin == "EXPLICIT_USER"
    assert not hasattr(snapshot, "final_status")


def test_snapshot_blocks_non_ready_matter_issue_without_persisting(tmp_path: Path) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    provenance = _evidence_database(evidence_db)
    provenance["database_path"] = str(evidence_db)
    store = _matter_store(tmp_path / "matter.sqlite", provenance, state="STALE")

    with pytest.raises(ValueError, match="NOT_READY|STALE|FORMALIZATION"):
        _snapshot_module().create_formalization_snapshot(
            store, "MATTER-SNAP-1", 2, evidence_db
        )

    assert _snapshot_module().list_formalization_snapshots(store) == ()


def test_snapshot_rejects_selected_evidence_identity_mismatch(tmp_path: Path) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    provenance = _evidence_database(evidence_db)
    provenance["database_path"] = str(evidence_db)
    store = _matter_store(tmp_path / "matter.sqlite", provenance)
    store.connection.execute(
        "UPDATE matters SET document_json = replace(document_json, 'EVID-SNAP-1', 'EVID-TAMPERED')"
    )
    store.connection.commit()

    with pytest.raises(ValueError):
        _snapshot_module().create_formalization_snapshot(
            store, "MATTER-SNAP-1", 2, evidence_db
        )


def test_snapshot_create_only_retry_is_deterministic(tmp_path: Path) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    provenance = _evidence_database(evidence_db)
    provenance["database_path"] = str(evidence_db)
    store = _matter_store(tmp_path / "matter.sqlite", provenance)
    module = _snapshot_module()

    first = module.create_formalization_snapshot(store, "MATTER-SNAP-1", 2, evidence_db)
    second = module.create_formalization_snapshot(store, "MATTER-SNAP-1", 2, evidence_db)

    assert first.snapshot_id == second.snapshot_id
    assert (
        module.formalization_snapshot_document(first)
        == module.formalization_snapshot_document(second)
    )
    assert len(module.list_formalization_snapshots(store)) == 1
