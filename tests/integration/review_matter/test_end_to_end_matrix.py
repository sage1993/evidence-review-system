from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from threading import Thread

import pytest

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.case_visual import prepare_case_visual_sources
from evidence_review.drawing_review.visual_pages import prepare_visual_page_assets
from evidence_review.review_matter.events import list_matter_events
from evidence_review.review_matter.formal_run_binding import (
    bind_formal_run,
    list_formal_runs,
)
from evidence_review.review_matter.invalidation import invalidate_source_dependents
from evidence_review.review_matter.service import ReviewMatterService
from evidence_review.review_packet.local_server import create_review_server
from evidence_review.workflow.drawing_confirmation import (
    resume_after_confirmation,
    start_drawing_confirmation,
)
from evidence_review.workflow.orchestrator import (
    ingest_pending_references,
    open_review_run,
    prepare_review_run,
    resume_review_run,
)
from evidence_review.workflow.request import decode_review_request
from tests.integration.review_matter.test_multi_run_history import (
    _finalized_formal_run,
    _matter_with_first_snapshot,
    _second_snapshot,
)
from tests.integration.review_packet.test_local_server import _request
from tests.integration.review_question.test_real_review_full_e2e import (
    _assert_claim_issue_lineage,
    _prepare_workspace,
    _track_a_output,
    _track_b_output,
    _write_manifest_bound_outputs,
)
from tests.integration.workflow._reference_helpers import FakeReferenceBackend
from tests.integration.workflow.test_reference_resume_reproducibility import (
    _prepare as _prepare_reference_run,
)
from tests.unit.review_matter.test_formalization_snapshot import (
    _evidence_database,
    _matter_store,
)

SCENARIOS = (
    "navigation_only",
    "planner_formal_review",
    "explicit_scope_formal_review",
    "partial_multi_issue",
    "drawing_confirmation",
    "source_revision_invalidation",
    "two_formal_runs",
    "packet_specific_human_decision",
    "restart_recovery",
    "installed_wheel_runtime",
    "protected_case_visual_cache_identity",
)


def _navigation_only(root: Path) -> None:
    workspace = root / "workspace"
    evidence_db = workspace / "evidence" / "evidence.sqlite"
    evidence_db.parent.mkdir(parents=True)
    _evidence_database(evidence_db)
    service = ReviewMatterService.open(workspace)
    service.create(matter_id="MATTER-NAV-1", title="Navigation acceptance")
    bound = service.bind_evidence(matter_id="MATTER-NAV-1", expected_revision=1)
    result = service.search(matter_id="MATTER-NAV-1", query="exact reference")
    assert result.hits and result.hits[0].evidence_id == "EVID-SNAP-1"
    assert bound.revision == 2
    assert service.status(matter_id="MATTER-NAV-1").revision == 2
    assert service.list_formal_runs(matter_id="MATTER-NAV-1") == ()


def _planner_formal_review(root: Path) -> None:
    plan, evidence_fixture, run_directory = _prepare_workspace(root)
    track_a = _track_a_output(run_directory, evidence_fixture)
    _write_manifest_bound_outputs(
        run_directory, track_a, _track_b_output(track_a, run_directory.name)
    )
    packet = finalize_run(run_directory)
    assert (run_directory / "question-plan.json").is_file()
    assert packet.status == "READY_FOR_HUMAN_REVIEW"
    assert {claim.issue_ids[0] for claim in packet.claims} == {
        issue.id for issue in plan.issues
    }
    _assert_claim_issue_lineage(run_directory, packet)


def _explicit_scope_formal_review(root: Path) -> None:
    workspace = root / "workspace"
    evidence_db = workspace / "evidence" / "evidence.sqlite"
    evidence_db.parent.mkdir(parents=True)
    provenance = _evidence_database(evidence_db)
    provenance["database_path"] = str(evidence_db)
    _matter_store(workspace / "matter.sqlite", provenance)
    formalized = ReviewMatterService.open(workspace).formalize(
        matter_id="MATTER-SNAP-1", expected_revision=2
    )
    request = json.loads(
        (workspace / "runs" / formalized.prepared.run_id / "review-request.json").read_text(
            encoding="utf-8"
        )
    )
    assert formalized.snapshot.review_scope.origin == "EXPLICIT_USER"
    assert request["inputs"]["formalization_snapshot_id"] == formalized.snapshot.snapshot_id
    assert request["inputs"]["matter_id"] == "MATTER-SNAP-1"
    assert request["inputs"]["matter_revision"] == 2
    assert request["inputs"]["evidence_snapshot_provenance"]["evidence_db_sha256"] == (
        formalized.snapshot.evidence_db_sha256
    )


