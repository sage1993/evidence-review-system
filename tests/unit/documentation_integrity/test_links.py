"""Link, anchor, path, and external URL validation tests."""

from __future__ import annotations

from pathlib import Path

from ansim_review.documentation_integrity.discovery import DiscoveredDocument
from ansim_review.documentation_integrity.links import DocumentationIndex, validate_links
from ansim_review.documentation_integrity.markdown import parse_markdown


def _write(path: Path, text: str = "# Document\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _document(root: Path, path: str, classification: str) -> DiscoveredDocument:
    file_path = root / path
    _write(file_path)
    return DiscoveredDocument(
        path=path,
        filesystem_path=file_path.absolute(),
        classification=classification,  # type: ignore[arg-type]
    )


def _codes(findings: tuple[object, ...]) -> list[str]:
    return [finding.code for finding in findings]  # type: ignore[attr-defined]


def test_current_document_accepts_files_directories_fragments_and_virtual_paths(
    tmp_path: Path,
) -> None:
    document = _document(tmp_path, "docs/current.md", "CURRENT")
    _write(tmp_path / "docs" / "guide.md", "# Section\n")
    _write(tmp_path / "images" / "diagram.png", "image")
    (tmp_path / "docs" / "assets").mkdir()
    parsed = parse_markdown(
        "[Guide](guide.md?mode=full#section)\n"
        "![Diagram](../images/diagram.png)\n"
        "[Assets](assets/)\n"
        "[Generated](../generated/VALIDATE.md#run)\n"
        "[Same](#local)\n"
        "# Local\n"
    )
    index = DocumentationIndex(
        classifications={
            "docs/current.md": "CURRENT",
            "docs/guide.md": "CURRENT",
            "generated/VALIDATE.md": "CURRENT",
        },
        headings_by_path={
            "docs/current.md": frozenset({"local"}),
            "docs/guide.md": frozenset({"section"}),
            "generated/VALIDATE.md": frozenset({"run"}),
        },
        virtual_paths=frozenset({"generated/VALIDATE.md"}),
        repository_root=tmp_path,
    )

    assert validate_links(document, parsed, index) == ()


def test_current_document_reports_missing_target_and_anchor(tmp_path: Path) -> None:
    document = _document(tmp_path, "docs/current.md", "CURRENT")
    _write(tmp_path / "docs" / "guide.md", "# Present\n")
    parsed = parse_markdown(
        "[Missing](missing.md)\n"
        "[Missing anchor](guide.md#absent)\n"
        "[Same missing](#absent)\n"
    )
    index = DocumentationIndex(
        classifications={
            "docs/current.md": "CURRENT",
            "docs/guide.md": "CURRENT",
        },
        headings_by_path={
            "docs/current.md": frozenset(),
            "docs/guide.md": frozenset({"present"}),
        },
        virtual_paths=frozenset(),
        repository_root=tmp_path,
    )

    assert _codes(validate_links(document, parsed, index)) == [
        "INTERNAL_LINK_TARGET_MISSING",
        "INTERNAL_LINK_ANCHOR_MISSING",
        "INTERNAL_LINK_ANCHOR_MISSING",
    ]


def test_repository_path_safety_is_fail_closed_for_both_classes(
    tmp_path: Path,
) -> None:
    index = DocumentationIndex(
        classifications={},
        headings_by_path={},
        virtual_paths=frozenset(),
        repository_root=tmp_path,
    )
    markdown = (
        "[Escape](../../outside.md)\n"
        "[POSIX absolute](/repo/file.md)\n"
        "[Windows absolute](C:/repo/file.md)\n"
        "[Backslash](docs\\file.md)\n"
    )
    expected = [
        "REPOSITORY_PATH_ESCAPE",
        "ABSOLUTE_REPOSITORY_PATH",
        "ABSOLUTE_REPOSITORY_PATH",
        "BACKSLASH_REPOSITORY_REFERENCE",
    ]
    for classification in ("CURRENT", "HISTORICAL"):
        document = _document(tmp_path, f"docs/{classification}.md", classification)
        parsed = parse_markdown(markdown)
        assert _codes(validate_links(document, parsed, index))[:4] == expected


def test_historical_document_allows_safe_missing_targets_but_requires_marker(
    tmp_path: Path,
) -> None:
    document = _document(tmp_path, "docs/acceptance/old.md", "HISTORICAL")
    parsed = parse_markdown("# Old record\n[Old target](removed/file.md#old)\n")
    index = DocumentationIndex(
        classifications={"docs/acceptance/old.md": "HISTORICAL"},
        headings_by_path={},
        virtual_paths=frozenset(),
        repository_root=tmp_path,
    )

    findings = validate_links(document, parsed, index)
    assert _codes(findings) == ["HISTORICAL_MARKER_MISSING"]
    assert findings[0].severity == "WARNING"


def test_historical_marker_suppresses_warning(tmp_path: Path) -> None:
    document = _document(tmp_path, "docs/acceptance/old.md", "HISTORICAL")
    parsed = parse_markdown(
        "> Document status: HISTORICAL RECORD\n\n[Old](removed.md)\n"
    )
    index = DocumentationIndex(
        classifications={"docs/acceptance/old.md": "HISTORICAL"},
        headings_by_path={},
        virtual_paths=frozenset(),
        repository_root=tmp_path,
    )
    assert validate_links(document, parsed, index) == ()


def test_current_to_historical_reference_requires_explicit_label(tmp_path: Path) -> None:
    document = _document(tmp_path, "docs/current.md", "CURRENT")
    _write(tmp_path / "docs" / "acceptance" / "old.md")
    parsed = parse_markdown(
        "[Old](acceptance/old.md)\n"
        "[Historical: Old](acceptance/old.md)\n"
        "[과거 기록: 예전 결과](acceptance/old.md)\n"
    )
    index = DocumentationIndex(
        classifications={
            "docs/current.md": "CURRENT",
            "docs/acceptance/old.md": "HISTORICAL",
        },
        headings_by_path={},
        virtual_paths=frozenset(),
        repository_root=tmp_path,
    )

    assert _codes(validate_links(document, parsed, index)) == [
        "CURRENT_TO_HISTORICAL_REFERENCE_UNMARKED"
    ]


def test_external_url_scheme_warnings_apply_to_links_and_raw_urls(
    tmp_path: Path,
) -> None:
    document = _document(tmp_path, "README.md", "CURRENT")
    parsed = parse_markdown(
        "[Valid](https://example.com/path)\n"
        "[HTTP](http://example.com/path)\n"
        "Raw ftp://example.com/file and //example.com/path.\n"
        "Broken https:///missing-host.\n"
    )
    index = DocumentationIndex(
        classifications={"README.md": "CURRENT"},
        headings_by_path={},
        virtual_paths=frozenset(),
        repository_root=tmp_path,
    )

    findings = validate_links(document, parsed, index)
    assert _codes(findings) == [
        "EXTERNAL_URL_SCHEME_INVALID",
        "EXTERNAL_URL_SCHEME_INVALID",
        "EXTERNAL_URL_SCHEME_INVALID",
        "EXTERNAL_URL_SCHEME_INVALID",
    ]
    assert all(finding.severity == "WARNING" for finding in findings)
