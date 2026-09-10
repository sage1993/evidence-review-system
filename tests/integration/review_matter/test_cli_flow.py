"""End-to-end contract coverage for the ReviewMatter command surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.command_dispatch import main
from evidence_review.review_matter.store import MatterStore
from tests.unit.review_matter.test_formalization_snapshot import _evidence_database


def _run(arguments: list[str], capsys) -> tuple[int, dict[str, object], str]:
    capsys.readouterr()
    code = main(arguments)
    captured = capsys.readouterr()
    document = json.loads(captured.out) if captured.out else {}
    return code, document, captured.err


def _workspace_with_finalized_evidence(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    evidence_database = workspace / "evidence" / "evidence.sqlite"
    evidence_database.parent.mkdir(parents=True)
    _evidence_database(evidence_database)
    return workspace


def test_review_matter_cli_flow_keeps_work_state_and_formal_identities_distinct(
    tmp_path: Path, capsys
) -> None:
    workspace = _workspace_with_finalized_evidence(tmp_path)
    common = ["--workspace", str(workspace), "--matter-id", "MATTER-001"]

    code, created, error = _run(
        [
            "review-matter",
            "create",
            *common,
            "--title",
            "Exact reference review",
        ],
        capsys,
    )
    assert code == 0, error
    assert created["status"] == "MATTER_CREATED"
    assert created["matter"]["revision"] == 1

    code, issue, error = _run(
        [
            "review-matter",
            "add-issue",
            *common,
            "--expected-revision",
            "1",
            "--issue-id",
            "ISSUE-001",
            "--question",
            "Does the exact source support the review?",
            "--work-state",
            "READY_TO_FORMALIZE",
        ],
        capsys,
    )
    assert code == 0, error
    assert issue["matter"]["revision"] == 2
    assert issue["matter"]["issues"][0]["work_state"] == "READY_TO_FORMALIZE"

    code, bound, error = _run(
        [
            "review-matter",
            "bind-evidence",
            *common,
            "--expected-revision",
            "2",
        ],
        capsys,
    )
    assert code == 0, error
    assert bound["matter"]["revision"] == 3

    code, search, error = _run(
        ["review-matter", "search", *common, "--query", "exact reference"], capsys
    )
    assert code == 0, error
    assert search["status"] == "NAVIGATION_RESULTS"
    assert search["hits"][0]["evidence_id"] == "EVID-SNAP-1"

    code, selected, error = _run(
        [
            "review-matter",
            "select-evidence",
            *common,
            "--expected-revision",
            "3",
            "--evidence-id",
            "EVID-SNAP-1",
            "--query",
            "exact reference",
        ],
        capsys,
    )
    assert code == 0, error
    assert selected["matter"]["revision"] == 4

    code, status, error = _run(["review-matter", "status", *common], capsys)
    assert code == 0, error
    assert status["status"] == "MUTABLE_MATTER_WORK"
    assert status["matter"]["revision"] == 4
    assert "snapshot_id" not in status
    assert "run_id" not in status

    code, formalized, error = _run(
        [
            "review-matter",
            "formalize",
            *common,
            "--expected-revision",
            "4",
        ],
        capsys,
    )
    assert code == 0, error
    assert formalized["status"] == "WAITING_TRACK_A"
    assert formalized["snapshot_id"].startswith("SNAP-")
    assert formalized["run_id"].startswith("RUN-")
    assert formalized["matter_revision"] == 4


def test_review_matter_cli_rejects_stale_revision_without_partial_mutation(
    tmp_path: Path, capsys
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    common = ["--workspace", str(workspace), "--matter-id", "MATTER-001"]
    code, _created, error = _run(
        ["review-matter", "create", *common, "--title", "Review"], capsys
    )
    assert code == 0, error

    code, _result, error = _run(
        [
            "review-matter",
            "add-issue",
            *common,
            "--expected-revision",
            "0",
            "--issue-id",
            "ISSUE-001",
            "--question",
            "Check width",
        ],
        capsys,
    )
    assert code == 2
    assert "MATTER_REVISION_CONFLICT" in error

    with MatterStore(workspace / "matter.sqlite") as store:
        matter = store.load("MATTER-001")
    assert matter.revision == 1
    assert matter.issues == ()


def test_invalid_create_id_does_not_create_matter_store(
    tmp_path: Path, capsys
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    code, _result, error = _run(
        [
            "review-matter",
            "create",
            "--workspace",
            str(workspace),
            "--matter-id",
            "bad/id",
            "--title",
            "Review",
        ],
        capsys,
    )

    assert code == 2
    assert "matter_id" in error
    assert not (workspace / "matter.sqlite").exists()
    assert tuple(workspace.iterdir()) == ()


def test_add_issue_accepts_dependency_on_existing_issue(
    tmp_path: Path, capsys
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    common = ["--workspace", str(workspace), "--matter-id", "MATTER-001"]

    code, _result, error = _run(
        ["review-matter", "create", *common, "--title", "Review"], capsys
    )
    assert code == 0, error

    code, _result, error = _run(
        [
            "review-matter",
            "add-issue",
            *common,
            "--expected-revision",
            "1",
            "--issue-id",
            "ISSUE-001",
            "--question",
            "Check width",
        ],
        capsys,
    )
    assert code == 0, error

    code, result, error = _run(
        [
            "review-matter",
            "add-issue",
            *common,
            "--expected-revision",
            "2",
            "--issue-id",
            "ISSUE-002",
            "--question",
            "Check height after width",
            "--depends-on",
            "ISSUE-001",
        ],
        capsys,
    )

    assert code == 0, error
    assert result["matter"]["revision"] == 3
    assert result["matter"]["issues"][1]["depends_on"] == ["ISSUE-001"]


def test_add_issue_rejects_self_dependency_without_mutation(
    tmp_path: Path, capsys
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    common = ["--workspace", str(workspace), "--matter-id", "MATTER-001"]

    code, _result, error = _run(
        ["review-matter", "create", *common, "--title", "Review"], capsys
    )
    assert code == 0, error

    code, _result, error = _run(
        [
            "review-matter",
            "add-issue",
            *common,
            "--expected-revision",
            "1",
            "--issue-id",
            "ISSUE-001",
            "--question",
            "Self-dependent issue",
            "--depends-on",
            "ISSUE-001",
        ],
        capsys,
    )

    assert code == 2
    assert "issue cannot depend on itself" in error
    with MatterStore(workspace / "matter.sqlite") as store:
        matter = store.load("MATTER-001")
    assert matter.revision == 1
    assert matter.issues == ()


@pytest.mark.parametrize("stage", [
    "status",
    "add-issue",
    "bind-evidence",
    "search",
    "select-evidence",
    "formalize",
])
def test_missing_matter_operations_do_not_create_matter_store(
    tmp_path: Path, capsys, stage: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    common = ["--workspace", str(workspace), "--matter-id", "MATTER-MISSING"]
    stage_arguments = {
        "status": [],
        "add-issue": [
            "--expected-revision", "1", "--issue-id", "ISSUE-001",
            "--question", "Check width",
        ],
        "bind-evidence": ["--expected-revision", "1"],
        "search": ["--query", "reference"],
        "select-evidence": [
            "--expected-revision", "1", "--evidence-id", "EVID-001",
            "--query", "reference",
        ],
        "formalize": ["--expected-revision", "1"],
    }

    code, _result, error = _run(
        ["review-matter", stage, *common, *stage_arguments[stage]], capsys
    )

    assert code == 2
    assert "MATTER_NOT_FOUND" in error
    assert not (workspace / "matter.sqlite").exists()
    assert tuple(workspace.iterdir()) == ()


def test_invalid_matter_id_does_not_create_matter_store(
    tmp_path: Path, capsys
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    code, _result, error = _run(
        [
            "review-matter",
            "add-issue",
            "--workspace",
            str(workspace),
            "--matter-id",
            "bad/id",
            "--expected-revision",
            "1",
            "--issue-id",
            "ISSUE-001",
            "--question",
            "Check width",
        ],
        capsys,
    )

    assert code == 2
    assert "matter_id" in error
    assert not (workspace / "matter.sqlite").exists()
    assert tuple(workspace.iterdir()) == ()


@pytest.mark.parametrize("stage", ["search", "select-evidence"])
def test_navigation_sidecar_failure_is_a_stable_cli_error(
    tmp_path: Path, capsys, stage: str
) -> None:
    workspace = _workspace_with_finalized_evidence(tmp_path)
    common = ["--workspace", str(workspace), "--matter-id", "MATTER-001"]
    code, _created, error = _run(
        ["review-matter", "create", *common, "--title", "Review"], capsys
    )
    assert code == 0, error

    sidecar = workspace / "evidence" / "evidence.sqlite-wal"
    sidecar.write_bytes(b"sidecar")
    arguments = [*common, "--query", "exact reference"]
    if stage == "select-evidence":
        arguments.extend(
            [
                "--expected-revision",
                "1",
                "--evidence-id",
                "EVID-SNAP-1",
            ]
        )
    code, _result, error = _run(
        ["review-matter", stage, *arguments], capsys
    )

    assert code == 2
    assert "EVIDENCE_DATABASE_SIDECAR_PRESENT" in error