def _partial_multi_issue(root: Path) -> None:
    _, evidence_fixture, run_directory = _prepare_workspace(
        root, omit_issue_ids=frozenset({"I7"})
    )
    track_a = _track_a_output(run_directory, evidence_fixture)
    _write_manifest_bound_outputs(
        run_directory, track_a, _track_b_output(track_a, run_directory.name)
    )
    packet = finalize_run(run_directory)
    by_issue = {item.issue_id: item for item in packet.issue_results}
    assert packet.status == "PARTIALLY_RESOLVED"
    assert by_issue["I7"].status == "UNRESOLVED"
    assert "RETRIEVAL_MISS" in by_issue["I7"].gap_codes
    assert all(
        by_issue[f"I{index}"].status == "RESOLVED" for index in (1, 3, 4, 5, 6)
    )
    assert all("I7" not in claim.issue_ids for claim in packet.claims)


def _drawing_confirmation(root: Path) -> None:
    from pypdf import PdfWriter

    source = root / "case-drawing.pdf"
    writer = PdfWriter()
    for _ in range(17):
        writer.add_blank_page(width=612, height=792)
    with source.open("wb") as stream:
        writer.write(stream)
    case_workspace = root / "case-workspace"
    attachments = prepare_case_visual_sources(case_workspace, case_drawings=(source,))
    pages = prepare_visual_page_assets(case_workspace, attachments)
    assert attachments[0].role == "CASE_DRAWING"
    assert len(pages) == 17
    assert {page.source_sha256 for page in pages} == {attachments[0].sha256}

    runs_root = root / "confirmation" / "runs"
    run_dir = runs_root / "RUN-DRAWING-001"
    original = run_dir / "inputs" / "original" / "drawing.pdf"
    original.parent.mkdir(parents=True)
    original.write_bytes(source.read_bytes())
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    request = decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-DRAWING-001",
            "question": "Does the confirmed drawing resume?",
            "attachments": [
                {
                    "attachment_id": "ATT-DRAW-001",
                    "original_name": "drawing.pdf",
                    "stored_path": "inputs/original/drawing.pdf",
                    "sha256": source_hash,
                    "byte_size": source.stat().st_size,
                    "mime": "application/pdf",
                    "role": "CASE_DRAWING",
                    "role_confirmation": "USER_CONFIRMED",
                    "proposed_role": None,
                }
            ],
        }
    )
    layout = prepare_review_run(
        runs_root, "RUN-DRAWING-001", request, recorded_at="2026-08-04T00:00:00+09:00"
    )
    plan = start_drawing_confirmation(
        layout,
        candidate_ids=("CAND-001",),
        source_sha256=source_hash,
        recorded_at="2026-08-04T00:01:00+09:00",
    )
    assert not plan.engine_allowed
    confirmed_path = layout.machine_dir / "confirmed-inputs.json"
    confirmed_path.write_bytes(
        b'{"format":"evidence-review/confirmed-input-set","inputs":[],"version":1}'
    )
    resumed = resume_after_confirmation(
        layout,
        confirmed_inputs_path=confirmed_path,
        source_sha256=source_hash,
        recorded_at="2026-08-04T00:02:00+09:00",
    )
    assert resumed.engine_allowed
    assert layout.load_state().workflow_state == "READY_TO_EVALUATE"


def _source_revision_invalidation(root: Path) -> None:
    from tests.integration.review_matter.test_revision_invalidation import (
        _matter_store as revision_matter_store,
    )

    store = revision_matter_store(root / "matter.sqlite")
    invalidated = invalidate_source_dependents(
        store,
        "MATTER-REV-1",
        3,
        "SRC-1",
        "b" * 64,
        new_source_revision_id="REV-2",
    )
    assert [issue.work_state for issue in invalidated.issues] == [
        "STALE",
        "STALE",
        "READY_TO_FORMALIZE",
    ]
    assert list_matter_events(store, "MATTER-REV-1")[-1].kind == "ISSUES_INVALIDATED"


def _two_formal_runs(root: Path) -> None:
    workspace, store, first = _matter_with_first_snapshot(root)
    first_run_id, first_hash = _finalized_formal_run(workspace, first)
    second = _second_snapshot(workspace, store)
    second_run_id, second_hash = _finalized_formal_run(workspace, second)
    first_binding = bind_formal_run(
        store,
        "MATTER-SNAP-1",
        first.snapshot_id,
        first_run_id,
        first_hash,
        workspace_root=workspace,
    )
    second_binding = bind_formal_run(
        store,
        "MATTER-SNAP-1",
        second.snapshot_id,
        second_run_id,
        second_hash,
        workspace_root=workspace,
    )
    assert list_formal_runs(store, "MATTER-SNAP-1", workspace_root=workspace) == (
        first_binding,
        second_binding,
    )
    for run_id, expected_hash in ((first_run_id, first_hash), (second_run_id, second_hash)):
        packet_path = workspace / "runs" / run_id / "final-review-packet.json"
        assert packet_path.is_file()
        assert hashlib.sha256(packet_path.read_bytes()).hexdigest() == expected_hash


