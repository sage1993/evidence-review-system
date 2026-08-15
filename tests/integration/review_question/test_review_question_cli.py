from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evidence_review import cli, review_question
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.index import build_fts_index
from evidence_review.review_question import (
    _append_event,
    prepare_review_question,
    submit_question_track_a,
    submit_question_track_b,
)
from evidence_review.review_run import TrackBContractError
from evidence_review.workflow.events import load_workflow_events


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


def _question_plan_output(
    path: Path,
    *,
    question: str,
    search_text: str,
    issue_question: str | None = None,
    facts: list[dict[str, str]] | None = None,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "format": "evidence-review/question-plan",
                "version": 1,
                "original_question": question,
                "facts": [] if facts is None else facts,
                "assumptions": [],
                "issues": [
                    {
                        "id": "I1",
                        "question": issue_question or question,
                        "depends_on": [],
                    }
                ],
                "legal_anchors": [],
                "search_requests": [
                    {
                        "id": "S1",
                        "issue_ids": ["I1"],
                        "text": search_text,
                        "kind": "phrase",
                        "source": "planner",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_review_question_prepare_hides_question_and_evidence_from_stdout(
    capsys,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    question = "주차장 설치 기준"
    plan_output = _question_plan_output(
        tmp_path / "question-plan-output.json",
        question=question,
        search_text="주차장",
        issue_question="주차장 설치 기준은 무엇인가",
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
            str(plan_output),
            "--expansion",
            "별표 2",
        ]
    ) == 0

    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "WAITING_TRACK_A"
    assert document["resumed"] is False
    assert question not in json.dumps(document, ensure_ascii=False)
    action = json.loads(Path(document["next_action_path"]).read_text(encoding="utf-8"))
    assert action["action"] == "PRODUCE_TRACK_A"
    evidence_query = json.loads(
        (workspace / "runs" / document["run_id"] / "evidence-query.json").read_text(
            encoding="utf-8"
        )
    )
    user_term = next(item for item in evidence_query["query"]["terms"] if item["text"] == "별표 2")
    assert user_term["origin"] == "user"


def test_review_question_submit_track_b_open_returns_review_html_and_protected_url(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    run_id = "RUN-0123456789ABCDEF0123"
    html_path = workspace / "runs" / run_id / "review.html"

    def fake_submit(*_args, **_kwargs):
        return SimpleNamespace(
            run_id=run_id,
            review_html=html_path,
            packet=SimpleNamespace(status="READY_FOR_HUMAN_REVIEW"),
            published_packet=None,
        )

    def fake_open(_workspace: Path, _run_id: str) -> str:
        return f"http://127.0.0.1:8123/runs/{run_id}/token/review"

    monkeypatch.setattr(cli, "submit_question_track_b", fake_submit)
    monkeypatch.setattr(cli, "open_review_run", fake_open)

    exit_code = cli.main(
        [
            "review-question",
            "submit-track-b",
            "--workspace",
            str(workspace),
            "--run-id",
            run_id,
            "--track-b-output",
            str(tmp_path / "track-b.json"),
            "--open",
        ]
    )

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["review_html"] == str(html_path)
    assert document["display_status"] == "OPENED"
    assert document["url"].startswith("http://127.0.0.1:")


def test_review_question_prepare_resumes_the_same_immutable_request(
    capsys,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    question = "주차장 설치 기준"
    plan_output = _question_plan_output(
        tmp_path / "question-plan-output.json",
        question=question,
        search_text="주차장",
        issue_question="주차장 설치 기준은 무엇인가",
    )
    arguments = [
        "review-question",
        "prepare",
        "--workspace",
        str(workspace),
        "--question",
        question,
        "--question-plan-output",
        str(plan_output),
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
    from evidence_review.review_run import submit_track_b

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
    from evidence_review.review_run import submit_track_b

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


def test_finalizing_retry_rejects_different_track_b_before_finalizer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_question(
        workspace,
        "\uc8fc\ucc28\uc7a5\uc740 \ubcc4\ud45c 2\uc5d0 \ub530\ub978\ub2e4",
    )
    run_directory = workspace / "runs" / first.run_id
    submit_question_track_a(workspace, first.run_id, _track_a(run_directory))

    original = _track_b(run_directory)
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    _append_event(run_directory, "FINALIZING", original_hash)

    changed = run_directory / "different-track-b.json"
    payload = json.loads(original.read_text(encoding="utf-8"))
    payload["claim_audits"][0]["notes"] = "different retry"
    changed.write_text(json.dumps(payload), encoding="utf-8")

    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("finalizer must not run for a retry hash mismatch")

    monkeypatch.setattr(review_question, "submit_track_b", fail_if_called)

    with pytest.raises(TrackBContractError) as caught:
        submit_question_track_b(workspace, first.run_id, changed)

    assert caught.value.reason_code == "TRACK_B_RETRY_MISMATCH"
    assert called is False


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


def _korean_element(
    evidence_id: str,
    *,
    parser_order: int,
    text: str,
    payload_hash_char: str,
) -> dict[str, object]:
    return {
        "id": evidence_id,
        "revision_id": "REV-KR",
        "page_id": "REV-KR-P1",
        "page_number": 1,
        "element_type": "table_cell",
        "raw_json": {"text": text},
        "raw_text": text,
        "normalized_text": text,
        "raw_payload_hash": payload_hash_char * 64,
        "bbox": [10.0, float(parser_order), 500.0, float(parser_order + 1)],
        "parser_order": parser_order,
    }


def _korean_workspace(path: Path) -> tuple[Path, str]:
    (path / "evidence").mkdir(parents=True)

    snapshot = EvidenceSnapshot(
        documents=(
            {"id": "DOC-KR", "title": "청소년수련시설 기준"},
        ),
        revisions=(
            {
                "id": "REV-KR",
                "document_id": "DOC-KR",
                "source_hash": "c" * 64,
                "byte_size": 100,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": "REV-KR-P1",
                "revision_id": "REV-KR",
                "page_number": 1,
                "width": 595.0,
                "height": 842.0,
            },
        ),
        elements=(
            _korean_element(
                "E-YOUTH-CENTER-LABEL",
                parser_order=10,
                text="청소년수련관",
                payload_hash_char="d",
            ),
            _korean_element(
                "E-YOUTH-CENTER-1500",
                parser_order=11,
                text="연건축면적이 1,500제곱미터 이상이어야 하며 관련 기준을 따른다.",
                payload_hash_char="e",
            ),
            _korean_element(
                "E-CULTURE-HOUSE",
                parser_order=20,
                text="청소년문화의집",
                payload_hash_char="f",
            ),
            _korean_element(
                "E-CULTURE-DESC",
                parser_order=21,
                text="청소년수련시설 중 가장 작은 규모의 시설이다.",
                payload_hash_char="1",
            ),
        ),
    )

    with EvidenceStore(
        path / "evidence" / "evidence.sqlite",
        create=True,
    ) as store:
        snapshot_hash = ingest_snapshot(store, snapshot)
        build_fts_index(store.require_connection())

    return path, snapshot_hash


def test_korean_formal_review_prepare_preserves_retrieval_and_snapshot_lineage(
    capsys,
    tmp_path: Path,
) -> None:
    workspace, snapshot_hash = _korean_workspace(tmp_path / "workspace")

    question = (
        "청소년 문화의집은 면적이 "
        "1500제곱미터 이상이어야 한다."
    )
    plan_output = _question_plan_output(
        tmp_path / "question-plan-output.json",
        question=question,
        search_text="청소년 문화의집",
        issue_question="청소년 문화의집의 면적 기준은 무엇인가",
        facts=[
            {
                "id": "F1",
                "text": "면적이 1500제곱미터 이상이어야 한다",
                "polarity": "positive",
            }
        ],
    )

    arguments = [
        "review-question",
        "prepare",
        "--workspace",
        str(workspace),
        "--question",
        question,
        "--question-plan-output",
        str(plan_output),
    ]

    assert cli.main(arguments) == 0

    first = json.loads(capsys.readouterr().out)

    run_directory = workspace / "runs" / first["run_id"]

    evidence_query_path = run_directory / "evidence-query.json"
    review_request_path = run_directory / "review-request.json"
    track_a_bundle_path = run_directory / "track-a-bundle.json"

    evidence_query = json.loads(evidence_query_path.read_text(encoding="utf-8"))
    review_request = json.loads(review_request_path.read_text(encoding="utf-8"))
    track_a_bundle = json.loads(track_a_bundle_path.read_text(encoding="utf-8"))

    assert evidence_query["hits"]

    evidence_ids = {item["evidence_id"] for item in evidence_query["hits"]}

    assert "E-YOUTH-CENTER-1500" in evidence_ids
    assert "E-CULTURE-HOUSE" in evidence_ids

    texts = [item["text"] for item in review_request["evidence"]]

    assert any("청소년문화의집" in text for text in texts)
    assert any("1,500제곱미터" in text for text in texts)
    assert any("청소년수련관" in text for text in texts)

    assert review_request["inputs"]["snapshot_hash"] == snapshot_hash
    assert track_a_bundle["inputs"]["snapshot_hash"] == snapshot_hash
    assert review_request["inputs"]["question_plan_sha256"]
    assert track_a_bundle["inputs"]["question_plan"]["facts"] == [
        {
            "id": "F1",
            "text": "면적이 1500제곱미터 이상이어야 한다",
            "polarity": "positive",
        }
    ]

    assert evidence_query["query"]["derived_variants"]["entity"] == [
        "청소년 문화의집",
        "청소년문화의집",
    ]

    artifacts_before = {
        item.name: item.read_bytes()
        for item in (
            evidence_query_path,
            review_request_path,
            track_a_bundle_path,
        )
    }

    assert cli.main(arguments) == 0

    second = json.loads(capsys.readouterr().out)

    assert second["run_id"] == first["run_id"]
    assert second["resumed"] is True

    artifacts_after = {
        item.name: item.read_bytes()
        for item in (
            evidence_query_path,
            review_request_path,
            track_a_bundle_path,
        )
    }

    assert artifacts_after == artifacts_before


def test_review_question_submit_track_b_open_preserves_finalization_on_display_failure(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    run_id = "RUN-0123456789ABCDEF0123"
    html_path = workspace / "runs" / run_id / "review.html"

    monkeypatch.setattr(
        cli,
        "submit_question_track_b",
        lambda *_args, **_kwargs: SimpleNamespace(
            run_id=run_id,
            review_html=html_path,
            packet=SimpleNamespace(status="READY_FOR_HUMAN_REVIEW"),
            published_packet=None,
        ),
    )

    def fail_open(*_args, **_kwargs):
        raise RuntimeError("browser dispatch failed")

    monkeypatch.setattr(cli, "open_review_run", fail_open)

    exit_code = cli.main(
        [
            "review-question",
            "submit-track-b",
            "--workspace",
            str(workspace),
            "--run-id",
            run_id,
            "--track-b-output",
            str(tmp_path / "track-b.json"),
            "--open",
        ]
    )

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "READY_FOR_HUMAN_REVIEW"
    assert document["review_html"] == str(html_path)
    assert document["display_status"] == "OPEN_FAILED"
    assert "browser dispatch failed" in document["display_error"]
    assert "url" not in document


def test_prepare_zero_hit_emits_guidance_but_keeps_authoritative_evidence_empty(
    tmp_path: Path,
) -> None:
    workspace, _snapshot_hash = _korean_workspace(tmp_path / "workspace")
    prepared = prepare_review_question(workspace, "존재하지않는시설 설치기준")
    run_directory = workspace / "runs" / prepared.run_id

    request = json.loads(
        (run_directory / "review-request.json").read_text(encoding="utf-8")
    )
    assert prepared.retrieval_guidance_path is not None
    guidance = json.loads(
        prepared.retrieval_guidance_path.read_text(encoding="utf-8")
    )

    assert request["evidence"] == []
    assert guidance["authoritative_hit_count"] == 0
    assert guidance["attempted_terms"]
    assert all(
        value["value"] == "0.0"
        for name, value in request["confidence_input"]["factors"].items()
        if name in {"source completeness", "traceability", "input completeness"}
    )


@pytest.mark.parametrize(
    "question",
    [
        "청소년 문화의집 설치기준",
        "청소년문화의집 설치기준",
        "청소년수련관 설치기준",
    ],
)
def test_reported_korean_question_prepares_with_authoritative_evidence_without_expansion(
    tmp_path: Path,
    question: str,
) -> None:
    workspace, snapshot_hash = _korean_workspace(tmp_path / "workspace")
    prepared = prepare_review_question(workspace, question)
    run_directory = workspace / "runs" / prepared.run_id
    request = json.loads(
        (run_directory / "review-request.json").read_text(encoding="utf-8")
    )

    assert request["evidence"]
    assert request["inputs"]["snapshot_hash"] == snapshot_hash
    assert prepared.retrieval_guidance_path is None


def test_korean_formal_review_traverses_to_protected_handoff(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    workspace, snapshot_hash = _korean_workspace(tmp_path / "workspace")
    _page_assets(workspace)
    page_directory = workspace / "page-images" / "REV-KR"
    page_directory.mkdir(parents=True)
    image = b"\\x89PNG\\r\\n\\x1a\\nreview-question-korean"
    (page_directory / "page-0001.png").write_bytes(image)
    (page_directory / "page-0001.json").write_text(
        json.dumps(
            {
                "format": "ansim/page-image",
                "version": 1,
                "revision_id": "REV-KR",
                "page_number": 1,
                "source_hash": "c" * 64,
                "pdf_width": 595.0,
                "pdf_height": 842.0,
                "image_sha256": hashlib.sha256(image).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    prepared = prepare_review_question(
        workspace,
        "\uccad\uc18c\ub144\ubb38\ud654\uc758\uc9d1 \uc124\uce58\uae30\uc900",
    )
    assert prepared.status == "WAITING_TRACK_A"
    run_directory = workspace / "runs" / prepared.run_id
    evidence_query = json.loads(
        (run_directory / "evidence-query.json").read_text(encoding="utf-8")
    )
    expected_citations = {
        hit["citation"]["citation_id"]: hit["citation"]
        for hit in evidence_query["hits"]
        if hit["citation"] is not None
    }

    track_a_bundle = json.loads((run_directory / "track-a-bundle.json").read_text(encoding="utf-8"))
    first_evidence = track_a_bundle["evidence"][0]
    integrated_track_a = run_directory / "integrated-track-a.json"
    integrated_track_a.write_text(
        json.dumps(
            {
                "run_id": prepared.run_id,
                "claims": [
                    {
                        "claim_id": "CL1",
                        "text": first_evidence["text"],
                        "citation_ids": [first_evidence["citation"]["citation_id"]],
                        "numeric_tokens": [],
                        "calculation_result_ids": [],
                        "rule_references": [],
                    }
                ],
                "citations": [first_evidence["citation"]["citation_id"]],
                "missing_inputs": [],
                "exceptions": [],
                "conflicts": [],
                "explanation": "integrated formal review fixture",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    submitted_a = submit_question_track_a(
        workspace,
        prepared.run_id,
        integrated_track_a,
    )
    assert submitted_a.next_action_path.is_file()

    external_track_b = _track_b(run_directory)
    track_b_bytes = external_track_b.read_bytes()
    run_local_b = run_directory / "track-b-output.json"
    run_local_b.write_bytes(track_b_bytes)
    finalized = submit_question_track_b(workspace, prepared.run_id, run_local_b)
    assert finalized.packet.status == "READY_FOR_HUMAN_REVIEW"
    assert finalized.review_html.is_file()
    assert run_local_b.read_bytes() == track_b_bytes

    request = json.loads(
        (run_directory / "review-request.json").read_text(encoding="utf-8")
    )
    assert request["inputs"]["snapshot_hash"] == snapshot_hash
    for item in request["evidence"]:
        citation = item["citation"]
        authoritative = expected_citations[citation["citation_id"]]
        assert citation["source_hash"] == authoritative["source_hash"]
        assert citation["page_number"] == authoritative["page_number"]
        assert citation["bbox"] == authoritative["bbox"]
        assert citation["evidence_id"] == authoritative["evidence_id"]

    monkeypatch.setattr(
        cli,
        "open_review_run",
        lambda _workspace, run_id: (
            f"http://127.0.0.1:8123/runs/{run_id}/acceptance-token/review"
        ),
    )
    assert cli.main(
        [
            "review-question",
            "submit-track-b",
            "--workspace",
            str(workspace),
            "--run-id",
            prepared.run_id,
            "--track-b-output",
            str(run_local_b),
            "--open",
        ]
    ) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["review_html"] == str(finalized.review_html)
    assert document["display_status"] == "OPENED"
    assert document["url"].startswith("http://127.0.0.1:")
