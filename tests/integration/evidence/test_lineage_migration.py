from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from evidence_review.canonical_json import dump_bytes
from evidence_review.evidence.lineage_contract import (
    DocumentLineageMapping,
    LegacyLineageManifest,
    RevisionMapping,
    legacy_lineage_manifest_document,
)
from evidence_review.evidence.lineage_migration import (
    apply_legacy_lineage_migration,
)
from evidence_review.evidence.store import EvidenceStore

LEGACY_DOCUMENT = "LAW3"
CANONICAL_DOCUMENT = "DOC-ACFD68E34043268C"
LEGACY_REVISION = "REV-LAW3-001"
CANONICAL_REVISION = "REV-DOC-001"
SOURCE_HASH = "b" * 64


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _insert_graph(connection: sqlite3.Connection, prefix: str, document_id: str) -> None:
    revision_id = LEGACY_REVISION if prefix == "L" else CANONICAL_REVISION
    page_id = f"PAGE-{prefix}-001"
    element_id = f"ELEMENT-{prefix}-001"
    clause_id = f"CLAUSE-{prefix}-001"
    table_id = f"TABLE-{prefix}-001"
    visual_id = f"VISUAL-{prefix}-001"
    link_id = f"LINK-{prefix}-001"
    flag_id = f"FLAG-{prefix}-001"
    retrieval_id = f"RETRIEVAL-{prefix}-001"

    connection.execute(
        "INSERT INTO documents(id, title) VALUES(?, 'Same source document')",
        (document_id,),
    )
    connection.execute(
        """
        INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
        VALUES(?, ?, ?, 100, 1)
        """,
        (revision_id, document_id, SOURCE_HASH),
    )
    connection.execute(
        """
        INSERT INTO pages(id, revision_id, page_number, width, height)
        VALUES(?, ?, 1, 595.0, 842.0)
        """,
        (page_id, revision_id),
    )
    connection.execute(
        """
        INSERT INTO elements(
            id, page_id, element_type, raw_json, raw_text, normalized_text,
            raw_payload_hash, bbox_json, parser_order
        ) VALUES(?, ?, 'text', '{"text":"same"}', 'same', 'same', ?,
                 '[1,2,3,4]', 0)
        """,
        (element_id, page_id, "c" * 64),
    )
    connection.execute(
        """
        INSERT INTO clauses(
            id, revision_id, title, raw_text, normalized_text, review_status
        ) VALUES(?, ?, 'Article 1', 'same clause', 'same clause', 'REVIEWED')
        """,
        (clause_id, revision_id),
    )
    connection.execute(
        """
        INSERT INTO tables(id, page_id, bbox_json, raw_json, normalized_json)
        VALUES(?, ?, '[10,20,30,40]', '{"rows":[["same"]]}',
               '{"rows":[["same"]]}')
        """,
        (table_id, page_id),
    )
    connection.execute(
        """
        INSERT INTO visuals(
            id, page_id, kind, relative_path, sha256, bbox_json, duplicate_group
        ) VALUES(?, ?, 'page_render', 'assets/page-1.png', ?,
                 '[0,0,595,842]', 'DUP-SAME')
        """,
        (visual_id, page_id, "d" * 64),
    )
    connection.execute(
        "INSERT INTO links VALUES(?, ?, ?, 'supports')",
        (link_id, element_id, clause_id),
    )
    connection.execute(
        """
        INSERT INTO review_flags(id, evidence_id, code, status, detail)
        VALUES(?, ?, 'CHECKED', 'CLOSED', 'same detail')
        """,
        (flag_id, clause_id),
    )
    connection.execute(
        """
        INSERT INTO retrieval_records(
            evidence_id, evidence_type, document_id, revision_id, page_id,
            page_number, bbox_json, source_hash, title, raw_text, normalized_text
        ) VALUES(?, 'clause', ?, ?, ?, 1, '[1,2,3,4]', ?, 'Article 1',
                 'same clause', 'same clause')
        """,
        (retrieval_id, document_id, revision_id, page_id, SOURCE_HASH),
    )


