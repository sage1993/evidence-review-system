from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evidence_review import cli
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.index import build_fts_index


def _workspace(path: Path) -> Path:
    evidence_directory = path / "evidence"
    evidence_directory.mkdir(parents=True)
    text = "에어컨 실외기 설치는 환기와 유지관리 공간을 확보할 수 있는 위치를 검토한다."
    with EvidenceStore(evidence_directory / "evidence.sqlite", create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC1", "title": "Synthetic installation criteria"},),
                revisions=(
                    {
                        "id": "REV1",
                        "document_id": "DOC1",
                        "source_hash": hashlib.sha256(b"question-planner-cli").hexdigest(),
                        "byte_size": len(text.encode("utf-8")),
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
                        "id": "E1",
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
            ),
        )
        build_fts_index(store.require_connection())
    return path


def test_cli_main_runs_prepare_plan_then_validated_plan_retrieval(
    capsys,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    question = "에어컨 등 가전제품 설치기준 알려줘"

    assert cli.main(
        [
            "review-question",
            "prepare-plan",
            "--workspace",
            str(workspace),
            "--question",
            question,
        ]
    ) == 0
    prepared_plan = json.loads(capsys.readouterr().out)
    assert prepared_plan["status"] == "WAITING_QUESTION_PLAN"

    output_path = Path(prepared_plan["expected_output"])
    output_path.write_text(
        json.dumps(
            {
                "format": "evidence-review/question-plan",
                "version": 1,
                "original_question": question,
                "facts": [],
                "assumptions": [],
                "issues": [
                    {
                        "id": "I1",
                        "question": "에어컨 실외기 설치조건은 무엇인가",
                        "depends_on": [],
                    }
                ],
                "legal_anchors": [],
                "search_requests": [
                    {
                        "id": "S1",
                        "issue_ids": ["I1"],
                        "text": "에어컨 실외기 설치",
                        "kind": "phrase",
                        "source": "planner",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert cli.main(
        [
            "review-question",
            "prepare",
            "--workspace",
            str(workspace),
            "--question",
            question,
            "--question-plan-output",
            str(output_path),
        ]
    ) == 0
    prepared_review = json.loads(capsys.readouterr().out)

    assert prepared_review["status"] == "WAITING_TRACK_A"
    run_directory = workspace / "runs" / prepared_review["run_id"]
    assert (run_directory / "question-plan.json").is_file()
    assert (run_directory / "evidence-query.json").is_file()
    assert (run_directory / "track-a-bundle.json").is_file()

    evidence_query = json.loads((run_directory / "evidence-query.json").read_text(encoding="utf-8"))
    assert [hit["evidence_id"] for hit in evidence_query["hits"]] == ["E1"]
    assert evidence_query["hits"][0]["matches"] == [
        {
            "search_request_id": "S1",
            "issue_ids": ["I1"],
            "query_text": "에어컨 실외기 설치",
            "origin": "llm",
        }
    ]
