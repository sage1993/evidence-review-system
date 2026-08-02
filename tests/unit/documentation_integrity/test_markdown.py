"""Bounded Markdown structure extraction tests."""

from __future__ import annotations

from ansim_review.documentation_integrity.markdown import (
    assign_heading_anchors,
    normalize_heading_anchor,
    parse_markdown,
)


def test_anchor_normalization_is_stable() -> None:
    assert normalize_heading_anchor("검토 Run") == "검토-run"
    assert normalize_heading_anchor("  A/B: C  ") == "ab-c"
    assert normalize_heading_anchor("***") == "section"
    assert assign_heading_anchors(["Title", "Title", "TITLE"]) == (
        "title",
        "title-1",
        "title-2",
    )


def test_extracts_atx_setext_and_duplicate_heading_anchors() -> None:
    parsed = parse_markdown(
        "# First title\n\nSecond title\n------------\n\n# FIRST TITLE #\n"
    )
    assert [(heading.text, heading.anchor, heading.line, heading.column) for heading in parsed.headings] == [
        ("First title", "first-title", 1, 3),
        ("Second title", "second-title", 3, 1),
        ("FIRST TITLE", "first-title-1", 6, 3),
    ]


def test_extracts_inline_image_reference_and_fragment_links() -> None:
    parsed = parse_markdown(
        "[Guide](docs/guide.md#run) ![Diagram](images/a.png) [Same](#local)\n"
        "[Reference][ref] and [Collapsed][] and [Shortcut].\n\n"
        "[ref]: docs/reference.md\n"
        "[collapsed]: docs/collapsed.md\n"
        "[shortcut]: docs/shortcut.md\n"
    )
    assert [(link.label, link.target, link.is_image, link.line) for link in parsed.links] == [
        ("Guide", "docs/guide.md#run", False, 1),
        ("Diagram", "images/a.png", True, 1),
        ("Same", "#local", False, 1),
        ("Reference", "docs/reference.md", False, 2),
        ("Collapsed", "docs/collapsed.md", False, 2),
        ("Shortcut", "docs/shortcut.md", False, 2),
    ]


def test_ignores_inline_code_escaped_markdown_and_non_command_fences() -> None:
    parsed = parse_markdown(
        "`[fake](missing.md)` and \\[escaped](missing.md)\n\n"
        "```python\n"
        "[also fake](missing.md)\n"
        "```\n"
        "```powershell\n"
        "evidence-review rules select --help\n"
        "```\n"
    )
    assert parsed.links == ()
    assert len(parsed.command_blocks) == 1
    block = parsed.command_blocks[0]
    assert block.language == "powershell"
    assert block.text == "evidence-review rules select --help"
    assert block.start_line == 7


def test_extracts_raw_urls_and_first_non_empty_line() -> None:
    parsed = parse_markdown(
        "\n> Document status: HISTORICAL RECORD\n"
        "Valid https://example.com/path and invalid http://example.com.\n"
        "Protocol relative //example.com/path and ftp://example.com/file.\n"
    )
    assert parsed.first_non_empty_line == "> Document status: HISTORICAL RECORD"
    assert [url.target for url in parsed.raw_urls] == [
        "https://example.com/path",
        "http://example.com",
        "//example.com/path",
        "ftp://example.com/file",
    ]
    assert [url.line for url in parsed.raw_urls] == [3, 3, 4, 4]
