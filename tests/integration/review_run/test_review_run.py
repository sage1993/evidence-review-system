from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evidence_review import cli
from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.snapshot import compute_snapshot_hash
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_run import (
    TrackBContractError,
    finalize_review_run,
    prepare_review_run,
    submit_track_a,
    submit_track_b,
)


def _citation() -> dict[str, object]:
    return {
        "citation_id": "CIT-E1",
        "document_id": "DOC1",
        "revision_id": "REV1",
        "page_number": 1,
        "evidence_id": "E1",
        "bbox": [0, 0, 10, 10],
        "source_hash": "a" * 64,
    }


def _calculation() -> dict[str, object]:
    return {
        "calculation_result_id": "CALC1",
        "status": "SUCCESS",
        "formula_id": "FRONTAGE_RATIO",
        "formula_version": "1.0.0",
        "inputs": {
            "frontage_length_m": "30",
            "perimeter_length_m": "320",
            "threshold_ratio": "0.125",
        },
        "substitution": "30 / 320 = 0.09375",
        "raw_result": "0.09375",
        "display_result": "9.375%",
        "comparison": "BELOW_THRESHOLD",
        "formula_manifest_hash": "b" * 64,
        "result_hash": "d" * 64,
        "error_codes": [],
    }


def _rule() -> dict[str, object]:
    return {
        "rule_result_id": "RULE1",
        "rule_id": "ANSIM-TEST-RULE",
        "rule_version": "1.0.0",
        "status": "SATISFIED",
        "citations": [_citation()],
        "missing_inputs": [],
        "calculation_result_ids": ["CALC1"],
        "reason_codes": ["EVALUATED_TRUE"],
        "result_hash": "c" * 64,
    }


def _confidence_input() -> dict[str, object]:
    return {
        "factors": {
            name: {"value": "1.0", "source": f"fixture:{name}"}
            for name in FACTOR_WEIGHTS
        }
    }


def _request(question: str = "접면 기준 충족 여부") -> dict[str, object]:
    return {
        "format": "ansim/review-run-request",
        "version": 1,
        "question": question,
        "inputs": {"frontage": "30", "perimeter": "320"},
        "evidence": [
            {
                "citation": _citation(),
                "text": "접면 비율은 9.375%이다.",
            }
        ],
        "calculations": [_calculation()],
        "rules": [_rule()],
        "approved_rule_result_ids": ["RULE1"],
        "confidence_input": _confidence_input(),
    }


def _write_request(path: Path, question: str = "접면 기준 충족 여부") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dump_bytes(_request(question)))
    return path


