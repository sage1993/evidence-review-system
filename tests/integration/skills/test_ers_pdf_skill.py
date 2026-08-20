from pathlib import Path

ROOT = Path(__file__).parents[3]


def test_ers_pdf_skill_declares_a_safe_parse_to_evidence_workflow() -> None:
    skill = (ROOT / "skills" / "ers-pdf" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "name: ers-pdf" in skill
    assert "$ERS_PDF" in skill
    assert "opendataloader-pdf" in skill
    assert "evidence-review source-batch prepare" in skill
    assert "evidence-review source-batch ingest" in skill
    assert "PENDING_PARSER_OUTPUT" in skill
    assert "READY_TO_EVALUATE" in skill
    assert "원본" in skill and "덮어쓰" in skill
    assert "evidence-review workspace bind" in skill
    assert ".ers/active-workspace.json" in skill
    assert "준비가 완료되지 않은 workspace를 active workspace로 bind" in skill
