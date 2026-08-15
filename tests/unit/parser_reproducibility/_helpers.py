from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from evidence_review.parser_reproducibility.contract import ReproducibilityConfig


def config() -> ReproducibilityConfig:
    return ReproducibilityConfig(
        parser_kind="opendataloader",
        adapter_version=1,
        json_artifact_names=("document.json",),
        markdown_artifact_names=("document.md",),
        warning_sources=("document.json", "parser.log"),
        normalization_profile="opendataloader-v1",
        allowed_nondeterministic_fields=(
            "$.metadata.parsed_at",
            "$.metadata.output_directory",
        ),
    )


def write_config(path: Path) -> Path:
    payload = {
        "format": "evidence-review/parser-reproducibility-config",
        "version": 1,
        "parser_kind": "opendataloader",
        "adapter_version": 1,
        "json_artifact_names": ["document.json"],
        "markdown_artifact_names": ["document.md"],
        "warning_sources": ["document.json", "parser.log"],
        "normalization_profile": "opendataloader-v1",
        "allowed_nondeterministic_fields": [
            "$.metadata.parsed_at",
            "$.metadata.output_directory",
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_pdf(path: Path, pages: int = 1) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    with path.open("wb") as stream:
        writer.write(stream)
    return path


def _page_payload(page_number: int, content: str) -> dict[str, object]:
    return {
        "page number": page_number,
        "width": 595,
        "height": 842,
        "kids": [
            {
                "type": "paragraph",
                "page number": page_number,
                "bounding box": [10, 20, 30, 40],
                "content": f"{content} {page_number}",
            }
        ],
    }


def write_run(
    root: Path,
    source: Path,
    *,
    parser_version: str = "1.2.3",
    parsed_at: str = "2026-08-03T00:00:00Z",
    content: str = "Alpha",
    markdown: str = "# Alpha\n",
    warning: str | None = None,
) -> Path:
    root.mkdir(parents=True)
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    document_id = "DOC-" + source_sha256[:20].upper()
    revision_id = f"{document_id}-{source_sha256[:12]}"
    with source.open("rb") as stream:
        page_count = len(PdfReader(stream, strict=True).pages)
    payload: dict[str, object] = {
        "file name": source.name,
        "number of pages": page_count,
        "metadata": {
            "parsed_at": parsed_at,
            "output_directory": str(root),
        },
        "pages": [
            _page_payload(page_number, content)
            for page_number in range(1, page_count + 1)
        ],
    }
    if warning is not None:
        payload["warnings"] = [warning]
    (root / "document.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (root / "document.md").write_text(markdown, encoding="utf-8", newline="")
    metadata = {
        "format": "evidence-review/opendataloader-parser-run",
        "version": 1,
        "source_relative_path": f"inputs/original/{source.name}",
        "source_sha256": source_sha256,
        "source_size": source.stat().st_size,
        "source_page_count": page_count,
        "document_id": document_id,
        "revision_id": revision_id,
        "parser_kind": "opendataloader",
        "parser_version": parser_version,
        "adapter_version": 1,
        "parser_configuration": {"markdown_with_html": True},
        "platform_family": "windows",
    }
    (root / "parser-run.json").write_text(
        json.dumps(metadata, separators=(",", ":")),
        encoding="utf-8",
    )
    return root


def write_source_manifest(
    path: Path,
    run_root: Path,
    *,
    parser_kind: str = "OPENDATALOADER_JSON",
    document_id: str | None = None,
) -> Path:
    metadata = json.loads((run_root / "parser-run.json").read_text(encoding="utf-8"))
    payload = {
        "format": "evidence-review/source-batch",
        "version": 2,
        "sources": [
            {
                "source_path": metadata["source_relative_path"],
                "role": "REFERENCE_DOCUMENT",
                "document_id": document_id,
                "display_title": "Reference",
                "parser": {
                    "kind": parser_kind,
                    "artifact_path": "inputs/parser/document.json",
                    "options": {},
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
