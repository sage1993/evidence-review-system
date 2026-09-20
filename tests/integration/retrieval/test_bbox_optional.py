import sqlite3
from pathlib import Path

import pytest

from evidence_review.canonical_json import dumps
from evidence_review.retrieval.index import build_fts_index, search_fts

SCHEMA = Path("src/evidence_review/evidence/schema.sql")


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    connection.execute("INSERT INTO documents(id, title) VALUES(?, ?)", ("DOC1", "Test"))
    connection.execute(
        """
        INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
        VALUES(?, ?, ?, ?, ?)
        """,
        ("REV1", "DOC1", "a" * 64, 1, 1),
    )
    connection.execute(
        """
        INSERT INTO pages(id, revision_id, page_number, width, height)
        VALUES(?, ?, ?, ?, ?)
        """,
        ("PAGE1", "REV1", 1, 595.0, 842.0),
    )
    connection.execute(
        "INSERT INTO snapshot_meta(key, value) VALUES('snapshot_hash', ?)",
        ("b" * 64,),
    )
    connection.commit()
    return connection


def _insert_element(
    connection: sqlite3.Connection,
    *,
    evidence_id: str,
    text: str,
    bbox: list[float] | None,
) -> None:
    connection.execute(
        """
        INSERT INTO elements(
            id, page_id, element_type, raw_json, raw_text, normalized_text,
            raw_payload_hash, bbox_json, parser_order
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence_id,
            "PAGE1",
            "clause",
            dumps({"text": text}),
            text,
            text,
            "c" * 64,
            None if bbox is None else dumps(bbox),
            0,
        ),
    )
    connection.commit()


def _insert_table(
    connection: sqlite3.Connection,
    *,
    evidence_id: str,
    text: str,
    bbox: list[float] | None,
) -> None:
    connection.execute(
        """
        INSERT INTO tables(id, page_id, bbox_json, raw_json, normalized_json)
        VALUES(?, ?, ?, ?, ?)
        """,
        (
            evidence_id,
            "PAGE1",
            None if bbox is None else dumps(bbox),
            dumps({"text": text}),
            dumps({"text": text}),
        ),
    )
    connection.commit()


def _insert_structured_table(
    connection: sqlite3.Connection,
    *,
    evidence_id: str,
    normalized: dict[str, object] | None,
) -> None:
    connection.execute(
        """
        INSERT INTO tables(id, page_id, bbox_json, raw_json, normalized_json)
        VALUES(?, 'PAGE1', ?, ?, ?)
        """,
        (
            evidence_id,
            dumps([10.0, 20.0, 200.0, 100.0]),
            dumps(
                {
                    "type": "table",
                    "rows": [
                        {
                            "row number": 1,
                            "cells": [
                                {
                                    "column number": 1,
                                    "kids": [{"content": "표 검색 근거"}],
                                }
                            ],
                        }
                    ],
                }
            ),
            None if normalized is None else dumps(normalized),
        ),
    )
    connection.commit()


def _insert_visual(
    connection: sqlite3.Connection,
    *,
    evidence_id: str,
    kind: str,
    bbox: list[float] | None,
) -> None:
    connection.execute(
        """
        INSERT INTO visuals(
            id, page_id, kind, relative_path, sha256, bbox_json, duplicate_group
        ) VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence_id,
            "PAGE1",
            kind,
            f"visuals/{evidence_id}.png",
            "d" * 64,
            None if bbox is None else dumps(bbox),
            f"group-{evidence_id}",
        ),
    )
    connection.commit()


def test_bboxless_element_is_lexically_retrievable() -> None:
    connection = _connection()
    try:
        _insert_element(
            connection,
            evidence_id="E-PAGE",
            text="bboxlessneedle",
            bbox=None,
        )
        build_fts_index(connection)

        hits = search_fts(connection, "bboxlessneedle")

        assert [hit.evidence_id for hit in hits] == ["E-PAGE"]
        assert hits[0].page_number == 1
        assert hits[0].bbox is None
    finally:
        connection.close()


def test_bboxless_table_is_lexically_retrievable() -> None:
    connection = _connection()
    try:
        _insert_table(
            connection,
            evidence_id="T-PAGE",
            text="bboxlesstable",
            bbox=None,
        )
        build_fts_index(connection)

        hits = search_fts(connection, "bboxlesstable")

        assert [hit.evidence_id for hit in hits] == ["T-PAGE"]
        assert hits[0].evidence_type == "table"
        assert hits[0].bbox is None
    finally:
        connection.close()


