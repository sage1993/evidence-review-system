from pathlib import Path


def test_review_matter_architecture_declares_distinct_identity() -> None:
    text = Path("docs/REVIEW_MATTER_ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "ReviewMatter" in text
    assert "matter_id" in text
    assert "CaseManifest" in text
    assert "ReviewCase" not in text
    assert "evidence.sqlite" in text
    assert "Human Decision" in text
