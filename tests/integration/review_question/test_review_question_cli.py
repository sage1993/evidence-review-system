from __future__ import annotations

import json
from pathlib import Path

from ansim_review import cli
from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.store import EvidenceStore
from ansim_review.retrieval.index import build_fts_index


def _workspace(path: Path) -> Path:
    (path / "evidence").mkdir(parents=True)
    with EvidenceStore(path / "evidence" / "evidence.sqlite", create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC1", "title": "주차장 조례"},),
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
                        "width": 10.0,
                        "height": 10.0,
                    },
                ),
                elements=(
                    {
                        "id": "E1",
                        "revision_id": "REV1",
                        "page_id": "REV1-P1",
                        "page_number": 1,
                        "element_type": "clause",
                        "raw_json": {"text": "주차장은 별표 2에 따른다."},
                        "raw_text": "주차장은 별표 2에 따른다.",
                        "normalized_text": "주차장은 별표 2에 따른다.",
                        "raw_payload_hash": "b" * 64,
                        "bbox": [0, 0, 10, 10],
                        "parser_order": 0,
                    },
                ),
            ),
        )
        build_fts_index(store.require_connection())
    return path


def test_review_question_prepare_hides_question_and_evidence_from_stdout(
    capsys,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")

    assert cli.main(
        [
            "review-question",
            "prepare",
            "--workspace",
            str(workspace),
            "--question",
            "주차장 설치 기준",
            "--expansion",
            "별표 2",
        ]
    ) == 0

    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "WAITING_TRACK_A"
    assert document["resumed"] is False
    assert "주차장 설치 기준" not in json.dumps(document, ensure_ascii=False)
    action = json.loads(Path(document["next_action_path"]).read_text(encoding="utf-8"))
    assert action["action"] == "PRODUCE_TRACK_A"


def test_review_question_prepare_resumes_the_same_immutable_request(
    capsys,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    arguments = [
        "review-question",
        "prepare",
        "--workspace",
        str(workspace),
        "--question",
        "주차장 설치 기준",
    ]

    assert cli.main(arguments) == 0
    first = json.loads(capsys.readouterr().out)
    assert cli.main(arguments) == 0
    second = json.loads(capsys.readouterr().out)

    assert second["run_id"] == first["run_id"]
    assert second["resumed"] is True
