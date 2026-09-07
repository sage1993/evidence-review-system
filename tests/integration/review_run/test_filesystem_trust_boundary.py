from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from evidence_review.abstention.verified_artifacts import verify_run_snapshot
from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.review_run import (
    TrackBContractError,
    _publish_validated_track_b,
    prepare_review_run,
    submit_track_a,
    validate_track_b_submission,
)


def _request() -> dict[str, object]:
    return {
        "format": "ansim/review-run-request",
        "version": 1,
        "question": "filesystem trust boundary",
        "inputs": {},
        "evidence": [],
        "calculations": [],
        "rules": [],
        "approved_rule_result_ids": [],
        "confidence_input": {
            "factors": {
                name: {"value": "1.0", "source": f"fixture:{name}"}
                for name in FACTOR_WEIGHTS
            }
        },
    }


def _prepared(tmp_path: Path):
    request = tmp_path / "request.json"
    request.write_bytes(dump_bytes(_request()))
    return prepare_review_run(tmp_path / "workspace", request)


def _empty_track_a(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "claims": [],
        "citations": [],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "No claims were supplied.",
    }


def _directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            pytest.skip(
                "directory junction creation unavailable: "
                f"exit={completed.returncode}; detail={detail or '<empty>'}"
            )
        return
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink creation unavailable: {error}")


def _file_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except OSError as error:
        pytest.skip(f"file symlink creation unavailable: {error}")


def test_submit_track_a_rejects_run_directory_link_before_external_consumption(
    tmp_path: Path,
) -> None:
    prepared = _prepared(tmp_path)
    real_run = prepared.run_directory
    external_root = tmp_path / "external-runs"
    external_root.mkdir()
    external_run = external_root / prepared.run_id
    real_run.rename(external_run)
    _directory_link(real_run, external_run)

    output = tmp_path / "track-a.json"
    output.write_bytes(dump_bytes(_empty_track_a(prepared.run_id)))

    with pytest.raises(ValueError, match="symlink|reparse"):
        submit_track_a(real_run.parents[1], prepared.run_id, output)

    assert not (external_run / "track-a-output.json").exists()


def test_validate_track_b_rejects_run_artifact_link_before_external_read(
    tmp_path: Path,
) -> None:
    prepared = _prepared(tmp_path)
    run_directory = prepared.run_directory
    external = tmp_path / "external-track-a.json"
    external.write_bytes(dump_bytes(_empty_track_a(prepared.run_id)))
    artifact = run_directory / "track-a-output.json"
    _file_link(artifact, external)
    track_b = tmp_path / "track-b.json"
    track_b.write_bytes(
        dump_bytes(
            {
                "run_id": prepared.run_id,
                "claim_audits": [],
                "overall_disposition": "INCOMPLETE",
            }
        )
    )

    with pytest.raises(ValueError, match="symlink|reparse"):
        validate_track_b_submission(
            run_directory.parents[1], prepared.run_id, track_b
        )

    assert external.read_bytes() == dump_bytes(_empty_track_a(prepared.run_id))


def test_manifest_snapshot_rejects_linked_run_artifact(
    tmp_path: Path,
) -> None:
    prepared = _prepared(tmp_path)
    external = tmp_path / "external-artifact.json"
    raw = b"{}"
    external.write_bytes(raw)
    artifact = prepared.run_directory / "trusted.json"
    _file_link(artifact, external)
    (prepared.run_directory / "run-manifest.json").write_bytes(
        dump_bytes(
            {
                "run_id": prepared.run_id,
                "artifacts": {
                    "trusted.json": hashlib.sha256(raw).hexdigest(),
                },
            }
        )
    )

    with pytest.raises(ValueError, match="symlink|reparse|artifact"):
        verify_run_snapshot(
            prepared.run_directory,
            required_artifacts=("trusted.json",),
        )


def test_track_b_collision_check_rejects_linked_canonical_destination(
    tmp_path: Path,
) -> None:
    prepared = _prepared(tmp_path)
    external = tmp_path / "external-track-b.json"
    payload = {"run_id": prepared.run_id, "claim_audits": [], "overall_disposition": "INCOMPLETE"}
    external.write_bytes(dump_bytes(payload))
    destination = prepared.run_directory / "track-b-output.json"
    _file_link(destination, external)

    with pytest.raises(TrackBContractError) as caught:
        _publish_validated_track_b(
            tmp_path / "submitted-track-b.json",
            destination,
            payload,
        )

    assert caught.value.reason_code == "TRACK_B_INPUT_MISMATCH"
    assert external.read_bytes() == dump_bytes(payload)
