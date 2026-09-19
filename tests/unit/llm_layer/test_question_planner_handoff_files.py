from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.question_planning import prepare_question_planner_handoff


def test_prepare_question_planner_handoff_is_deterministic_and_evidence_free(
    tmp_path: Path,
) -> None:
    raw_question = "  에어컨 등  가전제품 설치기준 알려줘 "
    first = prepare_question_planner_handoff(tmp_path, raw_question)
    second = prepare_question_planner_handoff(tmp_path, raw_question)

    assert first == second
    assert first.planning_directory.name.startswith("PLAN-")
    assert first.bundle_path.name == "question-planner-bundle.json"
    assert first.instructions_path.name == "QUESTION_PLANNER_INSTRUCTIONS.md"
    assert first.expected_output_path.name == "question-plan-output.json"
    assert not first.expected_output_path.exists()
    bundle = json.loads(first.bundle_path.read_text(encoding="utf-8"))
    assert bundle["original_question"] == "에어컨 등 가전제품 설치기준 알려줘"
    assert bundle["raw_user_question"] == raw_question
    assert "evidence" not in bundle
    assert "answer" not in bundle


def test_prepare_question_planner_handoff_rejects_conflicting_existing_artifact(
    tmp_path: Path,
) -> None:
    result = prepare_question_planner_handoff(tmp_path, "질문")
    result.bundle_path.write_text("tampered", encoding="utf-8")

    with pytest.raises(FileExistsError, match="differs"):
        prepare_question_planner_handoff(tmp_path, "질문")
