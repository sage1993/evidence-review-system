from __future__ import annotations

import json
from pathlib import Path

from evidence_review.question_planner_cli import dispatch_question_planning


def test_prepare_plan_cli_writes_handoff_without_question_in_status(
    capsys,
    tmp_path: Path,
) -> None:
    exit_code = dispatch_question_planning(
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
    assert document["stage"] == "prepare-plan"
    assert document["status"] == "WAITING_QUESTION_PLAN"
    assert "에어컨" not in json.dumps(document, ensure_ascii=False)
    assert Path(document["input_bundle"]).is_file()
    assert Path(document["instructions"]).is_file()
    assert document["expected_output"].endswith("question-plan-output.json")


def test_prepare_cli_rejects_invalid_plan_before_creating_run(
    capsys,
    tmp_path: Path,
) -> None:
    output = tmp_path / "plan.json"
    output.write_text(
        json.dumps(
            {
                "format": "evidence-review/question-plan",
                "version": 1,
                "original_question": "질문",
                "facts": [],
                "assumptions": [],
                "issues": [],
                "legal_anchors": [],
                "search_requests": [],
                "answer": "forbidden",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = dispatch_question_planning(
        [
            "review-question",
            "prepare",
            "--workspace",
            str(tmp_path),
            "--question",
            "질문",
            "--question-plan-output",
            str(output),
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["status"] == "PLANNER_FAILED"
    assert document["reason_code"] == "QUESTION_PLAN_INVALID"
    assert not (tmp_path / "runs").exists()


def test_prepare_cli_reports_retrieval_no_evidence_after_valid_plan(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    import evidence_review.question_planner_cli as planner_cli
    from evidence_review.review_question import PreparedReviewQuestion

    output = tmp_path / "plan.json"
    output.write_text(
        json.dumps(
            {
                "format": "evidence-review/question-plan",
                "version": 1,
                "original_question": "질문",
                "facts": [],
                "assumptions": [],
                "issues": [{"id": "I1", "question": "무엇인가", "depends_on": []}],
                "legal_anchors": [],
                "search_requests": [
                    {
                        "id": "S1",
                        "issue_ids": ["I1"],
                        "text": "검색어",
                        "kind": "phrase",
                        "source": "planner",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    guidance = tmp_path / "runs" / "RUN-1" / "retrieval-guidance.json"
    monkeypatch.setattr(
        planner_cli,
        "prepare_planned_review_question",
        lambda *args, **kwargs: PreparedReviewQuestion(
            run_id="RUN-1",
            status="WAITING_TRACK_A",
            next_action_path=tmp_path / "next.json",
            resumed=False,
            retrieval_guidance_path=guidance,
        ),
    )

    exit_code = dispatch_question_planning(
        [
            "review-question",
            "prepare",
            "--workspace",
            str(tmp_path),
            "--question",
            "질문",
            "--question-plan-output",
            str(output),
        ]
    )

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "RETRIEVAL_NO_EVIDENCE"
    assert document["retrieval_guidance_path"] == str(guidance)
