from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.store import EvidenceStore
from ansim_review.retrieval.bundle import build_evidence_bundle
from ansim_review.retrieval.index import (
    build_fts_index,
    search_fts_phrase,
    search_fts_token_and,
)


def _snapshot() -> EvidenceSnapshot:
    exact = "이면도로 차량 진출입 기준"
    reordered = "차량 진출입 안전 검토 이면도로 기준"
    return EvidenceSnapshot(
        documents=({"id": "LAW1", "title": "검색 기준"},),
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
                "id": "E-EXACT",
                "revision_id": "LAW1-REV1",
                "page_id": "LAW1-P1",
                "page_number": 1,
                "element_type": "clause",
                "raw_json": {"text": exact},
                "raw_text": exact,
                "normalized_text": exact,
                "raw_payload_hash": "b" * 64,
                "bbox": [10.0, 20.0, 200.0, 50.0],
                "parser_order": 0,
            },
            {
                "id": "E-REORDERED",
                "revision_id": "LAW1-REV1",
                "page_id": "LAW1-P1",
                "page_number": 1,
                "element_type": "clause",
                "raw_json": {"text": reordered},
                "raw_text": reordered,
                "normalized_text": reordered,
                "raw_payload_hash": "c" * 64,
                "bbox": [10.0, 60.0, 240.0, 90.0],
                "parser_order": 1,
            },
        ),
    )


@contextmanager
def _store(tmp_path: Path) -> Iterator[EvidenceStore]:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot())
        build_fts_index(store.require_connection())
        yield store


def test_exact_phrase_keeps_precision_while_token_and_recovers_reordered_text(
    tmp_path: Path,
) -> None:
    with _store(tmp_path) as store:
        connection = store.require_connection()
        phrase_hits = search_fts_phrase(connection, "이면도로 차량 진출입 기준")
        token_hits = search_fts_token_and(connection, "이면도로 차량 진출입 기준")

    assert [hit.evidence_id for hit in phrase_hits] == ["E-EXACT"]
    assert {hit.evidence_id for hit in token_hits} == {"E-EXACT", "E-REORDERED"}
    assert phrase_hits[0].channel_scores[0].channel == "fts_phrase"
    assert all(hit.channel_scores[0].channel == "fts_token_and" for hit in token_hits)


def test_primary_query_recovers_reordered_text_without_synonym_or_llm(
    tmp_path: Path,
) -> None:
    with _store(tmp_path) as store:
        bundle = build_evidence_bundle(
            store.require_connection(),
            {
                "question": "이면도로 차량 진출입 기준",
                "synonym_manifest": {},
                "expansions": [],
                "limit": 20,
            },
        )

    assert [hit["evidence_id"] for hit in bundle["hits"]] == [
        "E-EXACT",
        "E-REORDERED",
    ]
    reordered = bundle["hits"][1]
    assert [item["channel"] for item in reordered["channel_scores"]] == [
        "fts_token_and"
    ]
    assert reordered["channel_scores"][0]["detail"].startswith("primary:")


def test_bundle_preserves_all_query_origins_without_duplicate_channel_weight(
    tmp_path: Path,
) -> None:
    with _store(tmp_path) as store:
        bundle = build_evidence_bundle(
            store.require_connection(),
            {
                "question": "이면도로 차량 진출입 기준",
                "synonym_manifest": {
                    "이면도로 차량 진출입 기준": ["차량 진출입 이면도로 기준"]
                },
                "expansions": [
                    {"origin": "llm", "text": "이면도로 진출입 차량 기준"}
                ],
                "limit": 20,
            },
        )

    exact = next(hit for hit in bundle["hits"] if hit["evidence_id"] == "E-EXACT")
    scores = {item["channel"]: item for item in exact["channel_scores"]}
    assert set(scores) == {"fts_phrase", "fts_token_and"}
    token_detail = scores["fts_token_and"]["detail"]
    assert "primary:" in token_detail
    assert "approved_synonym:" in token_detail
    assert "llm:" in token_detail
