from pathlib import Path

ROOT = Path(__file__).parents[3]


def test_ers_review_skill_declares_answer_and_html_workflow() -> None:
    skill = (ROOT / "skills" / "ers-review" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "name: ers-review" in skill
    assert "$ERS_REVIEW" in skill
    assert "evidence-review query" in skill
    assert "evidence-review math-run" in skill
    assert "review-run prepare" in skill
    assert "review-run finalize" in skill
    assert "--open" in skill
    assert "review.html" in skill
    assert "human_decision" in skill
    assert "READY_FOR_HUMAN_REVIEW" in skill
    assert "ABSTAIN" in skill
