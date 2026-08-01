from __future__ import annotations

import json
from pathlib import Path

import pytest

from ansim_review.parsing.source_manifest import sha256_file
from ansim_review.parsing.visual_manifest import load_visual_manifest


def _record(path: str, sha256: str, *, visual_id: str, page_id: str) -> dict[str, object]:
    return {
        "id": visual_id,
        "document_id": "DOC-1",
        "revision_id": "DOC-1-r1",
        "page_id": page_id,
        "kind": "occurrence_crop",
        "path": path,
        "sha256": sha256,
        "bbox": [10, 20, 30, 40],
        "source_evidence_ids": ["E1"],
    }


def test_duplicate_bytes_remain_distinct_explicit_occurrences(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    (root / "visuals").mkdir(parents=True)
    first = root / "visuals/p1.png"
    second = root / "visuals/p2.png"
    first.write_bytes(b"same-image")
    second.write_bytes(b"same-image")
    digest = sha256_file(first)
    manifest = root / "visuals/manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "format": "evidence-review/visual-manifest",
                "version": 1,
                "records": [
                    _record("visuals/p1.png", digest, visual_id="VIS-1", page_id="PAGE-1"),
                    _record("visuals/p2.png", digest, visual_id="VIS-2", page_id="PAGE-2"),
                ],
            }
        ),
        encoding="utf-8",
    )

    result = load_visual_manifest(root, manifest)

    assert result.issues == ()
    assert tuple(record.visual_id for record in result.records) == ("VIS-1", "VIS-2")
    assert result.records[0].duplicate_group == result.records[1].duplicate_group
    assert result.records[0].page_id == "PAGE-1"


@pytest.mark.parametrize("missing", ["document_id", "revision_id", "page_id"])
def test_visual_manifest_requires_explicit_identity(
    tmp_path: Path, missing: str
) -> None:
    root = tmp_path / "workspace"
    (root / "visuals").mkdir(parents=True)
    image = root / "visuals/law-1-page-3.png"
    image.write_bytes(b"image")
    entry = _record(
        "visuals/law-1-page-3.png",
        sha256_file(image),
        visual_id="VIS-1",
        page_id="PAGE-3",
    )
    del entry[missing]
    manifest = root / "visuals/law-1-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "format": "evidence-review/visual-manifest",
                "version": 1,
                "records": [entry],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=missing):
        load_visual_manifest(root, manifest)


def test_visual_filename_never_supplies_document_or_page_identity(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    (root / "visuals").mkdir(parents=True)
    image = root / "visuals/law-1-page-3.png"
    image.write_bytes(b"image")
    manifest = root / "visuals/law-1.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "id": "VIS-1",
                    "kind": "page_render",
                    "path": "visuals/law-1-page-3.png",
                    "sha256": sha256_file(image),
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="visual manifest format"):
        load_visual_manifest(root, manifest)
