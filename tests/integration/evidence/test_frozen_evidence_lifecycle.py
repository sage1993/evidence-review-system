from __future__ import annotations

import hashlib
import importlib
import sqlite3
from pathlib import Path

import pytest

from evidence_review.evidence.ingest import ingest_snapshot
from evidence_review.evidence.snapshot import compute_snapshot_hash
from evidence_review.evidence.store import EvidenceStore
from tests.integration.review_question.test_real_workspace_clause_repair_e2e import (
    _snapshot,
)


def _finalize_evidence_database(store: EvidenceStore) -> None:
    try:
        finalization = importlib.import_module("evidence_review.evidence.finalization")
    except ModuleNotFoundError as error:
        pytest.fail(f"evidence finalization API is missing: {error}")
    finalize = getattr(finalization, "finalize_evidence_database", None)
    if finalize is None:
        pytest.fail("evidence finalization API is missing: finalize_evidence_database")
    finalize(store)


def test_finalization_produces_complete_frozen_canonical_state(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(store, _snapshot())
        _finalize_evidence_database(store)

        connection = store.require_connection()
        assert connection.execute("SELECT COUNT(*) FROM clauses").fetchone()[0] > 0
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM links
            WHERE relation_type IN (
                'rule_source', 'source_not_ingested', 'reference_target_missing'
            )
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

        stored_snapshot_hash = store.scalar(
            "SELECT value FROM snapshot_meta WHERE key = 'snapshot_hash'"
        )
        retrieval_snapshot_hash = store.scalar(
            "SELECT value FROM retrieval_meta WHERE key = 'snapshot_hash'"
        )
        assert stored_snapshot_hash == compute_snapshot_hash(store)
        assert retrieval_snapshot_hash == stored_snapshot_hash
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    before = hashlib.sha256(database.read_bytes()).hexdigest()
    with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM clauses").fetchone()[0] > 0
        assert connection.execute(
            "SELECT value FROM snapshot_meta WHERE key = 'lifecycle_state'"
        ).fetchone() == ("FINALIZED",)
    after = hashlib.sha256(database.read_bytes()).hexdigest()
    assert after == before
