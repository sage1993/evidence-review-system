from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_INSTRUCTION_FILE = "AGENTS.md"
MISSING_REQUIRED_FILE = "MISSING_REQUIRED_FILE"


def required_workspace_paths(root: Path) -> tuple[Path, ...]:
    """Return the legacy workspace files required by this validator."""
    return (
        root / "02_source_pdf" / "law-1.pdf",
        root / "02_source_pdf" / "law-1.json",
        root / "02_source_pdf" / "law-2.pdf",
        root / "02_source_pdf" / "law-2.json",
        root / "01_database" / "안심주택DB.grist",
        root / CANONICAL_INSTRUCTION_FILE,
    )


def _has_exact_filename(path: Path) -> bool:
    """Require the exact directory-entry case even on case-insensitive filesystems."""
    try:
        return path.parent.is_dir() and any(
            entry.name == path.name and entry.is_file()
            for entry in path.parent.iterdir()
        )
    except OSError:
        return False


def missing_required_files(root: Path) -> tuple[str, ...]:
    """Return missing required paths using stable POSIX-style relative names."""
    missing: list[str] = []
    for path in required_workspace_paths(root):
        exists = (
            _has_exact_filename(path)
            if path.name == CANONICAL_INSTRUCTION_FILE
            else path.exists()
        )
        if not exists:
            missing.append(path.relative_to(root).as_posix())
    return tuple(missing)


def _validate_database(root: Path, errors: list[str]) -> dict[str, int]:
    database = root / "01_database" / "안심주택DB.grist"
    if not database.exists():
        return {}

    connection = sqlite3.connect(database)
    cursor = connection.cursor()
    integrity = cursor.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        errors.append(f"sqlite integrity: {integrity}")

    names = {
        row[0]
        for row in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    required_tables = (
        "Documents",
        "Clauses",
        "Visuals",
        "ExtractedTables",
        "Rules",
        "Cases",
        "SourceElements",
    )
    for table in required_tables:
        if table not in names:
            errors.append(f"missing Grist table: {table}")

    attachments = {
        row[0] for row in cursor.execute("SELECT id FROM _grist_Attachments")
    }
    files = {row[0] for row in cursor.execute("SELECT id FROM _gristsys_Files")}
    if attachments != files:
        errors.append(
            "attachment/file id mismatch: "
            f"attachments={len(attachments)}, files={len(files)}"
        )

    for table, column in (
        ("Documents", "SourcePDF"),
        ("Visuals", "Image"),
        ("ExtractedTables", "TableImage"),
        ("Cases", "CaseImage"),
    ):
        if table not in names:
            continue
        columns = {
            row[1] for row in cursor.execute(f"PRAGMA table_info({table})")
        }
        if column not in columns:
            continue
        query = (
            f'SELECT id,{column} FROM {table} '
            f'WHERE {column} IS NOT NULL AND {column}!=""'
        )
        for row_id, raw in cursor.execute(query):
            try:
                value = json.loads(raw)
                attachment_ids = (
                    value
                    if isinstance(value, list) and (not value or value[0] != "L")
                    else []
                )
                for attachment_id in attachment_ids:
                    if attachment_id not in attachments:
                        errors.append(
                            f"broken attachment: {table}.{column} "
                            f"row {row_id} -> {attachment_id}"
                        )
            except Exception as error:  # noqa: BLE001 - report malformed legacy cells
                errors.append(
                    f"invalid attachment json: {table}.{column} "
                    f"row {row_id}: {error}"
                )

    reference_columns = (
        ("Documents", "RelatedDocuments"),
        ("Clauses", "Document"),
        ("Clauses", "ParentClause"),
        ("Visuals", "Document"),
        ("Visuals", "Clause"),
        ("Visuals", "RelatedTable"),
        ("ExtractedTables", "Document"),
        ("ExtractedTables", "Clause"),
        ("Rules", "Clause"),
        ("Cases", "Rule"),
        ("Cases", "Visual"),
        ("SourceElements", "Document"),
        ("SourceElements", "Clause"),
    )
    for table, column in reference_columns:
        table_record = cursor.execute(
            "SELECT id FROM _grist_Tables WHERE tableId=?",
            (table,),
        ).fetchone()
        if not table_record:
            continue
        reference = cursor.execute(
            """
            SELECT displayCol,visibleCol
            FROM _grist_Tables_column
            WHERE parentId=? AND colId=?
            """,
            (table_record[0], column),
        ).fetchone()
        if not reference:
            continue
        helper = (
            cursor.execute(
                """
                SELECT parentId,colId,isFormula,formula
                FROM _grist_Tables_column
                WHERE id=?
                """,
                (reference[0],),
            ).fetchone()
            if reference[0]
            else None
        )
        if (
            not helper
            or helper[0] != table_record[0]
            or not str(helper[1]).startswith("gristHelper_Display")
            or helper[2] != 1
        ):
            errors.append(f"invalid reference display helper: {table}.{column}")
        if not reference[1]:
            errors.append(f"missing reference visibleCol: {table}.{column}")

    count_tables = (
        "Documents",
        "Clauses",
        "Visuals",
        "ExtractedTables",
        "SourceElements",
    )
    counts = {
        table: cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in count_tables
    }
    connection.close()
    return counts


def _validate_visual_manifest(root: Path, errors: list[str]) -> None:
    manifest = root / "04_visuals" / "manifests" / "visual_manifest.csv"
    if not manifest.exists():
        errors.append("missing visual manifest")
        return

    with manifest.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        crop_path = row["crop_path"]
        if not (root / crop_path).exists():
            errors.append(f"manifest crop missing: {crop_path}")


def validate_workspace(root: Path = ROOT) -> dict[str, object]:
    """Validate the legacy workspace while exposing stable missing-file details."""
    errors: list[str] = []
    error_details: list[dict[str, str]] = []
    for relative_path in missing_required_files(root):
        errors.append(f"missing: {relative_path}")
        error_details.append(
            {
                "code": MISSING_REQUIRED_FILE,
                "path": relative_path,
            }
        )

    counts = _validate_database(root, errors)
    _validate_visual_manifest(root, errors)
    return {
        "status": "PASS" if not errors else "FAIL",
        "counts": counts,
        "errors": errors,
        "error_details": error_details,
    }


def main() -> int:
    result = validate_workspace()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
