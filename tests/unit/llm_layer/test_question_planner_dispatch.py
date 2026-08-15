from __future__ import annotations

import json
from pathlib import Path

from evidence_review.command_dispatch import main as command_main


def test_canonical_dispatch_prepare_plan_returns_planner_handoff(
    capsys,
    tmp_path: Path,
) -> None:
    exit_code = command_main(
        [
            "review-question",
            "prepare-plan",
            "--workspace",
            str(tmp_path),
            "--question",
            "에어컨 등 가전제품 설치기준 알려줘",
        ]
    )

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "WAITING_QUESTION_PLAN"
    assert Path(document["input_bundle"]).is_file()


def test_canonical_dispatch_rejects_prepare_without_validated_plan(
    capsys,
    tmp_path: Path,
) -> None:
    exit_code = command_main(
        [
            "review-question",
            "prepare",
            "--workspace",
            str(tmp_path),
            "--question",
            "에어컨 등 가전제품 설치기준 알려줘",
        ]
    )

    assert exit_code == 2
    document = json.loads(capsys.readouterr().out)
    assert document == {
        "format": "evidence-review/review-question-status",
        "version": 1,
        "stage": "prepare",
        "status": "PLANNER_FAILED",
        "reason_code": "QUESTION_PLAN_OUTPUT_REQUIRED",
    }
    assert not (tmp_path / "runs").exists()
