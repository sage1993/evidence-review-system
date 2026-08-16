from __future__ import annotations

from pathlib import Path

from evidence_review.evidence.clause_rebuild import ensure_clause_index
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.graph import traverse_relations_with_provenance
from evidence_review.retrieval.index import build_fts_index


def _document(
    doc_id: str,
    title: str,
    revision_id: str,
    page_id: str,
    text: str,
):
    return (
        {"id": doc_id, "title": title},
        {
            "id": revision_id,
            "document_id": doc_id,
            "source_hash": ("a" if doc_id == "DOC-SOURCE" else "b") * 64,
            "byte_size": 100,
            "page_count": 1,
        },
        {
            "id": page_id,
            "revision_id": revision_id,
            "page_number": 1,
            "width": 595.0,
            "height": 842.0,
        },
        {
            "id": f"E-{doc_id}",
            "revision_id": revision_id,
            "page_id": page_id,
            "page_number": 1,
            "element_type": "paragraph",
            "raw_json": {"text": text},
            "raw_text": text,
            "normalized_text": text,
            "raw_payload_hash": ("c" if doc_id == "DOC-SOURCE" else "d") * 64,
            "bbox": [10.0, 10.0, 550.0, 40.0],
            "parser_order": 0,
        },
    )


def _snapshot(
    *,
    source_text: str,
    target_title: str | None = None,
    target_text: str | None = None,
) -> EvidenceSnapshot:
    source = _document(
        "DOC-SOURCE",
        "안심주택 조례",
        "REV-SOURCE",
        "P-SOURCE",
        source_text,
    )
    values = [source]
    if target_title is not None and target_text is not None:
        values.append(
            _document(
                "DOC-TARGET",
                target_title,
                "REV-TARGET",
                "P-TARGET",
                target_text,
            )
        )
    return EvidenceSnapshot(
        documents=tuple(value[0] for value in values),
        revisions=tuple(value[1] for value in values),
        pages=tuple(value[2] for value in values),
        elements=tuple(value[3] for value in values),
    )


def _article_source() -> str:
    return (
        "제13조(주차장 설치기준 완화) ① 「주택건설기준 등에 관한 규정」 "
        "제27조에 따라 주차장을 설치하여야 한다."
    )


def test_missing_external_authority_is_source_gap_not_generic_missing_target(
    tmp_path: Path,
) -> None:
    with EvidenceStore(tmp_path / "missing.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot(source_text=_article_source()))
        connection = store.require_connection()
        build_fts_index(connection)
        ensure_clause_index(connection)

        result = traverse_relations_with_provenance(
            connection,
            ("E-DOC-SOURCE",),
            depth=1,
        )

    assert result.hits == ()
    assert len(result.missing) == 1
    assert result.missing[0].reason_code == "SOURCE_NOT_INGESTED"


def test_ingested_external_authority_resolves_to_citation_grade_target(
    tmp_path: Path,
) -> None:
    with EvidenceStore(tmp_path / "resolved.sqlite", create=True) as store:
        ingest_snapshot(
            store,
            _snapshot(
                source_text=_article_source(),
                target_title="주택건설기준 등에 관한 규정",
                target_text="제27조(주차장) 주택의 주차장 설치기준을 정한다.",
            ),
        )
        connection = store.require_connection()
        build_fts_index(connection)
        ensure_clause_index(connection)

        result = traverse_relations_with_provenance(
            connection,
            ("E-DOC-SOURCE",),
            depth=1,
        )

    assert {hit.evidence_id for hit in result.hits} == {"E-DOC-TARGET"}
    assert result.missing == ()
    assert result.paths[0].steps[0].relation_type == "rule_source"


def test_specific_annex_reference_does_not_fall_back_to_article_only(
    tmp_path: Path,
) -> None:
    source_text = (
        "제13조(주차장 설치기준 완화) ② 「서울특별시 주차장 설치 및 관리 조례」 "
        "제20조제1항 별표 2에 따라 주차장을 설치하여야 한다."
    )
    with EvidenceStore(tmp_path / "annex-missing.sqlite", create=True) as store:
        ingest_snapshot(
            store,
            _snapshot(
                source_text=source_text,
                target_title="서울특별시 주차장 설치 및 관리 조례",
                target_text="제20조(부설주차장) 제1항 일반적인 설치 원칙을 정한다.",
            ),
        )
        connection = store.require_connection()
        build_fts_index(connection)
        ensure_clause_index(connection)

        result = traverse_relations_with_provenance(
            connection,
            ("E-DOC-SOURCE",),
            depth=1,
        )

    assert result.hits == ()
    assert len(result.missing) == 1
    assert result.missing[0].reason_code == "REFERENCE_TARGET_MISSING"
