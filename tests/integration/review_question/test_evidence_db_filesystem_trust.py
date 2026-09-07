from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.cli import main
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.index import build_fts_index
from evidence_review.review_question import prepare_review_question


def _workspace(path: Path) -> Path:
    database = path / "evidence" / "evidence.sqlite"
    database.parent.mkdir(parents=True)
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(store, EvidenceSnapshot())
        build_fts_index(store.require_connection())
    return path


def _file_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except OSError as error:
        pytest.skip(f"evidence database symlink creation unavailable: {error}")


def test_prepare_review_question_rejects_evidence_database_link_escape(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    database = workspace / "evidence" / "evidence.sqlite"
    external = tmp_path / "external-evidence.sqlite"
    database.rename(external)
    _file_link(database, external)

    with pytest.raises((ValueError, OSError), match="symlink|reparse|evidence"):
        prepare_review_question(workspace, "filesystem trust")

    assert not (workspace / "runs").exists()


def test_prepare_review_question_rejects_linked_existing_run_artifact(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_question(workspace, "filesystem trust")
    run_directory = workspace / "runs" / prepared.run_id
    artifact = run_directory / "evidence-query.json"
    external = tmp_path / "external-evidence-query.json"
    external.write_bytes(artifact.read_bytes())
    artifact.unlink()
    _file_link(artifact, external)

    with pytest.raises(ValueError, match="symlink|reparse"):
        prepare_review_question(workspace, "filesystem trust")


def test_query_cli_rejects_linked_evidence_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    database = workspace / "evidence" / "evidence.sqlite"
    external = tmp_path / "external-evidence.sqlite"
    database.rename(external)
    _file_link(database, external)
    request = tmp_path / "query.json"
    request.write_text(
        json.dumps(
            {
                "question": "filesystem trust",
                "expansions": [],
                "synonym_manifest": {},
                "filters": {},
                "clause_ids": [],
                "seed_ids": [],
                "graph_depth": 1,
                "limit": 10,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "retrieved.json"

    exit_code = main(
        [
            "query",
            "--db",
            str(database),
            "--request",
            str(request),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 2
    assert "symlink" in capsys.readouterr().err
    assert not output.exists()