def _write_page_assets(workspace: Path) -> None:
    page_directory = workspace / "page-images" / "REV1"
    page_directory.mkdir(parents=True)
    page_bytes = b"\x89PNG\r\n\x1a\nreview-run-fixture"
    (page_directory / "page-0001.png").write_bytes(page_bytes)
    metadata = {
        "format": "ansim/page-image",
        "version": 1,
        "revision_id": "REV1",
        "page_number": 1,
        "source_hash": "a" * 64,
        "pdf_width": 10.0,
        "pdf_height": 10.0,
        "image_sha256": hashlib.sha256(page_bytes).hexdigest(),
    }
    (page_directory / "page-0001.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )


def _workspace(path: Path) -> Path:
    path.mkdir(parents=True)
    evidence = path / "evidence"
    evidence.mkdir()
    with EvidenceStore(evidence / "evidence.sqlite", create=True) as store:
        connection = store.require_connection()
        connection.execute("INSERT INTO documents(id, title) VALUES('DOC1', 'Document')")
        connection.execute(
            """
            INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
            VALUES('REV1', 'DOC1', ?, 10, 1)
            """,
            ("a" * 64,),
        )
        connection.execute(
            """
            INSERT INTO pages(id, revision_id, page_number, width, height)
            VALUES('REV1-P1', 'REV1', 1, 10, 10)
            """
        )
        connection.execute(
            """
            INSERT INTO elements(
                id, page_id, element_type, raw_json, raw_text,
                normalized_text, raw_payload_hash, bbox_json, parser_order
            ) VALUES('E1', 'REV1-P1', 'paragraph', ?,
                     '접면 비율은 9.375%이다.', '접면 비율은 9.375%이다.', ?, ?, 0)
            """,
            (
                json.dumps({"text": "접면 비율은 9.375%이다."}),
                "a" * 64,
                "[0,0,10,10]",
            ),
        )
        connection.execute(
            """
            INSERT INTO retrieval_records(
                evidence_id, evidence_type, document_id, revision_id, page_id,
                page_number, bbox_json, source_hash, title, raw_text,
                normalized_text
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "E1",
                "clause",
                "DOC1",
                "REV1",
                "REV1-P1",
                1,
                "[0,0,10,10]",
                "a" * 64,
                "접면 기준",
                "접면 비율은 9.375%이다.",
                "접면 비율은 9.375%이다.",
            ),
        )
        connection.commit()
        initial_snapshot_hash = compute_snapshot_hash(store)
        connection.execute(
            "INSERT INTO snapshot_meta(key, value) VALUES('snapshot_hash', ?)",
            (initial_snapshot_hash,),
        )
        connection.commit()
        finalize_evidence_database(store)
    _write_page_assets(path)
    return path


def _track_a(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "claims": [
            {
                "claim_id": "CL1",
                "text": "접면 비율은 9.375%이다.",
                "citation_ids": ["CIT-E1"],
                "numeric_tokens": ["9.375%"],
                "calculation_result_ids": ["CALC1"],
                "rule_references": [
                    {
                        "rule_result_id": "RULE1",
                        "result_hash": "c" * 64,
                        "status": "SATISFIED",
                    }
                ],
            }
        ],
        "citations": ["CIT-E1"],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "근거와 계산 결과를 정리한다.",
    }


def _track_b(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
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


def _write_tracks(root: Path, run_id: str) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    track_a = root / "track-a-output.json"
    track_b = root / "track-b-output.json"
    track_a.write_bytes(dump_bytes(_track_a(run_id)))
    track_b.write_bytes(dump_bytes(_track_b(run_id)))
    return track_a, track_b


def test_prepare_is_deterministic_and_refuses_overwrite(tmp_path: Path) -> None:
    first_workspace = _workspace(tmp_path / "first-workspace")
    second_workspace = _workspace(tmp_path / "second-workspace")
    first_request = _write_request(tmp_path / "first-request.json")
    second_request = _write_request(tmp_path / "second-request.json")

    first = prepare_review_run(first_workspace, first_request)
    second = prepare_review_run(second_workspace, second_request)

    assert first.run_id == second.run_id
    assert (first.run_directory / "review-request.json").read_bytes() == (
        second.run_directory / "review-request.json"
    ).read_bytes()
    assert (first.run_directory / "track-a-bundle.json").read_bytes() == (
        second.run_directory / "track-a-bundle.json"
    ).read_bytes()
    assert (first.run_directory / "confidence-input.json").read_bytes() == (
        second.run_directory / "confidence-input.json"
    ).read_bytes()
    assert (first.run_directory / "prepare-status.json").read_bytes() == (
        second.run_directory / "prepare-status.json"
    ).read_bytes()

    with pytest.raises(FileExistsError):
        prepare_review_run(first_workspace, first_request)


def test_finalize_writes_packet_html_manifest_and_published_packet(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_run(
        workspace,
        _write_request(tmp_path / "request.json"),
    )
    track_a, track_b = _write_tracks(tmp_path, prepared.run_id)

    result = finalize_review_run(
        workspace,
        prepared.run_id,
        track_a,
        track_b,
        publish=True,
    )

    assert result.packet.status == "READY_FOR_HUMAN_REVIEW"
    assert result.packet.human_decision is None
    assert result.packet_path.is_file()
    assert result.review_html.is_file()
    assert (prepared.run_directory / "run-manifest.json").is_file()
    assert result.published_packet == workspace / "runs/final-review-packet.json"
    assert result.published_packet.read_bytes() == result.packet_path.read_bytes()
    published = json.loads(result.published_packet.read_text(encoding="utf-8"))
    assert published["human_decision"] is None
    html = result.review_html.read_text(encoding="utf-8")
    assert "기계 평가는 최종 판정이 아닙니다." in html
    assert "9.375%" in html
    assert "data:image/png;base64," in html


def test_submit_track_b_finalizes_a_prevalidated_track_a(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_run(workspace, _write_request(tmp_path / "request.json"))
    track_a, track_b = _write_tracks(tmp_path, prepared.run_id)

    submit_track_a(workspace, prepared.run_id, track_a)
    result = submit_track_b(workspace, prepared.run_id, track_b)

    assert result.packet.status == "READY_FOR_HUMAN_REVIEW"


def test_submit_track_b_accepts_valid_run_local_track_b_without_rewriting(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_run(tmp_path / "workspace", _write_request(tmp_path / "request.json"))
    track_a, _external_b = _write_tracks(tmp_path / "tracks", prepared.run_id)
    submit_track_a(workspace, prepared.run_id, track_a)

    run_local_b = prepared.run_directory / "track-b-output.json"
    original = dump_bytes(_track_b(prepared.run_id))
    run_local_b.write_bytes(original)

    result = submit_track_b(workspace, prepared.run_id, run_local_b)

    assert result.packet.status == "READY_FOR_HUMAN_REVIEW"
    assert run_local_b.read_bytes() == original

def test_external_track_b_reuses_identical_run_local_validated_input(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_run(workspace, _write_request(tmp_path / "request.json"))
    track_a, track_b = _write_tracks(tmp_path / "tracks", prepared.run_id)
    submit_track_a(workspace, prepared.run_id, track_a)

    canonical = prepared.run_directory / "track-b-output.json"
    canonical.write_bytes(dump_bytes(_track_b(prepared.run_id)))

    result = submit_track_b(workspace, prepared.run_id, track_b)

    assert result.packet.status == "READY_FOR_HUMAN_REVIEW"


def test_external_track_b_rejects_different_existing_run_local_input(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_run(workspace, _write_request(tmp_path / "request.json"))
    track_a, track_b = _write_tracks(tmp_path / "tracks", prepared.run_id)
    submit_track_a(workspace, prepared.run_id, track_a)

    canonical = prepared.run_directory / "track-b-output.json"
    different = _track_b(prepared.run_id)
    different["overall_disposition"] = "REJECT"
    canonical.write_bytes(dump_bytes(different))

    with pytest.raises(TrackBContractError) as caught:
        submit_track_b(workspace, prepared.run_id, track_b)

    assert caught.value.reason_code == "TRACK_B_INPUT_MISMATCH"


def test_finalize_open_cli_prints_only_the_protected_review_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    run_id = "RUN-0123456789ABCDEF0123"
    run_directory = workspace / "runs" / run_id
    packet_path = run_directory / "final-review-packet.json"
    html_path = run_directory / "review.html"

    def fake_finalize(
        workspace_root: Path,
        supplied_run_id: str,
        track_a_output: Path,
        track_b_output: Path,
        *,
        publish: bool,
    ) -> SimpleNamespace:
        assert workspace_root == workspace
        assert supplied_run_id == run_id
        assert track_a_output == tmp_path / "track-a.json"
        assert track_b_output == tmp_path / "track-b.json"
        assert publish is False
        return SimpleNamespace(
            run_id=run_id,
            run_directory=run_directory,
            packet=SimpleNamespace(status="READY_FOR_HUMAN_REVIEW"),
            packet_path=packet_path,
            review_html=html_path,
            published_packet=None,
        )

    def fake_open(workspace_root: Path, supplied_run_id: str) -> str:
        assert workspace_root == workspace
        assert supplied_run_id == run_id
        return f"http://127.0.0.1:8123/runs/{run_id}/token/review"

    def legacy_wait_or_close(*_args: object) -> None:
        raise AssertionError("detached review server must not use legacy wait/close hooks")

    monkeypatch.setattr(cli, "finalize_review_run", fake_finalize)
    monkeypatch.setattr(cli, "open_review_run", fake_open, raising=False)
    monkeypatch.setattr(cli, "wait_for_review_run", legacy_wait_or_close, raising=False)
    monkeypatch.setattr(cli, "close_review_run", legacy_wait_or_close, raising=False)

    assert (
        cli.main(
            [
                "review-run",
                "finalize",
                "--workspace",
                str(workspace),
                "--run-id",
                run_id,
                "--track-a-output",
                str(tmp_path / "track-a.json"),
                "--track-b-output",
                str(tmp_path / "track-b.json"),
                "--open",
            ]
        )
        == 0
    )

    document = json.loads(capsys.readouterr().out)
    assert document == {
        "status": "READY_FOR_HUMAN_REVIEW",
        "run_id": run_id,
        "url": f"http://127.0.0.1:8123/runs/{run_id}/token/review",
    }
    assert not document["url"].startswith("file:")


def test_finalize_refuses_existing_publication(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_run(
        workspace,
        _write_request(tmp_path / "first.json", "첫 번째 검토"),
    )
    first_a, first_b = _write_tracks(tmp_path / "first-tracks", first.run_id)
    finalize_review_run(
        workspace,
        first.run_id,
        first_a,
        first_b,
        publish=True,
    )

    second = prepare_review_run(
        workspace,
        _write_request(tmp_path / "second.json", "두 번째 검토"),
    )
    second_a, second_b = _write_tracks(tmp_path / "second-tracks", second.run_id)
    with pytest.raises(FileExistsError):
        finalize_review_run(
            workspace,
            second.run_id,
            second_a,
            second_b,
            publish=True,
        )


def test_finalize_refuses_missing_verified_page_assets(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_run(
        workspace,
        _write_request(tmp_path / "request.json"),
    )
    track_a, track_b = _write_tracks(tmp_path, prepared.run_id)
    for asset_path in (workspace / "page-images").rglob("*"):
        if asset_path.is_file():
            asset_path.unlink()

    with pytest.raises(FileNotFoundError, match="verified page image"):
        finalize_review_run(
            workspace,
            prepared.run_id,
            track_a,
            track_b,
            publish=True,
        )

    assert not (prepared.run_directory / "final-review-packet.json").exists()
    assert not (prepared.run_directory / "review.html").exists()
    assert not (workspace / "runs" / "final-review-packet.json").exists()


def test_prepare_rejects_invalid_request_before_creating_runs(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    request = _request()
    request["format"] = "invalid"
    request_path = tmp_path / "invalid.json"
    request_path.write_bytes(dump_bytes(request))

    with pytest.raises(ValueError, match="unsupported review-run request"):
        prepare_review_run(workspace, request_path)

    assert not (workspace / "runs").exists()


def test_finalize_requires_prepared_artifacts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    run_id = "RUN-0123456789ABCDEF0123"
    (workspace / "runs" / run_id).mkdir(parents=True)
    track_a, track_b = _write_tracks(tmp_path, run_id)

    with pytest.raises(FileNotFoundError):
        finalize_review_run(workspace, run_id, track_a, track_b)
