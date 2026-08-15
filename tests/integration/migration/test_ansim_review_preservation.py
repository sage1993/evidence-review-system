import json
import sqlite3
from pathlib import Path

from evidence_review.migration.evidence import migrate_evidence


def _write_records(workspace: Path, records: list[dict[str, object]]) -> None:
    path = workspace / "migration"
    path.mkdir(parents=True, exist_ok=True)
    (path / "evidence-input.json").write_text(
        json.dumps(records, ensure_ascii=False),
        encoding="utf-8",
    )


def _record(
    source_hash: str,
    normalized: str,
    status: str,
    revision: str,
) -> dict[str, object]:
    return {
        "stable_id": "CLAUSE-1",
        "revision_id": revision,
        "source_hash": source_hash,
        "document_id": "LAW1",
        "page_number": 1,
        "bbox_json": "[1,2,3,4]",
        "raw_text": "원문",
        "normalized_text": normalized,
        "review_status": status,
    }


def test_reviewed_value_survives_identical_rebuild_and_revision_change_flags(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    output = tmp_path / "output"
    _write_records(workspace, [_record("a" * 64, "검토값", "REVIEWED", "REV1")])
    migrate_evidence(workspace, output)
    _write_records(
        workspace,
        [_record("a" * 64, "자동 재생성값", "AUTOMATIC", "REV1")],
    )
    migrate_evidence(workspace, output)
    database = output / "evidence/evidence.sqlite"
    connection = sqlite3.connect(database)
    row = connection.execute(
        "SELECT normalized_text, review_status FROM migration_records"
    ).fetchone()
    assert row == ("검토값", "REVIEWED")
    connection.close()

    _write_records(workspace, [_record("b" * 64, "새 개정값", "REVIEWED", "REV2")])
    migrate_evidence(workspace, output)
    connection = sqlite3.connect(database)
    rows = connection.execute(
        "SELECT source_hash, normalized_text, review_status FROM migration_records "
        "ORDER BY source_hash"
    ).fetchall()
    connection.close()
    assert rows == [
        ("a" * 64, "검토값", "REVIEWED"),
        ("b" * 64, "새 개정값", "AUTOMATIC"),
    ]
    unresolved = json.loads(
        (output / "migration/unresolved-links.json").read_text(encoding="utf-8")
    )
    assert unresolved["format"] == "evidence-review/unresolved-links"
    assert unresolved["items"][0]["code"] == "SOURCE_REVISION_REVIEW_REQUIRED"
