from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ansim_review import cli
from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.store import EvidenceStore
from ansim_review.retrieval.index import build_fts_index
from ansim_review.review_question import (
    _append_event,
    prepare_review_question,
    submit_question_track_a,
    submit_question_track_b,
)
from ansim_review.workflow.events import load_workflow_events


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


def _track_a(run_directory: Path) -> Path:
    bundle = json.loads((run_directory / "track-a-bundle.json").read_text(encoding="utf-8"))
    citation_id = bundle["evidence"][0]["citation"]["citation_id"]
    output = run_directory / "external-track-a.json"
    output.write_text(
        json.dumps(
            {
                "run_id": bundle["run_id"],
                "claims": [
                    {
                        "claim_id": "CL1",
                        "text": "주차장은 별표 2에 따른다.",
                        "citation_ids": [citation_id],
                        "numeric_tokens": ["2"],
                        "calculation_result_ids": [],
                        "rule_references": [],
                    }
                ],
                "citations": [citation_id],
                "missing_inputs": [],
                "exceptions": [],
                "conflicts": [],
                "explanation": "근거를 정리한다.",
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
                        "claim_id": "CL1",
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


def test_prepare_after_valid_track_a_resumes_track_b_without_regression(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / first.run_id

    submit_question_track_a(workspace, first.run_id, _track_a(run_directory))
    resumed = prepare_review_question(workspace, "주차장은 별표 2에 따른다")

    assert resumed.resumed is True
    assert resumed.status == "WAITING_TRACK_B"
    assert resumed.next_action_path == run_directory / "next-action-track-b.json"
    assert (run_directory / "next-action-track-a.json").is_file()
    assert load_workflow_events(run_directory / "events")[-1].next_state == "WAITING_TRACK_B"


def test_track_a_recovers_malformed_partial_submission(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / first.run_id
    (run_directory / "track-a-output.json").write_text("{partial", encoding="utf-8")
    (run_directory / "next-action-track-b.json").write_text("partial", encoding="utf-8")
    (run_directory / "track-a-validation.json").write_text("partial", encoding="utf-8")

    submitted = submit_question_track_a(workspace, first.run_id, _track_a(run_directory))

    assert submitted.next_action_path.is_file()
    assert load_workflow_events(run_directory / "events")[-1].next_state == "WAITING_TRACK_B"


def test_prepare_after_finalization_does_not_reopen_track_a(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / first.run_id
    _page_assets(workspace)
    submit_question_track_a(workspace, first.run_id, _track_a(run_directory))
    submit_question_track_b(workspace, first.run_id, _track_b(run_directory))

    resumed = prepare_review_question(workspace, "주차장은 별표 2에 따른다")

    assert resumed.resumed is True
    assert resumed.status == "READY_FOR_HUMAN_REVIEW"
    assert resumed.next_action_path is None
    assert [event.next_state for event in load_workflow_events(run_directory / "events")][-2:] == [
        "FINALIZING",
        "READY_FOR_REVIEW",
    ]


def test_prepare_completes_interrupted_finalization_from_valid_artifacts(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / first.run_id
    _page_assets(workspace)
    submit_question_track_a(workspace, first.run_id, _track_a(run_directory))
    track_b = _track_b(run_directory)
    _append_event(run_directory, "FINALIZING", hashlib.sha256(track_b.read_bytes()).hexdigest())
    from ansim_review.review_run import submit_track_b

    submit_track_b(workspace, first.run_id, track_b)

    resumed = prepare_review_question(workspace, "주차장은 별표 2에 따른다")

    assert resumed.status == "READY_FOR_HUMAN_REVIEW"
    assert resumed.next_action_path is None
    assert load_workflow_events(run_directory / "events")[-1].next_state == "READY_FOR_REVIEW"


def test_prepare_fails_closed_for_tampered_final_packet(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / first.run_id
    _page_assets(workspace)
    submit_question_track_a(workspace, first.run_id, _track_a(run_directory))
    track_b = _track_b(run_directory)
    submit_question_track_b(workspace, first.run_id, track_b)
    packet_path = run_directory / "final-review-packet.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["question"] = "변조된 질문"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    try:
        prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    except ValueError as error:
        assert "manifest-bound artifacts" in str(error)
    else:
        raise AssertionError("tampered final packet resumed")


def test_track_b_recovers_partial_html_while_finalizing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / first.run_id
    _page_assets(workspace)
    submit_question_track_a(workspace, first.run_id, _track_a(run_directory))
    track_b = _track_b(run_directory)
    _append_event(run_directory, "FINALIZING", hashlib.sha256(track_b.read_bytes()).hexdigest())
    from ansim_review.review_run import submit_track_b

    submit_track_b(workspace, first.run_id, track_b)
    (run_directory / "review.html").write_text("partial", encoding="utf-8")

    result = submit_question_track_b(workspace, first.run_id, track_b)

    assert result.packet.status == "READY_FOR_HUMAN_REVIEW"
    assert load_workflow_events(run_directory / "events")[-1].next_state == "READY_FOR_REVIEW"


def test_track_b_recovers_malformed_import_while_finalizing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / first.run_id
    _page_assets(workspace)
    submit_question_track_a(workspace, first.run_id, _track_a(run_directory))
    track_b = _track_b(run_directory)
    _append_event(run_directory, "FINALIZING", hashlib.sha256(track_b.read_bytes()).hexdigest())
    (run_directory / "track-b-output.json").write_text("{partial", encoding="utf-8")

    result = submit_question_track_b(workspace, first.run_id, track_b)

    assert result.packet.status == "READY_FOR_HUMAN_REVIEW"
    assert load_workflow_events(run_directory / "events")[-1].next_state == "READY_FOR_REVIEW"


def test_track_b_retries_after_interruption_before_finalizer_starts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / first.run_id
    _page_assets(workspace)
    submit_question_track_a(workspace, first.run_id, _track_a(run_directory))
    track_b = _track_b(run_directory)
    _append_event(run_directory, "FINALIZING", hashlib.sha256(track_b.read_bytes()).hexdigest())

    result = submit_question_track_b(workspace, first.run_id, track_b)

    assert result.packet.status == "READY_FOR_HUMAN_REVIEW"
    assert load_workflow_events(run_directory / "events")[-1].next_state == "READY_FOR_REVIEW"


def test_invalid_track_b_keeps_the_run_waiting_for_track_b(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / first.run_id
    submit_question_track_a(workspace, first.run_id, _track_a(run_directory))
    invalid = _track_b(run_directory)
    payload = json.loads(invalid.read_text(encoding="utf-8"))
    payload["overall_disposition"] = "REJECT"
    invalid.write_text(json.dumps(payload), encoding="utf-8")

    try:
        submit_question_track_b(workspace, first.run_id, invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid Track B output was finalized")

    resumed = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    assert resumed.status == "WAITING_TRACK_B"
    assert not (run_directory / "final-review-packet.json").exists()


def test_prepare_rejects_conflicting_immutable_query_artifact(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_question(workspace, "주차장 설치 기준")
    query_path = workspace / "runs" / first.run_id / "evidence-query.json"
    query_path.write_text("{}", encoding="utf-8")

    try:
        prepare_review_question(workspace, "주차장 설치 기준")
    except FileExistsError as error:
        assert "evidence-query.json" in str(error)
    else:
        raise AssertionError("conflicting immutable query artifact was accepted")


def test_changed_question_creates_a_new_immutable_run(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")

    first = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    second = prepare_review_question(workspace, "별표 2")

    assert first.run_id != second.run_id
    assert (workspace / "runs" / first.run_id).is_dir()
    assert (workspace / "runs" / second.run_id).is_dir()
