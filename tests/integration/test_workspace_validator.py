from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPOSITORY_ROOT / "scripts" / "validate_workspace.py"


def _create_valid_legacy_workspace(
    tmp_path: Path,
    *,
    instruction_names: tuple[str, ...],
) -> Path:
    root = tmp_path / "workspace"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "validate_workspace.py").write_text(
        VALIDATOR.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    sources = root / "02_source_pdf"
    sources.mkdir()
    for name in ("law-1.pdf", "law-1.json", "law-2.pdf", "law-2.json"):
        (sources / name).write_bytes(b"{}" if name.endswith(".json") else b"%PDF-1.4\n")

    database_directory = root / "01_database"
    database_directory.mkdir()
    database = database_directory / "안심주택DB.grist"
    with sqlite3.connect(database) as connection:
        for table in (
            "Documents",
            "Clauses",
            "Visuals",
            "ExtractedTables",
            "Rules",
            "Cases",
            "SourceElements",
        ):
            connection.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')
        connection.execute("CREATE TABLE _grist_Attachments (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE _gristsys_Files (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE _grist_Tables (id INTEGER PRIMARY KEY, tableId TEXT)"
        )
        connection.execute(
            """
            CREATE TABLE _grist_Tables_column (
                id INTEGER PRIMARY KEY,
                parentId INTEGER,
                colId TEXT,
                displayCol INTEGER,
                visibleCol INTEGER,
                isFormula INTEGER,
                formula TEXT
            )
            """
        )

    manifest_directory = root / "04_visuals" / "manifests"
    manifest_directory.mkdir(parents=True)
    (manifest_directory / "visual_manifest.csv").write_text(
        "crop_path\n",
        encoding="utf-8-sig",
    )

    for name in instruction_names:
        (root / name).write_text("# Instructions\n", encoding="utf-8")
    return root


def _run_validator(root: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "validate_workspace.py")],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, json.loads(result.stdout)


def test_validator_accepts_canonical_agents_without_legacy_agent_md(
    tmp_path: Path,
) -> None:
    root = _create_valid_legacy_workspace(
        tmp_path,
        instruction_names=("AGENTS.md",),
    )

    result, payload = _run_validator(root)

    assert "missing: agent.md" not in payload["errors"]
    assert result.returncode == 0
    assert payload["status"] == "PASS"
