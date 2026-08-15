from __future__ import annotations

import hashlib
from pathlib import Path

from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.bundle import build_evidence_bundle
from evidence_review.retrieval.index import build_fts_index, search_fts_token_prefix_and


def _snapshot() -> EvidenceSnapshot:
    text = "에어컨 설치기준은 실내기 위치, 배관 공간, 전원 조건을 함께 확인하도록 정한다."
    return EvidenceSnapshot(
        documents=({"id": "DOC1", "title": "가전제품 기준"},),
        revisions=(
            {
                "id": "REV1",
                "document_id": "DOC1",
                "source_hash": "a" * 64,
                "byte_size": 10,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": "REV1-P1",
                "revision_id": "REV1",
                "page_number": 1,
                "width": 595.0,
                "height": 842.0,
            },
        ),
        elements=(
            {
                "id": "E-AIRCON-INSTALL",
                "revision_id": "REV1",
                "page_id": "REV1-P1",
                "page_number": 1,
                "element_type": "clause",
                "raw_json": {"text": text},
                "raw_text": text,
                "normalized_text": text,
                "raw_payload_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "bbox": [10.0, 10.0, 500.0, 30.0],
                "parser_order": 0,
            },
        ),
    )


def test_planned_query_recovers_korean_suffix_tokens_with_lineage(tmp_path: Path) -> None:
    database = tmp_path / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(store, _snapshot())
        connection = store.require_connection()
        build_fts_index(connection)

        prefix_hits = search_fts_token_prefix_and(connection, "에어컨 설치기준")
        bundle = build_evidence_bundle(
            connection,
            {
                "question": "에어컨 등 가전제품 설치기준 알려줘",
                "expansions": [
                    {
                        "text": "에어컨 설치기준",
                        "origin": "llm",
                        "search_request_ids": ["S1"],
                        "issue_ids": ["I1"],
                    }
                ],
                "synonym_manifest": {},
                "filters": {},
                "clause_ids": [],
                "seed_ids": [],
                "graph_depth": 1,
                "limit": 20,
            },
        )

    assert [hit.evidence_id for hit in prefix_hits] == ["E-AIRCON-INSTALL"]
    hit = next(item for item in bundle["hits"] if item["evidence_id"] == "E-AIRCON-INSTALL")
    assert "fts_token_prefix_and" in {item["channel"] for item in hit["channel_scores"]}
    assert hit["matches"] == [
        {
            "search_request_id": "S1",
            "issue_ids": ["I1"],
            "query_text": "에어컨 설치기준",
            "origin": "llm",
        }
    ]
