from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import evidence_review.workflow.engine_orchestration as orchestration
from evidence_review.workflow.engine_orchestration import run_deterministic_stages
from evidence_review.workflow.orchestrator import prepare_review_run
from evidence_review.workflow.request import decode_review_request
from evidence_review.workflow.resume import machine_artifacts_byte_equal


def _layout(root: Path, run_id: str = "RUN-001"):
    request = decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "재현 가능한가?",
            "attachments": [],
        }
    )
    return prepare_review_run(
        root / "runs",
        run_id,
        request,
        recorded_at="2026-08-04T00:00:00+09:00",
    )


def test_resume_skips_completed_retrieval_stage(tmp_path: Path, monkeypatch) -> None:
    layout = _layout(tmp_path / "first")
    original = orchestration._write_stage

    def stop_after_retrieval(*args, **kwargs):
        if args[1] == "RUNNING_MATH":
            raise RuntimeError("simulated process termination")
        return original(*args, **kwargs)

    monkeypatch.setattr(orchestration, "_write_stage", stop_after_retrieval)
    with pytest.raises(RuntimeError, match="simulated process termination"):
        run_deterministic_stages(
            layout,
            retrieval={"evidence_ids": ["EVIDENCE-001"]},
            math={"calculation_result_ids": ["CALC-001"]},
            rules={"rule_result_ids": ["RULE-001"]},
        )
    monkeypatch.setattr(orchestration, "_write_stage", original)

    results = run_deterministic_stages(
        layout,
        retrieval={"evidence_ids": ["EVIDENCE-001"]},
        math={"calculation_result_ids": ["CALC-001"]},
        rules={"rule_result_ids": ["RULE-001"]},
    )

    assert len(results) == 3
    assert layout.load_state().workflow_state == "WAITING_TRACK_A"


def test_same_machine_artifacts_are_byte_identical(tmp_path: Path) -> None:
    left = _layout(tmp_path / "left")
    right = _layout(tmp_path / "right")
    for layout in (left, right):
        run_deterministic_stages(
            layout,
            retrieval={"evidence_ids": ["EVIDENCE-001"]},
            math={"calculation_result_ids": ["CALC-001"]},
            rules={"rule_result_ids": ["RULE-001"]},
        )

    assert machine_artifacts_byte_equal(left.machine_dir, right.machine_dir)


def test_machine_artifact_comparison_rejects_linked_root(tmp_path: Path) -> None:
    left = _layout(tmp_path / "left")
    right = _layout(tmp_path / "right")
    for layout in (left, right):
        run_deterministic_stages(
            layout,
            retrieval={"evidence_ids": ["EVIDENCE-001"]},
            math={"calculation_result_ids": ["CALC-001"]},
            rules={"rule_result_ids": ["RULE-001"]},
        )

    external = tmp_path / "external-machine"
    shutil.copytree(left.machine_dir, external)
    shutil.rmtree(left.machine_dir)
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(left.machine_dir), str(external)],
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
    else:
        try:
            left.machine_dir.symlink_to(external, target_is_directory=True)
        except OSError as error:
            pytest.skip(f"directory symlink creation unavailable: {error}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        machine_artifacts_byte_equal(left.machine_dir, right.machine_dir)
