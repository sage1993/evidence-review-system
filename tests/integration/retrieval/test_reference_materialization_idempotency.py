from __future__ import annotations

from pathlib import Path

from evidence_review.evidence.clause_rebuild import ensure_clause_index
from evidence_review.evidence.ingest import ingest_snapshot
from evidence_review.evidence.reference_materialization import (
    materialize_legal_reference_links,
)
from evidence_review.evidence.snapshot import evidence_snapshot_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.workspace_binding import (
    bind_active_workspace,
    resolve_active_workspace,
)

from tests.integration.retrieval.test_external_reference_resolution import (
    _article_source,
    _snapshot,
)


def test_unchanged_reference_materialization_is_physically_idempotent(
    tmp_path: Path,
) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot(source_text=_article_source()))
        connection = store.require_connection()
        ensure_clause_index(connection)

        before = evidence_snapshot_provenance(connection)
        assert materialize_legal_reference_links(connection) == 0
        after = evidence_snapshot_provenance(connection)

    assert after == before


def test_repeated_clause_indexing_does_not_self_invalidate_active_workspace(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    workspace = tmp_path / "workspace"

    with EvidenceStore(workspace / "evidence" / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot(source_text=_article_source()))
        connection = store.require_connection()
        ensure_clause_index(connection)
        before = evidence_snapshot_provenance(connection)
        bind_active_workspace(repository_root, workspace)

        ensure_clause_index(connection)
        middle = evidence_snapshot_provenance(connection)
        ensure_clause_index(connection)
        after = evidence_snapshot_provenance(connection)

    assert middle == before
    assert after == before
    assert resolve_active_workspace(repository_root).workspace == workspace.resolve()
