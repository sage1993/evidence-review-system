import json
from pathlib import Path

from ansim_review.migration.ansim_workspace import inventory_and_backup, tree_inventory


def test_source_tree_hashes_are_identical_before_and_after_migration(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "02_source_pdf"
    database = workspace / "01_database"
    source.mkdir(parents=True)
    database.mkdir()
    (source / "law-1.pdf").write_bytes(b"PDF-1")
    (source / "law-1.json").write_text('{"pages":1}', encoding="utf-8")
    (database / "안심주택DB.grist").write_bytes(b"GRIST")
    before = tree_inventory(source)
    output = tmp_path / "output"
    inventory = inventory_and_backup(workspace, output, date_label="2026-08-01")
    after = tree_inventory(source)
    assert before == after
    assert inventory["counts"]["pdfs"] == 1
    assert inventory["counts"]["parser_outputs"] == 1
    assert (output / "migration/backups/2026-08-01/02_source_pdf/law-1.pdf").is_file()
    assert (
        output
        / "migration/backups/2026-08-01/01_database/안심주택DB.grist"
    ).is_file()
    saved = json.loads(
        (output / "migration/source-inventory.json").read_text(encoding="utf-8")
    )
    assert saved["source_tree_hash"] == inventory["source_tree_hash"]
