from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.store import EvidenceStore
from ansim_review.observability.run_metrics import load_run_metrics
from ansim_review.retrieval.index import build_fts_index
from ansim_review.review_question import (
    prepare_review_question,
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
        build_fts_index(store.require_connection())
    return path


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
    image = b"\x89PNG\r\n\x1a\nmetrics"
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


def test_review_question_records_real_stage_boundaries(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / prepared.run_id
    _page_assets(workspace)

    submit_question_track_a(workspace, prepared.run_id, _track_a(run_directory))
    submit_question_track_b(workspace, prepared.run_id, _track_b(run_directory))

    metrics = load_run_metrics(run_directory)
    names = [stage["name"] for stage in metrics["stages"]]
    for required in (
        "request-normalization",
        "retrieval",
        "review-request-build",
        "prepare",
        "track-a-external-wait",
        "track-a-validation",
        "track-b-external-wait",
        "track-b-validation",
        "finalizer",
        "view-model-build",
        "page-image-verification",
        "html-render-write",
    ):
        assert required in names
    assert metrics["retry_count"] == 0
    assert metrics["deterministic_total_ms"] >= 0
    assert metrics["external_wait_total_ms"] >= 0


def test_metrics_do_not_change_run_id_or_final_packet_hash(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / prepared.run_id
    request_before = (run_directory / "review-request.json").read_bytes()
    _page_assets(workspace)
    submit_question_track_a(workspace, prepared.run_id, _track_a(run_directory))
    finalized = submit_question_track_b(workspace, prepared.run_id, _track_b(run_directory))
    packet_before = finalized.packet_path.read_bytes()

    load_run_metrics(run_directory)
    assert prepared.run_id == finalized.run_id
    assert (run_directory / "review-request.json").read_bytes() == request_before
    assert finalized.packet_path.read_bytes() == packet_before


def test_same_path_track_a_records_zero_retry_and_no_fileexistserror(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / prepared.run_id

    external = _track_a(run_directory)
    document = json.loads(external.read_text(encoding="utf-8"))

    output = run_directory / "track-a-output.json"
    output.write_text(
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    external.unlink()

    original_bytes = output.read_bytes()

    submit_question_track_a(
        workspace,
        prepared.run_id,
        output,
    )

    metrics = load_run_metrics(run_directory)

    assert output.read_bytes() == original_bytes
    assert metrics["retry_count"] == 0
    assert not any(
        stage["reason_code"] == "FILEEXISTSERROR"
        for stage in metrics["stages"]
    )