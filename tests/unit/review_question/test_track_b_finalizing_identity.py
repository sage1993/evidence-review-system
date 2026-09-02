from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.canonical_json import dump_bytes, sha256_json
from evidence_review.review_question import (
    _append_event,
    _has_valid_finalizing_canonical_track_b,
    _validate_finalizing_retry_identity,
)
from evidence_review.review_run import TrackBContractError


def _track_b_document(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "claims": [{"claim_id": "CL1", "text": "동일한 의미의 Track B"}],
        "citations": ["CIT-E1"],
    }


def _enter_finalizing(run_directory: Path, track_b_hash: str) -> None:
    for state in (
        "RECEIVED",
        "CLASSIFYING_INPUTS",
        "READY_TO_EVALUATE",
        "RETRIEVING_EVIDENCE",
        "RUNNING_MATH",
        "RUNNING_RULES",
        "WAITING_TRACK_A",
        "WAITING_TRACK_B",
    ):
        _append_event(run_directory, state, "a" * 64)  # type: ignore[arg-type]
    _append_event(run_directory, "FINALIZING", track_b_hash)


def test_finalizing_track_b_identity_ignores_json_serialization(tmp_path: Path) -> None:
    run_directory = tmp_path / "RUN-0123456789ABCDEF0123"
    document = _track_b_document(run_directory.name)
    _enter_finalizing(run_directory, sha256_json(document))

    canonical = run_directory / "track-b-output.json"
    canonical.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    retry = tmp_path / "track-b-retry.json"
    retry.write_text(
        json.dumps(document, ensure_ascii=False, separators=(", ", ": ")),
        encoding="utf-8",
    )

    assert canonical.read_bytes() != dump_bytes(document)
    assert retry.read_bytes() != dump_bytes(document)
    assert _has_valid_finalizing_canonical_track_b(run_directory)
    _validate_finalizing_retry_identity(run_directory, retry)


def test_finalizing_track_b_identity_rejects_semantic_change(tmp_path: Path) -> None:
    run_directory = tmp_path / "RUN-ABCDEF0123456789ABCD"
    document = _track_b_document(run_directory.name)
    _enter_finalizing(run_directory, sha256_json(document))

    retry_document = dict(document)
    retry_document["claims"] = [{"claim_id": "CL2", "text": "변경된 Track B"}]
    retry = tmp_path / "track-b-mutated.json"
    retry.write_bytes(dump_bytes(retry_document))

    with pytest.raises(TrackBContractError) as exc_info:
        _validate_finalizing_retry_identity(run_directory, retry)

    assert exc_info.value.reason_code == "TRACK_B_RETRY_MISMATCH"
