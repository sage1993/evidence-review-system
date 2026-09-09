from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.current_review_binding import (
    bind_current_review,
    resolve_current_review,
)
from evidence_review.review_packet.decision_record import write_human_decision
from evidence_review.review_run import prepare_review_run


def _request() -> dict[str, object]:
    return {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": "Is the packet immutable?",
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


def _finalized_run(repository_root: Path, *, question: str) -> tuple[str, str, Path]:
    request = _request()
    request["question"] = question
    request_path = repository_root / f"{question}.json"
    request_path.write_bytes(dump_bytes(request))
    prepared = prepare_review_run(repository_root, request_path)
    run_directory = prepared.run_directory
    track_a = {
        "run_id": prepared.run_id,
        "claims": [],
        "citations": [],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "No claims are required.",
    }
    track_b = {
        "run_id": prepared.run_id,
        "claim_audits": [],
        "overall_disposition": "INCOMPLETE",
    }
    (run_directory / "track-a-output.json").write_bytes(dump_bytes(track_a))
    (run_directory / "track-b-output.json").write_bytes(dump_bytes(track_b))
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
        dump_bytes({"run_id": prepared.run_id, "artifacts": artifacts})
    )
    finalize_run(run_directory)
    packet_path = run_directory / "final-review-packet.json"
    return prepared.run_id, hashlib.sha256(packet_path.read_bytes()).hexdigest(), run_directory


def test_current_review_pointer_is_canonical_and_resolves_its_exact_packet(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    run_id, packet_sha256, _run_directory = _finalized_run(
        repository_root, question="First review"
    )

    binding = bind_current_review(
        repository_root, run_id, packet_sha256, workspace_root=repository_root
    )
    resolved = resolve_current_review(repository_root, workspace_root=repository_root)

    assert binding.run_id == run_id
    assert resolved.run_id == run_id
    assert resolved.packet_sha256 == packet_sha256
    assert resolved.packet.human_decision is None
    assert json.loads(
        (repository_root / ".ers" / "current-review.json").read_text(encoding="utf-8")
    ) == {
        "format": "evidence-review/current-review-binding",
        "version": 1,
        "run_id": run_id,
        "packet_sha256": packet_sha256,
    }


def test_current_review_resolves_a_workspace_scoped_run_from_a_separate_repository(
    tmp_path: Path,
) -> None:
    """The repository pointer is control state; finalized runs remain in the workspace."""
    repository_root = tmp_path / "repository"
    workspace_root = tmp_path / "workspace"
    repository_root.mkdir()
    workspace_root.mkdir()
    run_id, packet_sha256, _run_directory = _finalized_run(
        workspace_root, question="Workspace-scoped review"
    )

    binding = bind_current_review(
        repository_root,
        run_id,
        packet_sha256,
        workspace_root=workspace_root,
    )
    resolved = resolve_current_review(repository_root, workspace_root=workspace_root)

    assert binding.run_id == run_id
    assert resolved.run_directory.parent.parent == workspace_root


def test_current_review_resolution_fails_closed_for_missing_stale_malformed_and_mismatched_pointer(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    with pytest.raises(FileNotFoundError, match="CURRENT_REVIEW_NOT_BOUND"):
        resolve_current_review(repository_root, workspace_root=repository_root)

    run_id, packet_sha256, run_directory = _finalized_run(
        repository_root, question="Second review"
    )
    binding_path = repository_root / ".ers" / "current-review.json"
    bind_current_review(repository_root, run_id, packet_sha256, workspace_root=repository_root)
    binding_path.write_bytes(b'{"run_id":"not-a-contract"}')
    with pytest.raises(ValueError, match="CURRENT_REVIEW_BINDING_INVALID"):
        resolve_current_review(repository_root, workspace_root=repository_root)

    binding_path.write_text(
        json.dumps(
            {
                "format": "evidence-review/current-review-binding",
                "version": 1,
                "run_id": run_id,
                "packet_sha256": packet_sha256,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="CURRENT_REVIEW_BINDING_INVALID"):
        resolve_current_review(repository_root, workspace_root=repository_root)

    malformed_before_failed_bind = binding_path.read_bytes()
    with pytest.raises(ValueError, match="CURRENT_REVIEW_STALE"):
        bind_current_review(
            repository_root, run_id, "b" * 64, workspace_root=repository_root
        )
    assert binding_path.read_bytes() == malformed_before_failed_bind

    bind_current_review(repository_root, run_id, packet_sha256, workspace_root=repository_root)
    run_directory.rename(repository_root / "removed-run")
    with pytest.raises(ValueError, match="CURRENT_REVIEW_STALE"):
        resolve_current_review(repository_root, workspace_root=repository_root)


def _file_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except OSError as error:
        pytest.skip(f"file symlink creation unavailable: {error}")


def test_current_review_resolution_rejects_an_unsafe_pointer_path(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    run_id, packet_sha256, _run_directory = _finalized_run(
        repository_root, question="Third review"
    )
    bind_current_review(repository_root, run_id, packet_sha256, workspace_root=repository_root)
    binding_path = repository_root / ".ers" / "current-review.json"
    outside = tmp_path / "outside.json"
    binding_path.rename(outside)
    _file_link(binding_path, outside)

    with pytest.raises(ValueError, match="CURRENT_REVIEW_BINDING_INVALID|symlink|reparse"):
        resolve_current_review(repository_root, workspace_root=repository_root)


def test_current_review_does_not_project_a_prior_run_human_decision(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    first_id, first_hash, first_directory = _finalized_run(
        repository_root, question="Prior review"
    )
    write_human_decision(
        first_directory,
        reviewer_id="reviewer-01",
        reviewed_at=datetime.now(UTC).isoformat(),
        packet_hash=first_hash,
        decision="SATISFIED",
        notes="",
    )
    second_id, second_hash, _second_directory = _finalized_run(
        repository_root, question="New review"
    )

    bind_current_review(
        repository_root, second_id, second_hash, workspace_root=repository_root
    )
    resolved = resolve_current_review(repository_root, workspace_root=repository_root)

    assert resolved.run_id == second_id
    assert resolved.packet_sha256 == second_hash
    assert resolved.packet.human_decision is None
    assert resolved.run_id != first_id
