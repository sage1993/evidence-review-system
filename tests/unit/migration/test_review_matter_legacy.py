from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.review_run import prepare_review_run


def _finalized_legacy_run(tmp_path: Path) -> Path:
    workspace = tmp_path / "legacy-workspace"
    workspace.mkdir()
    request_path = workspace / "request.json"
    request_path.write_bytes(
        dump_bytes(
            {
                "format": "evidence-review/review-run-request",
                "version": 1,
                "question": "Historical formal review",
                "inputs": {},
                "evidence": [],
                "calculations": [],
                "rules": [],
                "approved_rule_result_ids": [],
                "confidence_input": {
                    "factors": {
                        name: {"value": "1.0", "source": "fixture"}
                        for name in FACTOR_WEIGHTS
                    }
                },
            }
        )
    )
    prepared = prepare_review_run(workspace, request_path)
    run_directory = prepared.run_directory
    bundle = json.loads((run_directory / "track-a-bundle.json").read_text(encoding="utf-8"))
    (run_directory / "track-a-output.json").write_bytes(
        dump_bytes(
            {
                "run_id": bundle["run_id"],
                "claims": [],
                "citations": [],
                "missing_inputs": [],
                "exceptions": [],
                "conflicts": [],
                "explanation": "No claims are required.",
            }
        )
    )
    (run_directory / "track-b-output.json").write_bytes(
        dump_bytes(
            {
                "run_id": bundle["run_id"],
                "audited_question": bundle["question"],
                "question_responsiveness": "NOT_VERIFIED",
                "required_facet_completeness": "NOT_APPLICABLE",
                "claim_audits": [],
                "overall_disposition": "INCOMPLETE",
            }
        )
    )
    artifacts = {
        name: hashlib.sha256((run_directory / name).read_bytes()).hexdigest()
        for name in (
            "track-a-bundle.json",
            "track-a-output.json",
            "track-b-output.json",
            "confidence-input.json",
        )
    }
    (run_directory / "run-manifest.json").write_bytes(
        dump_bytes({"run_id": bundle["run_id"], "artifacts": artifacts})
    )
    finalize_run(run_directory)
    return run_directory


def _directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/D", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            return
        detail = (completed.stderr or completed.stdout).strip()
        pytest.skip(f"directory symlink creation unavailable: {detail or '<empty>'}")
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink creation unavailable: {error}")


def test_legacy_run_reference_rejects_noncanonical_human_decision(tmp_path: Path) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    run_directory = _finalized_legacy_run(tmp_path)
    packet_sha256 = hashlib.sha256(
        (run_directory / "final-review-packet.json").read_bytes()
    ).hexdigest()
    decisions = run_directory / "human-decisions"
    decisions.mkdir()
    (decisions / "20260911T090000000000+0000-reviewer-01.json").write_bytes(
        (
            '{"decision":"SATISFIED","notes":"","packet_hash":"'
            + packet_sha256
            + '","reviewed_at":"2026-09-11T09:00:00+00:00",'
            '"reviewer_id":"reviewer-01","run_id":"'
            + run_directory.name
            + '","unexpected":true}'
        ).encode("utf-8")
    )

    with pytest.raises(ValueError, match="LEGACY_FORMAL_RUN_INVALID"):
        legacy_reference_from_run(run_directory)


def test_legacy_run_reference_is_immutable_and_deterministic(tmp_path: Path) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    run_directory = _finalized_legacy_run(tmp_path)

    first = legacy_reference_from_run(run_directory)
    second = legacy_reference_from_run(Path(run_directory))

    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.run_id = "RUN-00000000000000000000"  # type: ignore[misc]


def test_legacy_run_reference_rejects_noncanonical_packet_without_rewriting(
    tmp_path: Path,
) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    run_directory = _finalized_legacy_run(tmp_path)
    packet_path = run_directory / "final-review-packet.json"
    tampered = packet_path.read_bytes() + b"\n"
    packet_path.write_bytes(tampered)

    with pytest.raises(ValueError, match="LEGACY_FORMAL_RUN_INVALID"):
        legacy_reference_from_run(run_directory)

    assert packet_path.read_bytes() == tampered


def test_legacy_run_reference_rejects_decision_for_another_packet(tmp_path: Path) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    run_directory = _finalized_legacy_run(tmp_path)
    decisions = run_directory / "human-decisions"
    decisions.mkdir()
    (decisions / "20260911T090000000000+0000-reviewer-01.json").write_bytes(
        dump_bytes(
            {
                "run_id": run_directory.name,
                "reviewer_id": "reviewer-01",
                "reviewed_at": "2026-09-11T09:00:00+00:00",
                "packet_hash": "f" * 64,
                "decision": "SATISFIED",
                "notes": "",
            }
        )
    )

    with pytest.raises(ValueError, match="LEGACY_FORMAL_RUN_INVALID"):
        legacy_reference_from_run(run_directory)


def test_legacy_run_reference_rejects_malformed_manifest_without_rewriting(
    tmp_path: Path,
) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    run_directory = _finalized_legacy_run(tmp_path)
    manifest_path = run_directory / "run-manifest.json"
    malformed = b'{"artifacts":'
    manifest_path.write_bytes(malformed)

    with pytest.raises(ValueError, match="LEGACY_FORMAL_RUN_INVALID"):
        legacy_reference_from_run(run_directory)

    assert manifest_path.read_bytes() == malformed


def test_legacy_run_reference_rejects_linked_run_path_without_reading_target(
    tmp_path: Path,
) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    run_directory = _finalized_legacy_run(tmp_path)
    packet_path = run_directory / "final-review-packet.json"
    packet_bytes = packet_path.read_bytes()
    linked_run = tmp_path / "linked-run"
    _directory_link(linked_run, run_directory)

    with pytest.raises(ValueError, match="LEGACY_FORMAL_RUN_INVALID"):
        legacy_reference_from_run(linked_run)

    assert packet_path.read_bytes() == packet_bytes


def test_legacy_run_reference_rejects_noncanonical_same_id_run_directory(
    tmp_path: Path,
) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    canonical_run = _finalized_legacy_run(tmp_path)
    packet_path = canonical_run / "final-review-packet.json"
    packet_sha256 = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    decisions = canonical_run / "human-decisions"
    decisions.mkdir()
    (decisions / "20260911T090000000000+0000-reviewer-01.json").write_bytes(
        dump_bytes(
            {
                "run_id": canonical_run.name,
                "reviewer_id": "reviewer-01",
                "reviewed_at": "2026-09-11T09:00:00+00:00",
                "packet_hash": packet_sha256,
                "decision": "SATISFIED",
                "notes": "",
            }
        )
    )

    copied_run = canonical_run.parent.parent / "copied-runs" / canonical_run.name
    shutil.copytree(canonical_run, copied_run)
    shutil.rmtree(copied_run / "human-decisions")

    with pytest.raises(ValueError, match="LEGACY_FORMAL_RUN_INVALID"):
        legacy_reference_from_run(copied_run)
