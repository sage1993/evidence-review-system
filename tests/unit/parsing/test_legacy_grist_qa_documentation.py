from pathlib import Path

PROCEDURE = Path("docs/GRIST_DESKTOP_QA.md")
EXAMPLE = Path("docs/examples/grist-desktop-qa.example.json")
LEGACY_POLICY = Path("docs/LEGACY_VISUALS.md")


def test_grist_desktop_qa_procedure_is_complete_and_fail_closed() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROCEDURE, EXAMPLE, LEGACY_POLICY)
    )

    for token in (
        "LEGACY_UI_QA",
        "LEGACY_NON_CANONICAL",
        "ATTACHMENTS_FILE_LINK",
        "VISUALS_THUMBNAIL",
        "REFERENCE_LINK_PREVIEW",
        "PAGE_RENDER",
        "IMAGE_CONTEXT_CROP",
        "TABLE_CROP",
        "COMPOSITE_DIAGRAM",
        "MISSING_BROKEN_LINK_SCAN",
        "LEGACY_CANONICAL_SEPARATION",
        "PASS",
        "FAIL",
        "INCOMPLETE",
        "evidence-review legacy validate-grist-qa",
    ):
        assert token in combined


def test_docs_deny_ci_screen_review_and_premature_issue_closure() -> None:
    text = PROCEDURE.read_text(encoding="utf-8")

    assert "CI는 실제 Grist Desktop 화면 검토를 수행할 수 없다" in text
    assert "Issue #38을 닫지 않는다" in text
    assert "validator 결과가 PASS" in text
    assert "canonical identity" in text


def test_example_is_explicitly_incomplete_not_acceptance_evidence() -> None:
    text = EXAMPLE.read_text(encoding="utf-8")

    assert text.count('"status": "NOT_RUN"') == 9
    assert '"samples": []' in text
    assert "실제 acceptance evidence가 아니다" in PROCEDURE.read_text(
        encoding="utf-8"
    )
