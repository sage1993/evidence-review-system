from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.store import EvidenceStore
from ansim_review.retrieval.bundle import build_evidence_bundle
from ansim_review.retrieval.index import build_fts_index


def _element(
    evidence_id: str,
    *,
    revision_id: str,
    page_id: str,
    page_number: int,
    parser_order: int,
    text: str,
    payload_hash_char: str,
) -> dict[str, object]:
    return {
        "id": evidence_id,
        "revision_id": revision_id,
        "page_id": page_id,
        "page_number": page_number,
        "element_type": "table_cell",
        "raw_json": {"text": text},
        "raw_text": text,
        "normalized_text": text,
        "raw_payload_hash": payload_hash_char * 64,
        "bbox": [10.0, float(parser_order), 500.0, float(parser_order + 1)],
        "parser_order": parser_order,
    }


def _snapshot() -> EvidenceSnapshot:
    return EvidenceSnapshot(
        documents=(
            {"id": "DOC1", "title": "청소년수련시설 기준"},
            {"id": "DOC2", "title": "다른 개정판"},
        ),
        revisions=(
            {
                "id": "REV1",
                "document_id": "DOC1",
                "source_hash": "a" * 64,
                "byte_size": 100,
                "page_count": 2,
            },
            {
                "id": "REV2",
                "document_id": "DOC2",
                "source_hash": "b" * 64,
                "byte_size": 50,
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
            {
                "id": "REV1-P2",
                "revision_id": "REV1",
                "page_number": 2,
                "width": 595.0,
                "height": 842.0,
            },
            {
                "id": "REV2-P1",
                "revision_id": "REV2",
                "page_number": 1,
                "width": 595.0,
                "height": 842.0,
            },
        ),
        elements=(
            _element(
                "E-ROW-LABEL",
                revision_id="REV1",
                page_id="REV1-P1",
                page_number=1,
                parser_order=10,
                text="청소년수련관",
                payload_hash_char="c",
            ),
            _element(
                "E-ROW-CRITERION",
                revision_id="REV1",
                page_id="REV1-P1",
                page_number=1,
                parser_order=11,
                text="연건축면적이 1,500제곱미터 이상이어야 하며 관련 기준을 따른다.",
                payload_hash_char="d",
            ),
            _element(
                "E-CULTURE-LABEL",
                revision_id="REV1",
                page_id="REV1-P1",
                page_number=1,
                parser_order=20,
                text="청소년문화의집",
                payload_hash_char="e",
            ),
            _element(
                "E-CULTURE-DESC",
                revision_id="REV1",
                page_id="REV1-P1",
                page_number=1,
                parser_order=21,
                text="다양한 유형의 청소년수련시설 중 가장 작은 규모의 시설이다.",
                payload_hash_char="f",
            ),
            _element(
                "E-PAGE2-GUARD",
                revision_id="REV1",
                page_id="REV1-P2",
                page_number=2,
                parser_order=21,
                text="다른 페이지의 인접 순서 요소이며 문맥으로 섞이면 안 된다.",
                payload_hash_char="1",
            ),
            _element(
                "E-REV2-GUARD",
                revision_id="REV2",
                page_id="REV2-P1",
                page_number=1,
                parser_order=21,
                text="다른 개정판의 인접 순서 요소이며 문맥으로 섞이면 안 된다.",
                payload_hash_char="2",
            ),
        ),
    )


@contextmanager
def _store(tmp_path: Path) -> Iterator[EvidenceStore]:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot())
        build_fts_index(store.require_connection())
        yield store


def test_real_question_returns_separately_cited_row_context_without_crossing_boundaries(
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
    expected = {
        "E-ROW-LABEL",
        "E-ROW-CRITERION",
        "E-CULTURE-LABEL",
        "E-CULTURE-DESC",
    }
    assert expected <= set(hits)
    assert "E-PAGE2-GUARD" not in hits
    assert "E-REV2-GUARD" not in hits

    for evidence_id in expected:
        citation = hits[evidence_id]["citation"]
        assert citation is not None
        assert citation["evidence_id"] == evidence_id

    assert "structural_context" in {
        score["channel"] for score in hits["E-ROW-LABEL"]["channel_scores"]
    }
    assert "structural_context" in {
        score["channel"] for score in hits["E-CULTURE-DESC"]["channel_scores"]
    }
