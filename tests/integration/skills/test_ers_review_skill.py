from pathlib import Path

ROOT = Path(__file__).parents[3]


def test_ers_review_skill_declares_formal_answer_and_html_workflow() -> None:
    skill = (ROOT / "skills" / "ers-review" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "name: ers-review" in skill
    assert "$ERS_REVIEW" in skill
    assert "빠른 조회 모드는 없다" in skill
    assert "evidence-review review-question prepare" in skill
    assert "evidence-review review-question submit-track-a" in skill
    assert "evidence-review review-question submit-track-b" in skill
    assert "evidence-review review-run serve" in skill
    assert "evidence-review review-run import-decision" in skill
    assert "review.html" in skill
    assert "human_decision" in skill
    assert "READY_FOR_HUMAN_REVIEW" in skill
    assert "ABSTAIN" in skill
    assert "REVIEW_COMPLETED" in skill