def test_structured_table_with_text_requires_searchable_projection() -> None:
    connection = _connection()
    try:
        _insert_structured_table(connection, evidence_id="T-QUALITY", normalized=None)

        with pytest.raises(RuntimeError, match="TABLE_SEARCH_TEXT_MISSING"):
            build_fts_index(connection)
    finally:
        connection.close()


def test_structured_table_search_uses_row_aware_projection() -> None:
    connection = _connection()
    try:
        _insert_structured_table(
            connection,
            evidence_id="T-QUALITY",
            normalized={"search_text": "행 1 열 1: 표 검색 근거"},
        )
        build_fts_index(connection)

        hits = search_fts(connection, "표 검색 근거")

        assert [hit.evidence_id for hit in hits] == ["T-QUALITY"]
        assert hits[0].text == "행 1 열 1: 표 검색 근거"
    finally:
        connection.close()


def test_bboxless_visual_is_lexically_retrievable() -> None:
    connection = _connection()
    try:
        _insert_visual(
            connection,
            evidence_id="V-PAGE",
            kind="bboxlessvisual",
            bbox=None,
        )
        build_fts_index(connection)

        hits = search_fts(connection, "bboxlessvisual")

        assert [hit.evidence_id for hit in hits] == ["V-PAGE"]
        assert hits[0].evidence_type == "visual"
        assert hits[0].bbox is None
    finally:
        connection.close()


def test_page_only_hit_has_explicit_quality_and_refuses_exact_citation() -> None:
    connection = _connection()
    try:
        _insert_element(
            connection,
            evidence_id="E-PAGE",
            text="pageonlycitation",
            bbox=None,
        )
        build_fts_index(connection)
        hit = search_fts(connection, "pageonlycitation")[0]

        assert hit.citation_quality.value == "PAGE_ONLY"
        with pytest.raises(RuntimeError, match="BBOX_UNAVAILABLE"):
            hit.citation()
    finally:
        connection.close()


def test_bbox_present_cases_remain_exact_for_all_evidence_types() -> None:
    connection = _connection()
    try:
        bbox = [10.0, 20.0, 200.0, 50.0]
        _insert_element(connection, evidence_id="E-EXACT", text="exactelement", bbox=bbox)
        _insert_table(connection, evidence_id="T-EXACT", text="exacttable", bbox=bbox)
        _insert_visual(connection, evidence_id="V-EXACT", kind="exactvisual", bbox=bbox)
        build_fts_index(connection)

        for query, expected_id in (
            ("exactelement", "E-EXACT"),
            ("exacttable", "T-EXACT"),
            ("exactvisual", "V-EXACT"),
        ):
            hit = search_fts(connection, query)[0]
            assert hit.evidence_id == expected_id
            assert hit.citation_quality.value == "EXACT_BBOX"
            assert hit.bbox is not None
            assert [hit.bbox.left, hit.bbox.bottom, hit.bbox.right, hit.bbox.top] == bbox
            citation = hit.citation()
            assert citation.bbox == hit.bbox
    finally:
        connection.close()


def test_bboxless_ordering_is_deterministic_across_rebuilds() -> None:
    connection = _connection()
    try:
        _insert_element(connection, evidence_id="E2", text="sameneedle", bbox=None)
        _insert_element(connection, evidence_id="E1", text="sameneedle", bbox=None)

        build_fts_index(connection)
        first = search_fts(connection, "sameneedle")
        second = search_fts(connection, "sameneedle")
        build_fts_index(connection)
        rebuilt = search_fts(connection, "sameneedle")

        assert [hit.evidence_id for hit in first] == ["E1", "E2"]
        assert [hit.evidence_id for hit in second] == ["E1", "E2"]
        assert [hit.evidence_id for hit in rebuilt] == ["E1", "E2"]
        assert [hit.channel_scores for hit in first] == [hit.channel_scores for hit in rebuilt]
    finally:
        connection.close()


def test_malformed_bbox_is_not_silently_downgraded_to_page_only() -> None:
    connection = _connection()
    try:
        _insert_element(
            connection,
            evidence_id="E-BAD",
            text="malformedneedle",
            bbox=[10.0, 20.0],
        )
        build_fts_index(connection)

        assert search_fts(connection, "malformedneedle") == ()
    finally:
        connection.close()