def _write_source_and_manifest(
    root: Path,
) -> tuple[Path, Path, LegacyLineageManifest]:
    root.mkdir(parents=True, exist_ok=True)
    database = root / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        connection = store.require_connection()
        _insert_graph(connection, "L", LEGACY_DOCUMENT)
        _insert_graph(connection, "C", CANONICAL_DOCUMENT)
        connection.commit()

    manifest = LegacyLineageManifest(
        source_database_sha256=_sha256_file(database),
        reviewer_id="ksh",
        reviewed_at=datetime.datetime.fromisoformat("2026-08-02T16:49:00+09:00"),
        mappings=(
            DocumentLineageMapping(
                legacy_document_id=LEGACY_DOCUMENT,
                canonical_document_id=CANONICAL_DOCUMENT,
                source_sha256=SOURCE_HASH,
                reason="same immutable PDF registered under a legacy alias",
                revision_mappings=(
                    RevisionMapping(
                        legacy_revision_id=LEGACY_REVISION,
                        canonical_revision_id=CANONICAL_REVISION,
                    ),
                ),
            ),
        ),
    )
    manifest_path = root / "legacy-lineage-manifest.json"
    manifest_path.write_bytes(dump_bytes(legacy_lineage_manifest_document(manifest)))
    return database, manifest_path, manifest


def _artifact_paths(output: Path) -> tuple[Path, Path]:
    return (
        output.with_name(f"{output.name}.legacy-lineage-aliases.json"),
        output.with_name(f"{output.name}.legacy-lineage-migration-report.json"),
    )


def test_copy_on_write_migration_removes_only_equivalent_legacy_graph(
    tmp_path: Path,
) -> None:
    source, manifest_path, _ = _write_source_and_manifest(tmp_path / "source")
    source_before = source.read_bytes()
    output = tmp_path / "migrated" / "evidence.sqlite"

    result = apply_legacy_lineage_migration(source, manifest_path, output)

    assert source.read_bytes() == source_before
    assert result.output_database == output.resolve()
    assert result.output_sha256 == _sha256_file(output)
    assert len(result.logical_lineage_digest) == 64
    aliases_path, report_path = _artifact_paths(output)
    assert result.aliases_path == aliases_path.resolve()
    assert result.report_path == report_path.resolve()
    assert aliases_path.is_file()
    assert report_path.is_file()

    with sqlite3.connect(output) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT id FROM documents ORDER BY id"
        ).fetchall() == [(CANONICAL_DOCUMENT,)]
        assert connection.execute(
            "SELECT id FROM revisions ORDER BY id"
        ).fetchall() == [(CANONICAL_REVISION,)]
        assert connection.execute(
            "SELECT id FROM pages ORDER BY id"
        ).fetchall() == [("PAGE-C-001",)]
        assert connection.execute(
            "SELECT id FROM elements ORDER BY id"
        ).fetchall() == [("ELEMENT-C-001",)]
        assert connection.execute(
            "SELECT id, review_status FROM clauses ORDER BY id"
        ).fetchall() == [("CLAUSE-C-001", "REVIEWED")]
        assert connection.execute(
            "SELECT evidence_id FROM retrieval_records ORDER BY evidence_id"
        ).fetchall() == [("RETRIEVAL-C-001",)]

    aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
    assert aliases["format"] == "evidence-review/legacy-lineage-aliases"
    assert aliases["entries"][0]["legacy_document_id"] == LEGACY_DOCUMENT
    assert aliases["entries"][0]["canonical_document_id"] == CANONICAL_DOCUMENT

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["format"] == "evidence-review/legacy-lineage-migration-report"
    assert report["status"] == "MIGRATED"
    assert report["integrity_check"] == "ok"
    assert report["foreign_key_violations"] == 0
    assert report["unresolved"] == []


