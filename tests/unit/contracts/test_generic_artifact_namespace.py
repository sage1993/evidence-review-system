from __future__ import annotations

from pathlib import Path

SOURCE_ROOT = Path("src/evidence_review")
LEGACY_FILE = SOURCE_ROOT / "contracts" / "legacy_formats.py"
LEGACY_READERS = {
    SOURCE_ROOT / "parsing" / "legacy_visual_manifest.py",
    SOURCE_ROOT / "parsing" / "page_image_cache.py",
    SOURCE_ROOT / "release" / "legacy_acceptance.py",
    SOURCE_ROOT / "review_run.py",
    SOURCE_ROOT / "review_packet" / "html_renderer.py",
}
LEGACY_CONSTANTS_BY_READER = {
    SOURCE_ROOT / "parsing" / "legacy_visual_manifest.py": "LEGACY_VISUAL_STATUS",
    SOURCE_ROOT / "parsing" / "page_image_cache.py": "LEGACY_PAGE_IMAGE_FORMAT",
    SOURCE_ROOT / "release" / "legacy_acceptance.py": "LEGACY_HUMAN_ACCEPTANCE_FORMAT",
    SOURCE_ROOT / "review_packet" / "html_renderer.py": "LEGACY_PAGE_IMAGE_FORMAT",
}
TOKENS = (
    '"ansim/',
    "'ansim/",
    '"ansim-v1.0"',
    "'ansim-v1.0'",
    '"ansim-evidence.sqlite"',
    "'ansim-evidence.sqlite'",
)


def test_sample_specific_artifact_identifiers_are_isolated() -> None:
    findings: list[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        if path == LEGACY_FILE or path in LEGACY_READERS:
            continue
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(token in line for token in TOKENS):
                findings.append(f"{path.as_posix()}:{line_number}:{line.strip()}")

    assert findings == []


def test_legacy_boundaries_are_explicitly_read_only() -> None:
    text = LEGACY_FILE.read_text(encoding="utf-8")

    assert "New writers must not emit these values" in text
    for required in (
        "LEGACY_NEXT_ACTION_FORMAT",
        "LEGACY_REVIEW_PACKET_FORMAT",
        "LEGACY_WORKFLOW_STATE_FORMAT",
        "LEGACY_CASE_MANIFEST_FORMAT",
        "LEGACY_HUMAN_ACCEPTANCE_FORMAT",
        "LEGACY_PAGE_IMAGE_FORMAT",
        "LEGACY_REVIEW_RUN_REQUEST_FORMAT",
        "LEGACY_EVIDENCE_DB_NAME",
        "LEGACY_RELEASE_ID",
        "LEGACY_VISUAL_MANIFEST_CSV",
        "LEGACY_VISUAL_STATUS",
    ):
        assert required in text
    for reader in sorted(LEGACY_READERS):
        reader_text = reader.read_text(encoding="utf-8")
        expected_constant = LEGACY_CONSTANTS_BY_READER.get(reader)
        assert any(token in reader_text for token in TOKENS) or (
            expected_constant is not None and expected_constant in reader_text
        )
