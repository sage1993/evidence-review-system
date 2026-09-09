from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evidence_review.contracts.question_plan import QuestionPlan, decode_question_plan
from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.planned_review_question import prepare_planned_review_question
from evidence_review.review_question import (
    submit_question_track_a,
    submit_question_track_b,
)


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
        finalize_evidence_database(store)
    return path


def _partial_plan(question: str) -> QuestionPlan:
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 1,
            "original_question": question,
            "facts": [],
            "assumptions": [],
            "issues": [
                {
                    "id": "I1",
                    "question": "주차장 설치 기준은 무엇인가",
                    "depends_on": [],
                },
                {
                    "id": "I2",
                    "question": "존재하지 않는 보조 기준은 무엇인가",
                    "depends_on": [],
                },
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S1",
                    "issue_ids": ["I1"],
                    "text": "주차장",
                    "kind": "phrase",
                    "source": "planner",
                },
                {
                    "id": "S2",
                    "issue_ids": ["I2"],
                    "text": "존재하지 않는 보조 기준",
                    "kind": "phrase",
                    "source": "planner",
                },
            ],
        },
        question,
    )


def _track_a(run_directory: Path) -> Path:
    bundle = json.loads(
        (run_directory / "track-a-bundle.json").read_text(encoding="utf-8")
    )
    citation_id = bundle["evidence"][0]["citation"]["citation_id"]
    output = run_directory / "external-track-a.json"
    output.write_text(
        json.dumps(
            {
                "run_id": bundle["run_id"],
                "claims": [
                    {
                        "claim_id": "CL-I1",
                        "text": "주차장은 별표 2에 따른다.",
                        "citation_ids": [citation_id],
                        "numeric_tokens": ["2"],
                        "issue_ids": ["I1"],
                        "calculation_result_ids": [],
                        "rule_references": [],
                    }
                ],
                "citations": [citation_id],
                "missing_inputs": ["I2: 관련 근거가 검색되지 않음"],
                "exceptions": [],
                "conflicts": [],
                "explanation": "I1은 근거가 있고 I2는 추가 근거가 필요하다.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return output


def _track_b(run_directory: Path) -> Path:
    output = run_directory / "external-track-b.json"
    output.write_text(
        json.dumps(
            {
                "run_id": run_directory.name,
                "claim_audits": [
                    {
                        "claim_id": "CL-I1",
                        "disposition": "ACCEPT",
                        "finding_codes": [],
                        "notes": "",
                    }
                ],
                "overall_disposition": "ACCEPT",
            }
        ),
        encoding="utf-8",
    )
    return output


def _page_assets(workspace: Path) -> None:
    directory = workspace / "page-images" / "REV1"
    directory.mkdir(parents=True)
    image = b"\x89PNG\r\n\x1a\nreview-question"
    (directory / "page-0001.png").write_bytes(image)
    (directory / "page-0001.json").write_text(
        json.dumps(
            {
                "format": "ansim/page-image",
                "version": 1,
                "revision_id": "REV1",
                "page_number": 1,
                "source_hash": "a" * 64,
                "pdf_width": 10.0,
                "pdf_height": 10.0,
                "image_sha256": hashlib.sha256(image).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


def test_partially_resolved_track_b_retry_is_terminal_and_idempotent(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    question = "주차장 설치 기준과 존재하지 않는 보조 기준"
    prepared = prepare_planned_review_question(workspace, _partial_plan(question))
    run_directory = workspace / "runs" / prepared.run_id
    _page_assets(workspace)

    submit_question_track_a(workspace, prepared.run_id, _track_a(run_directory))
    track_b = _track_b(run_directory)
    finalized = submit_question_track_b(
        workspace,
        prepared.run_id,
        track_b,
        publish=True,
    )
    assert finalized.packet.status == "PARTIALLY_RESOLVED"

    packet_path = run_directory / "final-review-packet.json"
    assert finalized.published_packet == packet_path
    events_directory = run_directory / "events"
    before_packet = packet_path.read_bytes()
    before_events = tuple(sorted(path.name for path in events_directory.iterdir()))

    retried = submit_question_track_b(
        workspace,
        prepared.run_id,
        track_b,
        publish=True,
    )

    assert retried.packet.status == "PARTIALLY_RESOLVED"
    assert retried.published_packet == packet_path
    assert packet_path.read_bytes() == before_packet
    assert tuple(sorted(path.name for path in events_directory.iterdir())) == before_events
