"""Historical command examples preserve recorded behavior without current parsing."""

from pathlib import Path

from evidence_review.documentation_integrity.commands import (
    normalize_command_block,
    validate_command_lines,
)
from evidence_review.documentation_integrity.discovery import DiscoveredDocument
from evidence_review.documentation_integrity.markdown import CommandBlock


def test_obsolete_historical_cli_command_is_not_reinterpreted(tmp_path: Path) -> None:
    document_path = tmp_path / "docs" / "acceptance" / "old.md"
    document_path.parent.mkdir(parents=True)
    document_path.write_text("# Old\n", encoding="utf-8")
    document = DiscoveredDocument(
        path="docs/acceptance/old.md",
        filesystem_path=document_path,
        classification="HISTORICAL",
    )
    lines = normalize_command_block(
        CommandBlock(
            language="powershell",
            text="evidence-review removed-command --legacy-option value",
            start_line=10,
        )
    )

    assert validate_command_lines(lines, tmp_path, document) == ()
