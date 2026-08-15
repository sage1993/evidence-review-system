import sqlite3
from pathlib import Path

import pytest

from evidence_review.evidence.migrations.v1_to_v2 import migrate_v1_to_v2

V1_SCHEMA = Path("tests/fixtures/evidence/schema_v1.sql")


def create_empty_v1(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(V1_SCHEMA.read_text(encoding="utf-8"))
    connection.close()


@pytest.mark.parametrize(
    "temporary_name",
    [
        ".v2.sqlite.tmp",
        ".v2.sqlite.migration-report.json.tmp",
    ],
)
def test_migration_preserves_existing_temporary_paths(
    tmp_path: Path,
    temporary_name: str,
) -> None:
    source = tmp_path / "v1.sqlite"
    output = tmp_path / "v2.sqlite"
    existing_temporary = tmp_path / temporary_name
    create_empty_v1(source)
    existing_temporary.write_bytes(b"user-owned")

    with pytest.raises(FileExistsError):
        migrate_v1_to_v2(source, output)

    assert existing_temporary.read_bytes() == b"user-owned"
    assert not output.exists()
    assert not (tmp_path / "v2.sqlite.migration-report.json").exists()
