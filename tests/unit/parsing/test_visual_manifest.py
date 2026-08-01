import json
from pathlib import Path

from ansim_review.parsing.visual_manifest import load_visual_manifest


def test_duplicate_bytes_remain_distinct_occurrences(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    (root / "04_visuals/image_context_crops").mkdir(parents=True)
    first = root / "04_visuals/image_context_crops/p1.png"
    second = root / "04_visuals/image_context_crops/p2.png"
    first.write_bytes(b"same-image")
    second.write_bytes(b"same-image")
    manifest = root / "04_visuals/manifests/visuals.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            [
                {
                    "kind": "occurrence_crop",
                    "path": "04_visuals/image_context_crops/p1.png",
                    "page_number": 1,
                    "bbox": [10, 20, 30, 40],
                    "source_evidence_ids": ["E1"],
                },
                {
                    "kind": "occurrence_crop",
                    "path": "04_visuals/image_context_crops/p2.png",
                    "page_number": 2,
                    "bbox": [11, 21, 31, 41],
                    "source_evidence_ids": ["E2"],
                },
            ]
        ),
        encoding="utf-8",
    )

    result = load_visual_manifest(
        root,
        manifest,
        document_id="LAW1",
        revision_id="LAW1-r1",
    )

    assert result.issues == ()
    assert len(result.records) == 2
    assert result.records[0].visual_id == "OCC-LAW1-001"
    assert result.records[1].visual_id == "OCC-LAW1-002"
    assert result.records[0].duplicate_group == result.records[1].duplicate_group
    assert result.records[0].relative_path != result.records[1].relative_path
