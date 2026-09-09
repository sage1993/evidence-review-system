from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore


def _navigation_service():
    try:
        return importlib.import_module("evidence_review.navigation.service")
    except ModuleNotFoundError as error:
        pytest.fail(f"NAVIGATION_SERVICE_MISSING: {error}")


def _finalized_database(path: Path, *, text: str = "reference") -> None:
    with EvidenceStore(path, create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-001", "title": "Reference"},),
                revisions=(
                    {
                        "id": "REV-001",
                        "document_id": "DOC-001",
                        "source_hash": "a" * 64,
                        "byte_size": len(text.encode("utf-8")),
                        "page_count": 1,
                    },
                ),
                pages=(
                    {
                        "id": "PAGE-001",
                        "revision_id": "REV-001",
                        "page_number": 1,
                        "width": 600.0,
                        "height": 800.0,
                    },
                ),
                elements=(
                    {
                        "id": "EVID-001",
                        "page_id": "PAGE-001",
                        "element_type": "paragraph",
                        "raw_json": {"text": text},
                        "raw_text": text,
                        "normalized_text": text,
                        "raw_payload_hash": "d" * 64,
                        "bbox": [10.0, 10.0, 500.0, 30.0],
                        "parser_order": 0,
                    },
                ),
            ),
        )
        finalize_evidence_database(store)


def test_navigation_is_read_only_and_returns_traceable_citation(tmp_path: Path) -> None:
    database = tmp_path / "evidence.sqlite"
    _finalized_database(database)
    before = database.read_bytes()
    before_provenance = finalized_evidence_provenance(database)

    result = _navigation_service().navigate_evidence(database, "reference")

    assert result.query == "reference"
    assert result.evidence_snapshot_hash == before_provenance["evidence_snapshot_hash"]
    assert result.evidence_db_sha256 == before_provenance["evidence_db_sha256"]
    assert len(result.hits) == 1
    hit = result.hits[0]
    assert hit.evidence_id == "EVID-001"
    assert hit.document_id == "DOC-001"
    assert hit.revision_id == "REV-001"
    assert hit.page_number == 1
    assert hit.bbox.left == 10.0
    assert hit.source_hash == "a" * 64
    assert hit.citation.evidence_id == hit.evidence_id
    assert not (tmp_path / "runs").exists()
    assert database.read_bytes() == before


@pytest.mark.parametrize(
    ("query", "limit"),
    [("", 20), ("   ", 20), ("reference", 0), ("reference", -1), ("reference", True)],
)
def test_navigation_rejects_empty_query_and_invalid_limit(
    tmp_path: Path, query: str, limit: object
) -> None:
    database = tmp_path / "evidence.sqlite"
    _finalized_database(database)

    with pytest.raises(ValueError):
        _navigation_service().navigate_evidence(database, query, limit=limit)


def test_navigation_rejects_unfinalized_database(tmp_path: Path) -> None:
    database = tmp_path / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-001", "title": "Reference"},),
            ),
        )

    with pytest.raises(Exception):
        _navigation_service().navigate_evidence(database, "reference")


def test_navigation_rejects_sidecar_backed_database(tmp_path: Path) -> None:
    database = tmp_path / "evidence.sqlite"
    _finalized_database(database)
    database.with_name(database.name + "-wal").write_bytes(b"sidecar")

    with pytest.raises(RuntimeError, match="EVIDENCE_DATABASE_SIDECAR_PRESENT"):
        _navigation_service().navigate_evidence(database, "reference")


def test_navigation_rejects_stale_logical_snapshot(tmp_path: Path) -> None:
    import sqlite3

    database = tmp_path / "evidence.sqlite"
    _finalized_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE snapshot_meta SET value = ? WHERE key = 'snapshot_hash'",
            ("f" * 64,),
        )
        connection.commit()

    with pytest.raises(Exception):
        _navigation_service().navigate_evidence(database, "reference")


def test_navigation_rejects_malformed_citation(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "evidence.sqlite"
    _finalized_database(database)
    service = _navigation_service()
    monkeypatch.setattr(
        service,
        "build_evidence_bundle",
        lambda _connection, _request: {
            "snapshot_hash": "a" * 64,
            "hits": [{"citation": ["not", "an", "object"]}],
        },
    )

    with pytest.raises(ValueError, match="citation"):
        service.navigate_evidence(database, "reference")


def test_navigation_rejects_citation_hit_identity_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "evidence.sqlite"
    _finalized_database(database)
    service = _navigation_service()
    monkeypatch.setattr(
        service,
        "build_evidence_bundle",
        lambda _connection, _request: {
            "snapshot_hash": "a" * 64,
            "hits": [
                {
                    "evidence_id": "EVID-001",
                    "evidence_type": "paragraph",
                    "document_id": "DOC-001",
                    "revision_id": "REV-001",
                    "page_number": 1,
                    "bbox": [10.0, 10.0, 500.0, 30.0],
                    "source_hash": "a" * 64,
                    "title": "Reference",
                    "text": "reference",
                    "final_score": "1.0",
                    "citation": {
                        "citation_id": "CIT-EVID-001",
                        "document_id": "DOC-OTHER",
                        "revision_id": "REV-001",
                        "page_number": 1,
                        "evidence_id": "EVID-001",
                        "bbox": [10.0, 10.0, 500.0, 30.0],
                        "source_hash": "a" * 64,
                    },
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="identity"):
        service.navigate_evidence(database, "reference")


def test_navigation_skips_page_only_hit_before_citation_parsing(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "evidence.sqlite"
    _finalized_database(database)
    provenance = finalized_evidence_provenance(database)
    service = _navigation_service()
    monkeypatch.setattr(
        service,
        "build_evidence_bundle",
        lambda _connection, _request: {
            "snapshot_hash": provenance["evidence_snapshot_hash"],
            "hits": [
                {
                    "evidence_id": "EVID-001",
                    "evidence_type": "paragraph",
                    "document_id": "DOC-001",
                    "revision_id": "REV-001",
                    "page_number": 1,
                    "bbox": None,
                    "citation_quality": "PAGE_ONLY",
                    "source_hash": "a" * 64,
                    "title": "Reference",
                    "text": "reference",
                    "final_score": "1.0",
                    "citation": ["not", "a", "citation"],
                }
            ],
        },
    )

    assert service.navigate_evidence(database, "reference").hits == ()
