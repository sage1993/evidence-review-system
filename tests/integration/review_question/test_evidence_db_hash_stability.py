from __future__ import annotations

import hashlib
from pathlib import Path

from evidence_review.review_question import (
    prepare_review_question,
    submit_question_track_a,
    submit_question_track_b,
)
from evidence_review.workspace_binding import (
    bind_active_workspace,
    resolve_active_workspace,
)
from tests.integration.review_question.test_review_metrics import (
    _page_assets,
    _track_a,
    _track_b,
    _workspace,
)


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sidecars(database: Path) -> tuple[Path, ...]:
    return tuple(
        database.with_name(f"{database.name}{suffix}")
        for suffix in ("-wal", "-shm", "-journal")
    )


def test_formal_review_preserves_finalized_evidence_database_bytes(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    database = workspace / "evidence" / "evidence.sqlite"
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    sha_a = _file_sha(database)
    binding = bind_active_workspace(repository_root, workspace)
    sha_b = _file_sha(database)
    assert binding.evidence_db_sha256 == sha_a
    assert resolve_active_workspace(repository_root) == binding
    sha_b_resolved = _file_sha(database)

    prepared = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    sha_c = _file_sha(database)
    run_directory = workspace / "runs" / prepared.run_id
    _page_assets(workspace)

    submit_question_track_a(workspace, prepared.run_id, _track_a(run_directory))
    sha_d = _file_sha(database)

    finalized = submit_question_track_b(
        workspace,
        prepared.run_id,
        _track_b(run_directory),
    )
    sha_e = _file_sha(database)
    sha_f = _file_sha(database)

    assert finalized.packet_path.is_file()
    assert len({sha_a, sha_b, sha_b_resolved, sha_c, sha_d, sha_e, sha_f}) == 1
    assert binding.evidence_db_sha256 == sha_a
    assert all(not sidecar.exists() for sidecar in _sidecars(database))