def _packet_specific_human_decision(root: Path) -> None:
    from evidence_review.review_packet.builder import build_review_view_model
    from evidence_review.review_packet.html_renderer import write_review_html

    workspace, store, first = _matter_with_first_snapshot(root)
    run_one, _first_hash = _finalized_formal_run(workspace, first)
    second = _second_snapshot(workspace, store)
    run_two, _second_hash = _finalized_formal_run(workspace, second)
    page_images = workspace / "page-images"
    page_images.mkdir()
    for run_id in (run_one, run_two):
        directory = workspace / "runs" / run_id
        view_model = build_review_view_model(
            (directory / "final-review-packet.json").read_bytes(),
            workspace / "evidence" / "evidence.sqlite",
        )
        write_review_html(view_model, page_images, directory / "review.html")
    token_one = "a" * 43
    token_two = "b" * 43
    server = create_review_server(
        workspace,
        run_tokens={run_one: token_one, run_two: token_two},
        reviewer_ids={run_one: "reviewer-01", run_two: "reviewer-01"},
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        packet_one = (workspace / "runs" / run_one / "final-review-packet.json").read_bytes()
        packet_hash = hashlib.sha256(packet_one).hexdigest()
        status, result = _request(
            server,
            "POST",
            f"/runs/{run_one}/{token_one}/decision",
            body={
                "reviewer_id": "reviewer-01",
                "packet_hash": packet_hash,
                "decision": "SATISFIED",
                "notes": "packet-specific acceptance",
            },
        )
        assert status == 201
        records = tuple((workspace / "runs" / run_one / "human-decisions").glob("*.json"))
        assert len(records) == 1
        assert json.loads(records[0].read_text(encoding="utf-8"))["packet_hash"] == packet_hash
        assert not (workspace / "runs" / run_two / "human-decisions").exists()
        assert json.loads(packet_one)["human_decision"] is None
        assert json.loads(
            (workspace / "runs" / run_two / "final-review-packet.json").read_text(
                encoding="utf-8"
            )
        )["human_decision"] is None
        assert result["display_status"] == "REVIEW_COMPLETED"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _restart_recovery(root: Path) -> None:
    runs_root, layout = _prepare_reference_run(root)
    first_backend = FakeReferenceBackend()
    first_receipt = ingest_pending_references(layout, first_backend)
    receipt_bytes = layout.reference_receipt_path.read_bytes()
    reopened = open_review_run(runs_root, "RUN-001")
    second_backend = FakeReferenceBackend(snapshot_sha256="c" * 64)
    assert ingest_pending_references(reopened, second_backend) == first_receipt
    assert second_backend.calls == []
    assert reopened.reference_receipt_path.read_bytes() == receipt_bytes
    final = resume_review_run(reopened, recorded_at="2026-08-04T00:01:00+09:00")
    assert final.workflow_state == "READY_TO_EVALUATE"
    events = tuple(path.read_bytes() for path in sorted(reopened.events_dir.glob("*.json")))
    assert resume_review_run(reopened, recorded_at="2026-08-04T00:02:00+09:00") == final
    assert tuple(path.read_bytes() for path in sorted(reopened.events_dir.glob("*.json"))) == events


def _installed_wheel_runtime(root: Path) -> None:
    repository_root = Path(__file__).parents[3]
    wheel_dir = root / "wheel"
    wheel_dir.mkdir()
    built = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--no-cache-dir",
            "-w",
            str(wheel_dir),
            str(repository_root),
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    wheels = tuple(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1
    target = root / "installed"
    installed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(target),
            str(wheels[0]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(target)
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from importlib.resources import files
from pathlib import Path
import evidence_review

assert Path(evidence_review.__file__).resolve().is_relative_to(Path.cwd())
assert files("evidence_review.review_matter").joinpath("schema.sql").is_file()
assert files("evidence_review.workbench").joinpath("assets", "workbench.css").is_file()
print("installed-wheel-runtime-ok")
""",
        ],
        cwd=target,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert "installed-wheel-runtime-ok" in probe.stdout
    cli = subprocess.run(
        [sys.executable, "-m", "evidence_review", "--help"],
        cwd=target,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cli.returncode == 0, cli.stdout + cli.stderr
    assert "review-matter" in cli.stdout


def _protected_case_visual_cache_identity(root: Path) -> None:
    """A case-scoped visual cache must be reachable through the protected route."""
    import base64
    import http.client

    from evidence_review.review_packet.html_renderer import render_review_html
    from tests.integration.review_packet.test_review_workspace_performance import (
        VALID_MINIMAL_PNG,
    )

    run_id = "RUN-CASE-VISUAL-001"
    token = "v" * 43
    case_id = "CASE-VISUAL-001"
    attachment_id = "ATT-CASE-VISUAL-001"
    source_hash = "a" * 64
    image_hash = hashlib.sha256(VALID_MINIMAL_PNG).hexdigest()
    workspace = root / "workspace"
    run_directory = workspace / "runs" / run_id
    run_directory.mkdir(parents=True)
    (run_directory / "final-review-packet.json").write_bytes(
        b'{"human_decision":null,"run_id":"RUN-CASE-VISUAL-001"}'
    )
    model = {
        "run_id": run_id,
        "status": "READY_FOR_HUMAN_REVIEW",
        "display_status": "READY_FOR_HUMAN_REVIEW",
        "question": "case visual cache identity",
        "claims": [],
        "review_items": [],
        "calculations": [],
        "rules": [],
        "exceptions": [],
        "conflicts": [],
        "abstention_reasons": [],
        "summary": {},
        "audit": {},
        "case_visual_review": {
            "status": "VISUAL_ANALYSIS_VALIDATED",
            "pages": [
                {
                    "asset_key": f"{attachment_id}-p1",
                    "attachment_id": attachment_id,
                    "case_id": case_id,
                    "document_name": "case-drawing.pdf",
                    "source_sha256": source_hash,
                    "page": 1,
                    "width": 1.0,
                    "height": 1.0,
                    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                    "image_sha256": image_hash,
                    "data_uri": "data:image/png;base64,"
                    + base64.b64encode(VALID_MINIMAL_PNG).decode("ascii"),
                    "candidates": [],
                }
            ],
            "reference_pages": [],
            "findings": [],
            "related_references": [],
        },
    }
    cache_directory = (
        workspace
        / "case-page-images-hq-v1"
        / f"{case_id}--{attachment_id}--{source_hash}"
    )
    cache_directory.mkdir(parents=True)
    (cache_directory / "page-0001.png").write_bytes(VALID_MINIMAL_PNG)
    (run_directory / "review.html").write_text(
        render_review_html(model, workspace / "page-images"),
        encoding="utf-8",
    )

    server = create_review_server(
        workspace,
        run_tokens={run_id: token},
        reviewer_ids={run_id: "reviewer-01"},
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=5)
        connection.request(
            "GET",
            f"/runs/{run_id}/{token}/case-pages/{attachment_id}/1/{image_hash}",
            headers={"Host": f"{host}:{port}"},
        )
        response = connection.getresponse()
        body = response.read()
        connection.close()
        assert response.status == 200
        assert body == VALID_MINIMAL_PNG
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


HANDLERS = {
    "navigation_only": _navigation_only,
    "planner_formal_review": _planner_formal_review,
    "explicit_scope_formal_review": _explicit_scope_formal_review,
    "partial_multi_issue": _partial_multi_issue,
    "drawing_confirmation": _drawing_confirmation,
    "source_revision_invalidation": _source_revision_invalidation,
    "two_formal_runs": _two_formal_runs,
    "packet_specific_human_decision": _packet_specific_human_decision,
    "restart_recovery": _restart_recovery,
    "installed_wheel_runtime": _installed_wheel_runtime,
    "protected_case_visual_cache_identity": _protected_case_visual_cache_identity,
}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_exact_head_review_matter_end_to_end_matrix(scenario: str, tmp_path: Path) -> None:
    root = tmp_path / scenario
    root.mkdir()
    HANDLERS[scenario](root)


def test_acceptance_document_covers_all_matrix_scenarios_and_gates() -> None:
    document = Path(__file__).parents[3] / "docs" / "REVIEW_MATTER_ACCEPTANCE_2026-09-08.md"
    assert document.is_file()
    body = document.read_text(encoding="utf-8")
    for scenario in SCENARIOS:
        assert f"`{scenario}`" in body
    for required in (
        "py -3.13 -m pytest -v",
        "1366×768",
        "1920×1080",
        "3840×2160",
        "ACTIONS_NOT_RUN",
        "CASE_DRAWING",
        "packet",
    ):
        assert required in body
