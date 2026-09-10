from __future__ import annotations

from pathlib import Path

from evidence_review.review_matter.service import ReviewMatterService
from evidence_review.workbench.local_server import create_workbench_server

MATTER_ID = "MATTER-001"
TOKEN = "a" * 43
REVIEWER_ID = "reviewer-01"


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ReviewMatterService.open(workspace).create(
        matter_id=MATTER_ID,
        title="Workbench route tests",
    )
    return workspace


def test_workbench_routes_are_tokenized_and_separate_from_formal_review(
    tmp_path: Path,
) -> None:
    server = create_workbench_server(
        _workspace(tmp_path),
        matter_id=MATTER_ID,
        token=TOKEN,
        reviewer_id=REVIEWER_ID,
    )
    try:
        assert server.path == f"/workbench/{MATTER_ID}/{TOKEN}/state"
        assert server.routes == {
            "state": "GET",
            "issues": "POST",
            "evidence/bind": "POST",
            "evidence/search": "GET",
            "evidence/select": "POST",
            "formalize": "POST",
        }
    finally:
        server.server_close()


def test_workbench_mutations_require_expected_revision_and_reject_client_reviewer_override(
    tmp_path: Path,
) -> None:
    server = create_workbench_server(
        _workspace(tmp_path),
        matter_id=MATTER_ID,
        token=TOKEN,
        reviewer_id=REVIEWER_ID,
    )
    try:
        routes = server.route_contracts
        assert routes["issues"].required_fields == {
            "expected_revision",
            "issue_id",
            "question",
            "work_state",
            "depends_on",
        }
        assert "reviewer_id" not in routes["issues"].allowed_fields
        assert routes["formalize"].required_fields == {"expected_revision"}
    finally:
        server.server_close()
