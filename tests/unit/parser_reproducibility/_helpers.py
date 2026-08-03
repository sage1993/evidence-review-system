from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pypdf import PdfWriter

from ansim_review.parser_reproducibility.contract import ReproducibilityConfig


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


def write_pdf(path: Path, pages: int = 1) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    with path.open("wb") as stream:
        writer.write(stream)
    return path


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
    payload: dict[str, object] = {
        "file name": source.name,
        "number of pages": 1,
        "metadata": {
            "parsed_at": parsed_at,
            "output_directory": str(root),
        },
        "pages": [
            {
                "page number": 1,
                "width": 595,
                "height": 842,
                "kids": [
                    {
                        "type": "paragraph",
                        "page number": 1,
                        "bounding box": [10, 20, 30, 40],
                        "content": content,
                    }
                ],
            }
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
        "source_page_count": 1,
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
