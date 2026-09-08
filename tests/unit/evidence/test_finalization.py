from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
from types import ModuleType

import pytest

from evidence_review.evidence.clause_rebuild import (
    ensure_clause_index,
    materialize_clause_structure,
)
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.snapshot import compute_snapshot_hash
from evidence_review.evidence.store import EvidenceStore


def _finalization_module() -> ModuleType:
    try:
        return importlib.import_module("evidence_review.evidence.finalization")
    except ModuleNotFoundError as error:
        pytest.fail(f"evidence finalization API is missing: {error}")


def _element(
    element_id: str,
    page_id: str,
    order: int,
    text: str,
) -> dict[str, object]:
    return {
        "id": element_id,
        "page_id": page_id,
        "element_type": "paragraph",
        "raw_json": {"text": text},
        "raw_text": text,
        "normalized_text": text,
        "raw_payload_hash": f"{order + 1:x}" * 64,
        "bbox": [10.0, float(order * 20), 550.0, float(order * 20 + 15)],
        "parser_order": order,
    }


def _snapshot() -> EvidenceSnapshot:
    return EvidenceSnapshot(
        documents=(
            {"id": "DOC-LOCAL", "title": "Local Ordinance"},
            {"id": "DOC-EXT", "title": "External Authority"},
        ),
        revisions=(
            {
                "id": "REV-LOCAL",
                "document_id": "DOC-LOCAL",
                "source_hash": "a" * 64,
                "byte_size": 100,
                "page_count": 1,
            },
            {
                "id": "REV-EXT",
                "document_id": "DOC-EXT",
                "source_hash": "b" * 64,
                "byte_size": 100,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": "P-LOCAL",
                "revision_id": "REV-LOCAL",
                "page_number": 1,
                "width": 595.0,
                "height": 842.0,
            },
            {
                "id": "P-EXT",
                "revision_id": "REV-EXT",
                "page_number": 1,
                "width": 595.0,
                "height": 842.0,
            },
        ),
        elements=(
            _element("E-LOCAL-1", "P-LOCAL", 0, "제1조(설치기준)"),
            _element(
                "E-LOCAL-2",
                "P-LOCAL",
                1,
                "① 「External Authority」 제27조에 따라 주차장을 설치하여야 한다.",
            ),
            _element("E-EXT-1", "P-EXT", 0, "제27조(주차장)"),
            _element("E-EXT-2", "P-EXT", 1, "주택의 주차장 설치기준을 정한다."),
        ),
    )


def _create_element_only_database(path: Path) -> None:
    with EvidenceStore(path, create=True) as store:
        ingest_snapshot(store, _snapshot())


def test_finalize_materializes_complete_canonical_state_before_hash_commit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(store, _snapshot())
        finalization = _finalization_module()
        state = finalization.finalize_evidence_database(store)

        connection = store.require_connection()
        assert connection.execute("SELECT COUNT(*) FROM clauses").fetchone()[0] > 0
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM links
            WHERE relation_type = 'rule_source'
            """
        ).fetchone()[0] > 0
        assert connection.execute(
            "SELECT COUNT(*) FROM clause_retrieval_records"
        ).fetchone()[0] > 0
        assert store.scalar(
            "SELECT value FROM snapshot_meta WHERE key = 'lifecycle_state'"
        ) == "FINALIZED"
        assert store.scalar(
            "SELECT value FROM snapshot_meta WHERE key = 'finalization_version'"
        ) == "1"
        stored_hash = store.scalar(
            "SELECT value FROM snapshot_meta WHERE key = 'snapshot_hash'"
        )
        retrieval_hash = store.scalar(
            "SELECT value FROM retrieval_meta WHERE key = 'snapshot_hash'"
        )
        assert state.snapshot_hash == stored_hash == compute_snapshot_hash(store)
        assert retrieval_hash == stored_hash
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_validate_finalized_evidence_is_idempotent_and_read_only(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(store, _snapshot())
        finalization = _finalization_module()
        finalization.finalize_evidence_database(store)

    before = hashlib.sha256(database.read_bytes()).hexdigest()
    with EvidenceStore(database) as store:
        finalization = _finalization_module()
        first = finalization.validate_finalized_evidence(store)
        second = finalization.validate_finalized_evidence(store)
        assert first == second
    after = hashlib.sha256(database.read_bytes()).hexdigest()
    assert after == before


def test_validate_finalized_evidence_rejects_missing_lifecycle_metadata(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    _create_element_only_database(database)

    with EvidenceStore(database) as store:
        finalization = _finalization_module()
        with pytest.raises(RuntimeError, match="EVIDENCE_DATABASE_NOT_FINALIZED"):
            finalization.validate_finalized_evidence(store)


def test_validate_finalized_evidence_rejects_logical_snapshot_tamper(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(store, _snapshot())
        finalization = _finalization_module()
        finalization.finalize_evidence_database(store)
        connection = store.require_connection()
        connection.execute(
            "UPDATE documents SET title = 'Tampered' WHERE id = 'DOC-LOCAL'"
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="EVIDENCE_LOGICAL_SNAPSHOT_MISMATCH"):
            finalization.validate_finalized_evidence(store)


def test_validate_finalized_evidence_rejects_stale_retrieval_index(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(store, _snapshot())
        finalization = _finalization_module()
        finalization.finalize_evidence_database(store)
        connection = store.require_connection()
        connection.execute(
            "UPDATE retrieval_meta SET value = ? WHERE key = 'snapshot_hash'",
            ("0" * 64,),
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="EVIDENCE_INDEX_STALE"):
            finalization.validate_finalized_evidence(store)


def test_clause_structure_materialization_does_not_build_retrieval_projection(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(store, _snapshot())
        connection = store.require_connection()
        assert materialize_clause_structure(connection) is True
        assert connection.execute("SELECT COUNT(*) FROM clauses").fetchone()[0] > 0
        assert connection.execute(
            "SELECT COUNT(*) FROM clause_retrieval_records"
        ).fetchone() == (0,)


def test_legacy_clause_index_helper_rejects_finalized_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(store, _snapshot())
        finalization = _finalization_module()
        finalization.finalize_evidence_database(store)
        with pytest.raises(RuntimeError, match="EVIDENCE_DATABASE_FINALIZED"):
            ensure_clause_index(store.require_connection())
