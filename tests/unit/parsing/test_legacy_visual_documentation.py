from pathlib import Path

README = Path("README.md")
POLICY = Path("docs/LEGACY_VISUALS.md")


def test_legacy_visual_policy_is_explicit_and_fail_closed() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in (README, POLICY)
    )

    for required in (
        "LEGACY_NON_CANONICAL",
        "conversion_supported",
        "false",
        "revision_id",
        "page_id",
        "파일명",
        "추론하지",
        "legacy reader 제거",
        "evidence-review legacy inspect-visual-manifest",
        "Issue #38",
    ):
        assert required in combined


def test_policy_denies_automatic_canonical_conversion() -> None:
    text = POLICY.read_text(encoding="utf-8")

    assert "canonical visual manifest로 자동 변환하지 않는다" in text
    assert "EXPLICIT_DOCUMENT_ALIAS" in text
    assert "EXPLICIT_REVISION_ID" in text
    assert "DB_RESOLVED_PAGE_ID" in text
    assert "EXPLICIT_VISUAL_KIND_MAP" in text
    assert "ASSET_SHA256_MATCH" in text
