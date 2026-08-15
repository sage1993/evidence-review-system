from pathlib import Path

import pytest

from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.index import (
    StaleRetrievalIndexError,
    build_fts_index,
    search_fts,
)


def _snapshot(text: str = "이면도로 차량 진출입 기준") -> EvidenceSnapshot:
    return EvidenceSnapshot(
        documents=({"id": "LAW1", "title": "안심주택 운영기준"},),
        revisions=(
            {
                "id": "LAW1-REV1",
                "document_id": "LAW1",
                "source_hash": "a" * 64,
                "byte_size": 10,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": "LAW1-P1",
                "revision_id": "LAW1-REV1",
                "page_number": 1,
                "width": 595.0,
                "height": 842.0,
            },
        ),
        elements=(
            {
                "id": "E-KR-1",
                "revision_id": "LAW1-REV1",
                "page_id": "LAW1-P1",
                "page_number": 1,
                "element_type": "clause",
                "raw_json": {"text": text},
                "raw_text": text,
                "normalized_text": text,
                "raw_payload_hash": "b" * 64,
                "bbox": [10.0, 20.0, 200.0, 50.0],
                "parser_order": 0,
            },
        ),
    )


def test_korean_fts_query_returns_page_resolved_hits(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence.sqlite"
    with EvidenceStore(db_path, create=True) as store:
        snapshot_hash = ingest_snapshot(store, _snapshot())
        assert build_fts_index(store.require_connection()) == snapshot_hash
        hits = search_fts(
            store.require_connection(),
            "이면도로 차량 진출입",
        )

    assert [hit.evidence_id for hit in hits] == ["E-KR-1"]
    hit = hits[0]
    assert hit.document_id == "LAW1"
    assert hit.revision_id == "LAW1-REV1"
    assert hit.page_number == 1
    assert hit.bbox.left == 10.0
    assert hit.source_hash == "a" * 64
    assert hit.channel_scores[0].channel == "fts_phrase"


def test_stale_index_is_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence.sqlite"
    with EvidenceStore(db_path, create=True) as store:
        ingest_snapshot(store, _snapshot())
        build_fts_index(store.require_connection())
        store.require_connection().execute(
            "UPDATE snapshot_meta SET value = ? WHERE key = 'snapshot_hash'",
            ("f" * 64,),
        )
        store.require_connection().commit()

        with pytest.raises(
            StaleRetrievalIndexError,
            match="snapshot hash mismatch",
        ):
            search_fts(store.require_connection(), "이면도로")


def test_fts_shadow_aliases_preserve_authority_fields(tmp_path: Path) -> None:
    expected = (
        "\uc8fc\ucc28 \uad6c\ud68d\uc120 "
        "\ud06c\uae30\ub294 \uae30\uc900\uc5d0 "
        "\ub9de\ucdb0\uc57c \ud55c\ub2e4."
    )
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot(expected))
        build_fts_index(store.require_connection())
        record = (
            store.require_connection()
            .execute(
                "SELECT raw_text, normalized_text, source_hash FROM retrieval_records "
                "WHERE evidence_id = ?",
                ("E-KR-1",),
            )
            .fetchone()
        )

    assert record is not None
    assert record["raw_text"] == expected
    assert record["normalized_text"] == expected
    assert record["source_hash"] == "a" * 64
