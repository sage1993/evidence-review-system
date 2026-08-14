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
    culture_house = (
        "청소년문화의집은 다양한 유형의 청소년수련시설 중 가장 작은 규모의 시설"
    )
    youth_center_criterion = (
        "청소년수련관은 연건축면적이 1,500제곱미터 이상이어야 한다"
    )
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
            {
                "id": "E-CULTURE-HOUSE",
                "revision_id": "LAW1-REV1",
                "page_id": "LAW1-P1",
                "page_number": 1,
                "element_type": "table_cell",
                "raw_json": {"text": culture_house},
                "raw_text": culture_house,
                "normalized_text": culture_house,
                "raw_payload_hash": "d" * 64,
                "bbox": [10.0, 100.0, 500.0, 130.0],
                "parser_order": 2,
            },
            {
                "id": "E-YOUTH-CENTER-1500",
                "revision_id": "LAW1-REV1",
                "page_id": "LAW1-P1",
                "page_number": 1,
                "element_type": "table_cell",
                "raw_json": {"text": youth_center_criterion},
                "raw_text": youth_center_criterion,
                "normalized_text": youth_center_criterion,
                "raw_payload_hash": "e" * 64,
                "bbox": [10.0, 140.0, 500.0, 170.0],
                "parser_order": 3,
            },
            {
                "id": "E-PARKING-LINE",
                "revision_id": "LAW1-REV1",
                "page_id": "LAW1-P1",
                "page_number": 1,
                "element_type": "clause",
                "raw_json": {"text": "\uc8fc\ucc28 \uad6c\ud68d\uc120 \ud06c\uae30\ub294 \uae30\uc900\uc5d0 \ub9de\ucdb0\uc57c \ud55c\ub2e4."},
                "raw_text": "\uc8fc\ucc28 \uad6c\ud68d\uc120 \ud06c\uae30\ub294 \uae30\uc900\uc5d0 \ub9de\ucdb0\uc57c \ud55c\ub2e4.",
                "normalized_text": "\uc8fc\ucc28 \uad6c\ud68d\uc120 \ud06c\uae30\ub294 \uae30\uc900\uc5d0 \ub9de\ucdb0\uc57c \ud55c\ub2e4.",
                "raw_payload_hash": "f" * 64,
                "bbox": [10.0, 180.0, 500.0, 210.0],
                "parser_order": 4,
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


def test_grouped_korean_variants_recover_entity_and_numeric_evidence(
    tmp_path: Path,
) -> None:
    with _store(tmp_path) as store:
        bundle = build_evidence_bundle(
            store.require_connection(),
            {
                "question": "청소년 문화의집은 면적이 1500제곱미터 이상이어야 한다.",
                "synonym_manifest": {},
                "expansions": [],
                "limit": 20,
            },
        )

    hits = {hit["evidence_id"]: hit for hit in bundle["hits"]}
    assert {"E-CULTURE-HOUSE", "E-YOUTH-CENTER-1500"} <= set(hits)
    assert bundle["query"]["derived_variants"] == {
        "entity": ["청소년 문화의집", "청소년문화의집"],
        "numeric": ["1500", "1,500", "1500제곱미터", "1,500제곱미터"],
        "concept": ["면적", "연면적", "연건축면적", "이상"],
    }

    culture_channels = {
        item["channel"] for item in hits["E-CULTURE-HOUSE"]["channel_scores"]
    }
    criterion_channels = {
        item["channel"] for item in hits["E-YOUTH-CENTER-1500"]["channel_scores"]
    }
    assert "fts_entity" in culture_channels
    assert {"fts_numeric", "fts_concept"} <= criterion_channels
    assert all(
        item["channel"] != "fts_token_or"
        for hit in hits.values()
        for item in hit["channel_scores"]
    )


def test_reported_korean_compound_present_in_authority_is_retrievable(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        connection = store.require_connection()
        row = connection.execute(
            "SELECT evidence_id, normalized_text FROM retrieval_records "
            "WHERE evidence_id = 'E-PARKING-LINE'"
        ).fetchone()
        assert row is not None

        hits = search_fts_phrase(connection, "\uc8fc\ucc28\uad6c\ud68d\uc120")
        token_hits = search_fts_token_and(connection, "\uc8fc\ucc28\uad6c\ud68d\uc120")

    assert "\uc8fc\ucc28" in row["normalized_text"]
    assert {hit.evidence_id for hit in (*hits, *token_hits)} == {"E-PARKING-LINE"}
