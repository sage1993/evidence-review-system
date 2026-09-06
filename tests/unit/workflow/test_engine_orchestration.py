from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from evidence_review.workflow.engine_orchestration import (
    advance_to_track_b,
    finalize_orchestration_run,
    require_track_b_acceptance,
    run_deterministic_stages,
)
from evidence_review.workflow.events import load_workflow_events
from evidence_review.workflow.orchestrator import prepare_review_run
from evidence_review.workflow.request import decode_review_request


def _ready_layout(tmp_path: Path):
    request = decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "결과를 검토할 수 있는가?",
            "attachments": [],
        }
    )
    return prepare_review_run(
        tmp_path / "runs",
        "RUN-001",
        request,
        recorded_at="2026-08-04T00:00:00+09:00",
    )


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


def test_deterministic_stages_are_executed_and_persisted_in_order(tmp_path: Path) -> None:
    layout = _ready_layout(tmp_path)

    results = run_deterministic_stages(
        layout,
        retrieval={"evidence_ids": ["EVIDENCE-001"]},
        math={"calculation_result_ids": ["CALC-001"]},
        rules={"rule_result_ids": ["RULE-001"]},
    )

    assert tuple(result.stage for result in results) == (
        "RETRIEVING_EVIDENCE",
        "RUNNING_MATH",
        "RUNNING_RULES",
    )
    assert layout.load_state().workflow_state == "WAITING_TRACK_A"
    assert tuple(event.next_state for event in load_workflow_events(layout.events_dir))[-4:] == (
        "RETRIEVING_EVIDENCE",
        "RUNNING_MATH",
        "RUNNING_RULES",
        "WAITING_TRACK_A",
    )
    assert (layout.machine_dir / "retrieval.json").is_file()
    assert (layout.machine_dir / "math.json").is_file()
    assert (layout.machine_dir / "rules.json").is_file()
    assert (layout.machine_dir / "next-action.json").is_file()


def test_deterministic_stages_reject_linked_machine_directory(
    tmp_path: Path,
) -> None:
    layout = _ready_layout(tmp_path)
    external_machine = tmp_path / "external-machine"
    external_machine.mkdir()
    _directory_link(layout.machine_dir, external_machine)

    with pytest.raises(ValueError, match="symlink|reparse"):
        run_deterministic_stages(
            layout,
            retrieval={"evidence_ids": ["EVIDENCE-001"]},
            math={"calculation_result_ids": ["CALC-001"]},
            rules={"rule_result_ids": ["RULE-001"]},
        )

    assert not (external_machine / "retrieval.json").exists()


def test_track_b_rejection_blocks_finalization(tmp_path: Path) -> None:
    layout = _ready_layout(tmp_path)
    run_deterministic_stages(
        layout,
        retrieval={"evidence_ids": []},
        math={"calculation_result_ids": []},
        rules={"rule_result_ids": []},
    )
    advance_to_track_b(
        layout,
        track_a_sha256="a" * 64,
        recorded_at="2026-08-04T00:01:00+09:00",
    )

    with pytest.raises(ValueError, match="TRACK_B_REJECTED"):
        require_track_b_acceptance(
            layout,
            {"overall_disposition": "REJECT"},
            recorded_at="2026-08-04T00:02:00+09:00",
        )

    assert layout.load_state().workflow_state == "BLOCKED"
    assert not (layout.run_dir / "final-review-packet.json").exists()


def test_track_b_acceptance_calls_existing_finalizer(tmp_path: Path, monkeypatch) -> None:
    layout = _ready_layout(tmp_path)
    run_deterministic_stages(
        layout,
        retrieval={"evidence_ids": []},
        math={"calculation_result_ids": []},
        rules={"rule_result_ids": []},
    )
    advance_to_track_b(
        layout,
        track_a_sha256="a" * 64,
        recorded_at="2026-08-04T00:01:00+09:00",
    )
    require_track_b_acceptance(
        layout,
        {"overall_disposition": "ACCEPT"},
        recorded_at="2026-08-04T00:02:00+09:00",
    )

    called = False

    def fake_finalize(run_directory: Path) -> SimpleNamespace:
        nonlocal called
        called = True
        (run_directory / "final-review-packet.json").write_bytes(
            b'{"status":"READY_FOR_HUMAN_REVIEW"}'
        )
        return SimpleNamespace(status="READY_FOR_HUMAN_REVIEW")

    monkeypatch.setattr(
        "evidence_review.abstention.finalizer.finalize_run",
        fake_finalize,
    )
    packet_path = finalize_orchestration_run(
        layout,
        recorded_at="2026-08-04T00:03:00+09:00",
    )

    assert called is True
    assert packet_path.name == "final-review-packet.json"
    assert layout.load_state().workflow_state == "READY_FOR_REVIEW"
