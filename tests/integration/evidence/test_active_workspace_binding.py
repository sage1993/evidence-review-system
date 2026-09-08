from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.index import build_fts_index
from evidence_review.workspace_binding import (
    bind_active_workspace,
    resolve_active_workspace,
)


def _workspace(root: Path, *, finalized: bool) -> Path:
    workspace = root.resolve()
    database = workspace / "evidence" / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-1", "title": "Binding test"},),
            ),
        )
        if finalized:
            finalize_evidence_database(store)
        else:
            build_fts_index(store.require_connection())
    return workspace


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_finalized_binding_uses_exact_file_sha_and_resolve_is_read_only(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    workspace = _workspace(tmp_path / "workspace", finalized=True)
    database = workspace / "evidence" / "evidence.sqlite"
    before = _file_sha(database)

    binding = bind_active_workspace(repository_root, workspace)
    assert binding.evidence_db_sha256 == before
    assert _file_sha(database) == before

    resolved = resolve_active_workspace(repository_root)
    assert resolved == binding
    assert _file_sha(database) == before
    assert not database.with_name("evidence.sqlite-wal").exists()
    assert not database.with_name("evidence.sqlite-shm").exists()
    assert not database.with_name("evidence.sqlite-journal").exists()


def test_unfinalized_workspace_is_rejected_before_binding(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    workspace = _workspace(tmp_path / "workspace", finalized=False)

    with pytest.raises(
        ValueError,
        match="ACTIVE_WORKSPACE_INVALID.*EVIDENCE_DATABASE_NOT_FINALIZED",
    ):
        bind_active_workspace(repository_root, workspace)

    assert not (repository_root / ".ers" / "active-workspace.json").exists()


def test_tampered_bound_database_is_stale_before_review(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    workspace = _workspace(tmp_path / "workspace", finalized=True)
    bind_active_workspace(repository_root, workspace)

    database = workspace / "evidence" / "evidence.sqlite"
    database.write_bytes(b"tampered database")

    with pytest.raises(ValueError, match="ACTIVE_WORKSPACE_STALE"):
        resolve_active_workspace(repository_root)
