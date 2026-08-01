import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.store import EvidenceStore
from ansim_review.retrieval.index import build_fts_index


def _build_db(path: Path) -> str:
    snapshot = EvidenceSnapshot(
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
                "id": "E1",
                "revision_id": "LAW1-REV1",
                "page_id": "LAW1-P1",
                "page_number": 1,
                "element_type": "clause",
                "raw_json": {"text": "이면도로 차량 진출입"},
                "raw_text": "이면도로 차량 진출입",
                "normalized_text": "이면도로 차량 진출입",
                "raw_payload_hash": "b" * 64,
                "bbox": [10, 20, 200, 50],
                "parser_order": 0,
            },
        ),
    )
    with EvidenceStore(path) as store:
        snapshot_hash = ingest_snapshot(store, snapshot)
        build_fts_index(store.require_connection())
    return snapshot_hash


def _run(
    db: Path,
    request: Path,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[3] / "src")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ansim_review",
            "query",
            "--db",
            str(db),
            "--request",
            str(request),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_query_cli_exports_traceable_evidence_bundle(
    tmp_path: Path,
) -> None:
    db = tmp_path / "evidence.sqlite"
    snapshot_hash = _build_db(db)
    request = tmp_path / "question.json"
    request.write_text(
        json.dumps(
            {
                "question": "이면도로 차량 진출입",
                "expansions": [
                    {"text": "차량 출입", "origin": "llm"}
                ],
                "synonym_manifest": {
                    "이면도로 차량 진출입": [
                        "후면도로 차량 진출입"
                    ]
                },
                "filters": {"document_id": "LAW1"},
                "clause_ids": ["E1"],
                "seed_ids": [],
                "graph_depth": 1,
                "limit": 10,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output1 = tmp_path / "retrieved-1.json"
    output2 = tmp_path / "retrieved-2.json"

    first = _run(db, request, output1)
    second = _run(db, request, output2)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert output1.read_bytes() == output2.read_bytes()
    payload = json.loads(output1.read_text(encoding="utf-8"))
    assert payload["snapshot_hash"] == snapshot_hash
    assert [
        term["origin"] for term in payload["query"]["terms"]
    ] == [
        "primary",
        "approved_synonym",
        "llm",
    ]
    assert payload["hits"]
    for hit in payload["hits"]:
        assert hit["channel_scores"]
        assert hit["citation"]["evidence_id"] == hit["evidence_id"]
        assert hit["citation"]["page_number"] == 1
        assert len(hit["citation"]["source_hash"]) == 64


def test_query_cli_refuses_stale_index(tmp_path: Path) -> None:
    db = tmp_path / "evidence.sqlite"
    _build_db(db)
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE snapshot_meta SET value = ? "
            "WHERE key = 'snapshot_hash'",
            ("f" * 64,),
        )
        connection.commit()
    request = tmp_path / "question.json"
    request.write_text(
        json.dumps(
            {
                "question": "이면도로",
                "expansions": [],
                "synonym_manifest": {},
                "filters": {},
                "clause_ids": [],
                "seed_ids": [],
                "graph_depth": 1,
                "limit": 10,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "retrieved.json"

    result = _run(db, request, output)

    assert result.returncode == 2
    assert "snapshot hash mismatch" in result.stderr
    assert not output.exists()
