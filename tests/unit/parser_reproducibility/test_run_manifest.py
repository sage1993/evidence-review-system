from __future__ import annotations

import hashlib
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.parser_reproducibility.run_manifest import (
    build_parser_run_manifest,
    parser_run_manifest_document,
)
from tests.unit.parser_reproducibility._helpers import config, write_pdf, write_run


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_builds_manifest_without_modifying_inputs(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run = write_run(
        tmp_path / "run",
        source,
        warning="page 1: inspect layout",
    )
    before = tree_hashes(tmp_path)

    manifest = build_parser_run_manifest(source, run, config())

    assert manifest.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest.source_page_count == 1
    assert manifest.parser_page_count == 1
    assert manifest.json_relative_path == "document.json"
    assert manifest.markdown_relative_path == "document.md"
    assert manifest.warning_count == 1
    assert manifest.warning_codes == ("PARSER_WARNING_UNKNOWN",)
    assert manifest.run_id.startswith("PRUN-")
    assert tree_hashes(tmp_path) == before


def test_manifest_serialization_is_deterministic(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run = write_run(tmp_path / "run", source)
    manifest = build_parser_run_manifest(source, run, config())

    first = dump_bytes(parser_run_manifest_document(manifest))
    second = dump_bytes(parser_run_manifest_document(manifest))

    assert first == second
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
