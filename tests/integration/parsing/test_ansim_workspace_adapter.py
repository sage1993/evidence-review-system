import csv
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from ansim_review.parsing.ansim_workspace_adapter import import_ansim_workspace


def _write_workspace(root: Path) -> None:
    source = root / "02_source_pdf"
    exports = root / "05_exports"
    source.mkdir(parents=True)
    exports.mkdir(parents=True)

    for stem, text in (("law-1", "first law"), ("law-2", "second law")):
        (source / f"{stem}.pdf").write_bytes(f"%PDF-1.7\n{stem}".encode())
        (source / f"{stem}.json").write_text(
            json.dumps(
                {
                    "file name": f"{stem}.pdf",
                    "number of pages": 1,
                    "kids": [
                        {
                            "type": "paragraph",
                            "page number": 1,
                            "bounding box": [10, 20, 100, 40],
                            "content": text,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    visuals = root / "04_visuals"
    image = visuals / "image_context_crops" / "law1.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"visual-law1")
    manifest = visuals / "manifests" / "law-1-visuals.json"
    manifest.parent.mkdir(parents=True)
    law1_hash = hashlib.sha256(b"%PDF-1.7\nlaw-1").hexdigest()
    law1_revision_id = f"LAW1-{law1_hash[:12]}"
    law1_page_id = f"{law1_revision_id}-P0001"
    law1_element_id = f"LAW1-{law1_revision_id}-P0001-E00001"
    image_hash = hashlib.sha256(b"visual-law1").hexdigest()
    manifest.write_text(
        json.dumps(
            {
                "format": "evidence-review/visual-manifest",
                "version": 1,
                "records": [
                    {
                        "id": "VISUAL-LAW1-001",
                        "document_id": "LAW1",
                        "revision_id": law1_revision_id,
                        "page_id": law1_page_id,
                        "kind": "occurrence_crop",
                        "path": "04_visuals/image_context_crops/law1.png",
                        "sha256": image_hash,
                        "bbox": [10, 20, 30, 40],
                        "source_evidence_ids": [law1_element_id],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with (exports / "Clauses.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "ClauseID",
                "DocumentID",
                "Title",
                "RawText",
                "NormalizedText",
                "ReviewStatus",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ClauseID": "CLAUSE-LAW1-001",
                "DocumentID": "LAW1",
                "Title": "Clause One",
                "RawText": "raw one",
                "NormalizedText": "normalized one",
                "ReviewStatus": "REVIEWED",
            }
        )
        writer.writerow(
            {
                "ClauseID": "CLAUSE-LAW2-001",
                "DocumentID": "LAW2",
                "Title": "Clause Two",
                "RawText": "raw two",
                "NormalizedText": "normalized two",
                "ReviewStatus": "AUTOMATIC",
            }
        )

    with (exports / "Links.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["LinkID", "SourceID", "TargetID", "RelationType"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "LinkID": "LINK-001",
                "SourceID": "CLAUSE-LAW1-001",
                "TargetID": "MISSING-EVIDENCE",
                "RelationType": "CITES",
            }
        )


def test_workspace_copies_produce_identical_snapshot_hash(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    _write_workspace(first_root)
    shutil.copytree(first_root, second_root)

    first = import_ansim_workspace(first_root, tmp_path / "first.sqlite")
    second = import_ansim_workspace(second_root, tmp_path / "second.sqlite")

    assert first.snapshot_hash == second.snapshot_hash
    assert first.counts == second.counts
    assert first.counts["documents"] == 2
    assert first.counts["elements"] == 2
    assert first.counts["clauses"] == 2
    assert first.counts["visuals"] == 1
    assert first.counts["links"] == 1
    assert first.unresolved_link_count == 1
    assert first.unresolved_links_path.read_bytes() == second.unresolved_links_path.read_bytes()

    with sqlite3.connect(tmp_path / "first.sqlite") as connection:
        assert connection.execute(
            "SELECT review_status FROM clauses WHERE id='CLAUSE-LAW1-001'"
        ).fetchone() == ("REVIEWED",)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
