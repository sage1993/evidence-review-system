"""Source-preserving legacy workspace inventory and evidence migration."""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from ansim_review.canonical_json import dump_bytes, sha256_json
from ansim_review.contracts.formats import SOURCE_INVENTORY_FORMAT

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_inventory(root: Path) -> tuple[dict[str, object], ...]:
    """Return a stable relative-path inventory for every file below *root*."""
    if not root.exists():
        return ()
    return tuple(
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _hash_file(path),
            "size": path.stat().st_size,
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    )


def _category(path: Path, workspace_root: Path) -> str:
    relative = path.relative_to(workspace_root).as_posix()
    suffix = path.suffix.lower()
    if relative.startswith("02_source_pdf/") and suffix == ".pdf":
        return "pdfs"
    if relative.startswith("02_source_pdf/") and suffix in {".json", ".md"}:
        return "parser_outputs"
    if relative.startswith("03_extracted_images/"):
        return "images"
    if relative.startswith("04_visuals/table_crops/"):
        return "tables"
    if relative.startswith("05_exports/") and "clause" in path.name.lower():
        return "clauses"
    if relative.startswith("05_exports/"):
        return "exports"
    if suffix == ".grist":
        return "grist"
    return "other"


def source_inventory(workspace_root: Path) -> dict[str, object]:
    """Inventory source, parser, visual, export, and Grist files."""
    roots = (
        workspace_root / "01_database",
        workspace_root / "02_source_pdf",
        workspace_root / "03_extracted_images",
        workspace_root / "04_visuals",
        workspace_root / "05_exports",
    )
    records: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            category = _category(path, workspace_root)
            counts[category] = counts.get(category, 0) + 1
            records.append(
                {
                    "path": path.relative_to(workspace_root).as_posix(),
                    "category": category,
                    "sha256": _hash_file(path),
                    "size": path.stat().st_size,
                }
            )
    return {
        "format": SOURCE_INVENTORY_FORMAT,
        "version": 1,
        "counts": {name: counts[name] for name in sorted(counts)},
        "files": records,
        "inventory_hash": sha256_json(records),
    }


def inventory_and_backup(
    workspace_root: Path,
    output_root: Path,
    *,
    date_label: str,
) -> dict[str, object]:
    """Back up source/Grist files and prove the source tree stayed unchanged."""
    if not _DATE.fullmatch(date_label):
        raise ValueError("date_label must use YYYY-MM-DD")
    source = workspace_root / "02_source_pdf"
    before = tree_inventory(source)
    backup = output_root / "migration" / "backups" / date_label
    if backup.exists():
        raise FileExistsError(backup)
    backup.mkdir(parents=True)
    if source.exists():
        shutil.copytree(source, backup / "02_source_pdf")
    grist = workspace_root / "01_database"
    if grist.exists():
        (backup / "01_database").mkdir()
        for path in sorted(grist.glob("*.grist")):
            shutil.copy2(path, backup / "01_database" / path.name)
    after = tree_inventory(source)
    if before != after:
        raise RuntimeError("source tree changed during migration backup")
    inventory = source_inventory(workspace_root)
    inventory["source_tree_hash"] = sha256_json(before)
    inventory["backup_path"] = backup.relative_to(output_root).as_posix()
    destination = output_root / "migration" / "source-inventory.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(dump_bytes(inventory))
    return inventory
