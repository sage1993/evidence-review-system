import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from ansim_review.canonical_json import dumps

V1_SCHEMA = Path("tests/fixtures/evidence/schema_v1.sql")


def create_v1_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(V1_SCHEMA.read_text(encoding="utf-8"))
    connection.execute("INSERT INTO documents(id, title) VALUES('DOC-1', 'Document')")
    connection.execute(
        """
        INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
        VALUES('REV-1', 'DOC-1', ?, 10, 1)
        """,
        ("a" * 64,),
    )
    connection.execute(
        """
        INSERT INTO pages(id, revision_id, page_number, width, height)
        VALUES('REV-1-P0001', 'REV-1', 1, 600, 800)
        """
    )
    connection.execute(
        """
        INSERT INTO elements(
            id, revision_id, page_id, page_number, element_type, raw_json,
            raw_text, normalized_text, raw_payload_hash, bbox_json, parser_order
        ) VALUES('E-1', 'REV-1', 'REV-1-P0001', 1, 'paragraph', ?,
                 'content', 'content', ?, ?, 0)
        """,
        (dumps({"text": "content"}), "b" * 64, dumps([10, 20, 30, 40])),
    )
    connection.commit()
    connection.close()


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[3] / "src")
    return subprocess.run(
        [sys.executable, "-m", "ansim_review", *arguments],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_evidence_migrate_cli_outputs_canonical_status(tmp_path: Path) -> None:
    source = tmp_path / "v1.sqlite"
    output = tmp_path / "v2.sqlite"
    create_v1_database(source)

    result = run_cli(
        "evidence",
        "migrate",
        "--source",
        str(source),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["format"] == "evidence-review/evidence-migration-status"
    assert payload["version"] == 1
    assert payload["status"] == "MIGRATED"
    assert payload["source_schema_version"] == 1
    assert payload["output_schema_version"] == 2
    assert payload["source_db"] == str(source.resolve())
    assert payload["output_db"] == str(output.resolve())
    assert payload["report"] == str(
        output.resolve().with_name(f"{output.name}.migration-report.json")
    )
    assert len(payload["logical_snapshot_hash"]) == 64
    assert output.is_file()


def test_evidence_migrate_cli_existing_output_returns_one(tmp_path: Path) -> None:
    source = tmp_path / "v1.sqlite"
    output = tmp_path / "v2.sqlite"
    create_v1_database(source)
    output.write_bytes(b"existing")

    result = run_cli(
        "evidence",
        "migrate",
        "--source",
        str(source),
        "--output",
        str(output),
    )

    assert result.returncode == 1
    assert str(output.resolve()) in result.stderr
    assert output.read_bytes() == b"existing"


def test_evidence_migrate_cli_invalid_source_returns_two(tmp_path: Path) -> None:
    source = tmp_path / "invalid.sqlite"
    output = tmp_path / "v2.sqlite"
    sqlite3.connect(source).close()

    result = run_cli(
        "evidence",
        "migrate",
        "--source",
        str(source),
        "--output",
        str(output),
    )

    assert result.returncode == 2
    assert "unrecognized evidence schema" in result.stderr
    assert not output.exists()


def test_evidence_migrate_help_is_available() -> None:
    result = run_cli("evidence", "migrate", "--help")

    assert result.returncode == 0
    assert "--source" in result.stdout
    assert "--output" in result.stdout
