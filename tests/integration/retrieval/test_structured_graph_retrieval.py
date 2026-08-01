from pathlib import Path

import pytest

from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.store import EvidenceStore
from ansim_review.retrieval.graph import traverse_relations
from ansim_review.retrieval.index import build_fts_index
from ansim_review.retrieval.structured import (
    retrieve_clause_ids,
    retrieve_structured,
)


def _snapshot() -> EvidenceSnapshot:
    elements = []
    records = (
        (
            "E-CLAUSE",
            "clause",
            "주 기준 조항",
            [10, 20, 200, 40],
        ),
        (
            "E-EXCEPTION",
            "exception",
            "예외 조항",
            [10, 50, 200, 70],
        ),
    )
    for index, (evidence_id, kind, text, bbox) in enumerate(records):
        elements.append(
            {
                "id": evidence_id,
                "revision_id": "LAW1-REV1",
                "page_id": "LAW1-P1",
                "page_number": 1,
                "element_type": kind,
                "raw_json": {"text": text},
                "raw_text": text,
                "normalized_text": text,
                "raw_payload_hash": chr(98 + index) * 64,
                "bbox": bbox,
                "parser_order": index,
            }
        )
    return EvidenceSnapshot(
        documents=({"id": "LAW1", "title": "안심주택 기준"},),
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
        elements=tuple(elements),
        tables=(
            {
                "id": "TBL-1",
                "revision_id": "LAW1-REV1",
                "page_number": 1,
                "bbox": [220, 20, 400, 100],
                "raw_json": {"rows": [["기준", "값"]]},
                "normalized_json": {"rows": [["기준", "값"]]},
            },
        ),
        visuals=(
            {
                "id": "VIS-1",
                "revision_id": "LAW1-REV1",
                "page_number": 1,
                "kind": "diagram",
                "relative_path": "visuals/diagram.png",
                "sha256": "d" * 64,
                "bbox": [220, 120, 400, 260],
                "duplicate_group": "DG-1",
            },
        ),
        links=(
            {
                "id": "L1",
                "source_id": "E-CLAUSE",
                "target_id": "E-EXCEPTION",
                "relation_type": "exception",
            },
            {
                "id": "L2",
                "source_id": "E-CLAUSE",
                "target_id": "TBL-1",
                "relation_type": "table",
            },
            {
                "id": "L3",
                "source_id": "E-CLAUSE",
                "target_id": "VIS-1",
                "relation_type": "visual",
            },
        ),
    )


def test_structured_and_graph_retrieval_are_stable(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence.sqlite"
    with EvidenceStore(db_path, create=True) as store:
        ingest_snapshot(store, _snapshot())
        build_fts_index(store.require_connection())
        exact = retrieve_structured(
            store.require_connection(),
            {"document_id": "LAW1", "page_number": 1},
        )
        clause = retrieve_clause_ids(
            store.require_connection(),
            ("E-CLAUSE",),
        )
        linked = traverse_relations(
            store.require_connection(),
            ("E-CLAUSE",),
            depth=1,
        )

    assert [hit.evidence_id for hit in exact] == [
        "E-CLAUSE",
        "E-EXCEPTION",
        "TBL-1",
        "VIS-1",
    ]
    assert clause[0].channel_scores[0].channel == "clause_id"
    assert [hit.evidence_id for hit in linked] == [
        "E-EXCEPTION",
        "TBL-1",
        "VIS-1",
    ]
    assert [hit.channel_scores[0].channel for hit in linked] == [
        "clause_id",
        "linked_visual_table",
        "linked_visual_table",
    ]


def test_graph_depth_is_bounded(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence.sqlite"
    with EvidenceStore(db_path, create=True) as store:
        ingest_snapshot(store, _snapshot())
        build_fts_index(store.require_connection())
        with pytest.raises(ValueError, match="depth must be between 0 and 3"):
            traverse_relations(
                store.require_connection(),
                ("E-CLAUSE",),
                depth=4,
            )