def test_blocked_plan_creates_no_output_or_temporary_files(tmp_path: Path) -> None:
    source, manifest_path, manifest = _write_source_and_manifest(tmp_path / "source")
    connection = sqlite3.connect(source)
    connection.execute(
        "UPDATE elements SET normalized_text='different' WHERE id='ELEMENT-L-001'"
    )
    connection.commit()
    connection.close()
    manifest = LegacyLineageManifest(
        source_database_sha256=_sha256_file(source),
        reviewer_id=manifest.reviewer_id,
        reviewed_at=manifest.reviewed_at,
        mappings=manifest.mappings,
    )
    manifest_path.write_bytes(dump_bytes(legacy_lineage_manifest_document(manifest)))
    output = tmp_path / "migrated" / "evidence.sqlite"

    with pytest.raises(ValueError, match="EVIDENCE_COUNTERPART_MISSING"):
        apply_legacy_lineage_migration(source, manifest_path, output)

    aliases_path, report_path = _artifact_paths(output)
    assert not output.exists()
    assert not aliases_path.exists()
    assert not report_path.exists()
    assert not list(output.parent.glob(".*lineage*")) if output.parent.exists() else True


def test_existing_output_and_temporary_paths_are_never_overwritten(
    tmp_path: Path,
) -> None:
    source, manifest_path, _ = _write_source_and_manifest(tmp_path / "source")
    output = tmp_path / "migrated" / "evidence.sqlite"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        apply_legacy_lineage_migration(source, manifest_path, output)
    assert output.read_bytes() == b"existing"

    output.unlink()
    temporary = output.with_name(f".{output.name}.lineage.tmp")
    temporary.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        apply_legacy_lineage_migration(source, manifest_path, output)
    assert temporary.read_bytes() == b"keep"
    assert not output.exists()


def test_source_and_output_paths_must_differ(tmp_path: Path) -> None:
    source, manifest_path, _ = _write_source_and_manifest(tmp_path / "source")
    before = source.read_bytes()

    with pytest.raises(ValueError, match="must differ"):
        apply_legacy_lineage_migration(source, manifest_path, source)

    assert source.read_bytes() == before


def test_repeated_migration_is_logically_and_byte_deterministic(
    tmp_path: Path,
) -> None:
    source, manifest_path, _ = _write_source_and_manifest(tmp_path / "source")
    output_a = tmp_path / "run-a" / "evidence.sqlite"
    output_b = tmp_path / "run-b" / "evidence.sqlite"

    result_a = apply_legacy_lineage_migration(source, manifest_path, output_a)
    result_b = apply_legacy_lineage_migration(source, manifest_path, output_b)

    assert result_a.logical_lineage_digest == result_b.logical_lineage_digest
    assert output_a.read_bytes() == output_b.read_bytes()
    aliases_a, report_a = _artifact_paths(output_a)
    aliases_b, report_b = _artifact_paths(output_b)
    assert aliases_a.read_bytes() == aliases_b.read_bytes()
    assert report_a.read_bytes() == report_b.read_bytes()


def test_artifact_write_failure_rolls_back_every_generated_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, manifest_path, _ = _write_source_and_manifest(tmp_path / "source")
    output = tmp_path / "migrated" / "evidence.sqlite"

    from evidence_review.evidence import lineage_migration

    original = lineage_migration._write_create_only
    calls = 0

    def fail_second_write(path: Path, payload: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated artifact failure")
        original(path, payload)

    monkeypatch.setattr(lineage_migration, "_write_create_only", fail_second_write)

    with pytest.raises(OSError, match="simulated artifact failure"):
        apply_legacy_lineage_migration(source, manifest_path, output)

    aliases_path, report_path = _artifact_paths(output)
    assert not output.exists()
    assert not aliases_path.exists()
    assert not report_path.exists()
    assert not list(output.parent.glob(".*lineage*")) if output.parent.exists() else True
