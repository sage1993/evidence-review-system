from pathlib import Path

from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.graph import traverse_relations_with_provenance
from evidence_review.retrieval.index import build_fts_index


def _element(evidence_id: str, revision_id: str, page_id: str, order: int) -> dict[str, object]:
    return {
        "id": evidence_id,
        "revision_id": revision_id,
        "page_id": page_id,
        "page_number": 1,
        "element_type": "clause",
        "raw_json": {"text": evidence_id},
        "raw_text": evidence_id,
        "normalized_text": evidence_id,
        "raw_payload_hash": f"{order + 1:064x}",
        "bbox": [10, 10 + order * 10, 200, 18 + order * 10],
        "parser_order": order,
    }


def _snapshot() -> EvidenceSnapshot:
    documents = (
        {"id": "LAW-A", "title": "법령 A"},
        {"id": "LAW-B", "title": "법령 B"},
    )
    revisions = (
        {
            "id": "A-REV1",
            "document_id": "LAW-A",
            "source_hash": "a" * 64,
            "byte_size": 10,
            "page_count": 1,
        },
        {
            "id": "A-REV2",
            "document_id": "LAW-A",
            "source_hash": "b" * 64,
            "byte_size": 10,
            "page_count": 1,
        },
        {
            "id": "B-REV1",
            "document_id": "LAW-B",
            "source_hash": "c" * 64,
            "byte_size": 10,
            "page_count": 1,
        },
    )
    pages = (
        {"id": "A1-P1", "revision_id": "A-REV1", "page_number": 1, "width": 595.0, "height": 842.0},
        {"id": "A2-P1", "revision_id": "A-REV2", "page_number": 1, "width": 595.0, "height": 842.0},
        {"id": "B1-P1", "revision_id": "B-REV1", "page_number": 1, "width": 595.0, "height": 842.0},
    )
    elements = (
        _element("SEED", "A-REV2", "A2-P1", 0),
        _element("A1", "A-REV2", "A2-P1", 1),
        _element("A2", "A-REV2", "A2-P1", 2),
        _element("A3", "A-REV2", "A2-P1", 3),
        _element("A4", "A-REV2", "A2-P1", 4),
        _element("STALE", "A-REV1", "A1-P1", 5),
        _element("CROSS", "B-REV1", "B1-P1", 6),
    )
    links = (
        {"id": "L1", "source_id": "SEED", "target_id": "A1", "relation_type": "exception"},
        {"id": "L2", "source_id": "SEED", "target_id": "A2", "relation_type": "parent"},
        {"id": "L3", "source_id": "SEED", "target_id": "A3", "relation_type": "cited_clause"},
        {"id": "L4", "source_id": "SEED", "target_id": "A4", "relation_type": "rule_source"},
        {"id": "L5", "source_id": "SEED", "target_id": "STALE", "relation_type": "cited_clause"},
        {"id": "L6", "source_id": "SEED", "target_id": "CROSS", "relation_type": "cited_clause"},
        {"id": "L7", "source_id": "SEED", "target_id": "MISSING", "relation_type": "cited_clause"},
        {"id": "L8", "source_id": "A1", "target_id": "SEED", "relation_type": "parent"},
        {"id": "L9", "source_id": "A1", "target_id": "A3", "relation_type": "cited_clause"},
    )
    return EvidenceSnapshot(
        documents=documents,
        revisions=revisions,
        pages=pages,
        elements=elements,
        links=links,
    )


def test_reference_traversal_enforces_fanout_and_node_budgets(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence.sqlite"
    with EvidenceStore(db_path, create=True) as store:
        ingest_snapshot(store, _snapshot())
        build_fts_index(store.require_connection())
        result = traverse_relations_with_provenance(
            store.require_connection(),
            ("SEED",),
            depth=2,
            max_nodes=2,
            max_fanout=3,
        )

    assert [hit.evidence_id for hit in result.hits] == ["A1", "A2"]
    assert [path.target_id for path in result.paths] == ["A1", "A2"]
    assert all(len(path.steps) == 1 for path in result.paths)


def test_reference_traversal_records_missing_and_filters_stale_same_document_revision(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "evidence.sqlite"
    with EvidenceStore(db_path, create=True) as store:
        ingest_snapshot(store, _snapshot())
        build_fts_index(store.require_connection())
        result = traverse_relations_with_provenance(
            store.require_connection(),
            ("SEED",),
            depth=1,
            max_nodes=12,
            max_fanout=10,
        )

    ids = {hit.evidence_id for hit in result.hits}
    assert "CROSS" in ids
    assert "STALE" not in ids
    missing = {(item.target_id, item.reason_code) for item in result.missing}
    assert ("MISSING", "REFERENCE_TARGET_MISSING") in missing
    assert ("STALE", "STALE_SAME_DOCUMENT_REVISION") in missing


def test_reference_traversal_is_cycle_safe_and_preserves_first_deterministic_path(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "evidence.sqlite"
    with EvidenceStore(db_path, create=True) as store:
        ingest_snapshot(store, _snapshot())
        build_fts_index(store.require_connection())
        result = traverse_relations_with_provenance(
            store.require_connection(),
            ("SEED",),
            depth=2,
            max_nodes=12,
            max_fanout=10,
        )

    ids = [hit.evidence_id for hit in result.hits]
    assert ids.count("A3") == 1
    assert "SEED" not in ids
    path_by_target = {path.target_id: path for path in result.paths}
    assert path_by_target["A3"].steps[0].source_id == "SEED"
    assert path_by_target["A3"].steps[0].target_id == "A3"
