from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from evidence_review.contracts.question_plan import QuestionIssue, QuestionPlan, SearchRequest
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.planned_review_question import prepare_planned_review_question
from evidence_review.retrieval.index import build_fts_index


def _plan() -> QuestionPlan:
    question = "주차장 설치기준은 무엇인가"
    return QuestionPlan(
        original_question=question,
        facts=(),
        assumptions=(),
        issues=(
            QuestionIssue(
                id="I1",
                question=question,
                depends_on=(),
                required_evidence_roles=("rule",),
            ),
        ),
        legal_anchors=(),
        search_requests=(
            SearchRequest(
                id="S1",
                issue_ids=("I1",),
                text="주차장 설치기준",
                kind="phrase",
                source="planner",
                role="rule",
            ),
        ),
    )


def _workspace(path: Path) -> Path:
    evidence_directory = path / "evidence"
    evidence_directory.mkdir(parents=True)
    with EvidenceStore(evidence_directory / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, EvidenceSnapshot())
        build_fts_index(store.require_connection())
    return path


def _directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            pytest.skip(
                "directory junction creation unavailable: "
                f"exit={completed.returncode}; detail={detail or '<empty>'}"
            )
        return
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink creation unavailable: {error}")


def test_planned_prepare_rejects_linked_run_before_external_artifact_write(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_planned_review_question(workspace, _plan())
    real_run = workspace / "runs" / prepared.run_id
    external_run = tmp_path / "external-run"
    real_run.rename(external_run)
    (external_run / "question-plan.json").unlink()
    _directory_link(real_run, external_run)

    with pytest.raises(ValueError, match="symlink|reparse"):
        prepare_planned_review_question(workspace, _plan())

    assert not (external_run / "question-plan.json").exists()
    shutil.rmtree(external_run)
