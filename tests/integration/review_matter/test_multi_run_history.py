from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.review_matter.formal_run_binding import (
    bind_formal_run,
    list_formal_runs,
)
from evidence_review.review_matter.formalization import formalize_snapshot
from evidence_review.review_matter.snapshot import create_formalization_snapshot
from evidence_review.review_run import prepare_review_run


def _matter_with_first_snapshot(tmp_path: Path):
    from tests.unit.review_matter.test_formalization_snapshot import (
        _evidence_database,
        _matter_store,
    )

    workspace = tmp_path / "workspace"
    evidence_db = workspace / "evidence" / "evidence.sqlite"
    evidence_db.parent.mkdir(parents=True)
    provenance = _evidence_database(evidence_db)
    provenance["database_path"] = str(evidence_db)
    store = _matter_store(workspace / "matter.sqlite", provenance)
    first = create_formalization_snapshot(store, "MATTER-SNAP-1", 2, evidence_db)
    return workspace, store, first


def _second_snapshot(workspace: Path, store: object):
    store.rename("MATTER-SNAP-1", expected_revision=2, title="Revised snapshot review")
    evidence_db = workspace / "evidence" / "evidence.sqlite"
    second = create_formalization_snapshot(store, "MATTER-SNAP-1", 3, evidence_db)
    return second


def _write_finalized_artifacts(run_directory: Path) -> tuple[str, str]:
    bundle = json.loads((run_directory / "track-a-bundle.json").read_text(encoding="utf-8"))
    track_a = {
        "run_id": bundle["run_id"],
        "claims": [],
        "citations": [],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "No claims are required.",
    }
    track_b = {
        "run_id": bundle["run_id"],
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
        dump_bytes({"run_id": bundle["run_id"], "artifacts": artifacts})
    )
    packet = finalize_run(run_directory)
    packet_path = run_directory / "final-review-packet.json"
    return packet.run_id, hashlib.sha256(packet_path.read_bytes()).hexdigest()


def _rewrite_finalized_artifact(
    run_directory: Path, artifact_name: str, document: dict[str, object]
) -> str:
    artifact_path = run_directory / artifact_name
    artifact_path.write_bytes(dump_bytes(document))
    manifest_path = run_directory / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][artifact_name] = hashlib.sha256(
        artifact_path.read_bytes()
    ).hexdigest()
    manifest_path.write_bytes(dump_bytes(manifest))
    (run_directory / "final-review-packet.json").unlink()
    finalize_run(run_directory)
    return hashlib.sha256(
        (run_directory / "final-review-packet.json").read_bytes()
    ).hexdigest()


def _finalized_formal_run(workspace: Path, snapshot: object) -> tuple[str, str]:
    prepared = formalize_snapshot(workspace, snapshot)
    return _write_finalized_artifacts(workspace / "runs" / prepared.run_id)


def _finalized_direct_run(workspace: Path, snapshot: object) -> tuple[str, str]:
    request = {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": "Unrelated direct review",
        "inputs": {
            "formalization_snapshot_id": snapshot.snapshot_id,
            "matter_id": snapshot.matter_id,
            "matter_revision": snapshot.matter_revision,
            "evidence_snapshot_provenance": {},
        },
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
    request_path = workspace / "direct-review.json"
    request_path.write_bytes(dump_bytes(request))
    prepared = prepare_review_run(workspace, request_path)
    return _write_finalized_artifacts(prepared.run_directory)


def test_one_matter_binds_two_verified_formal_runs_in_revision_order(
    tmp_path: Path,
) -> None:
    workspace, store, first = _matter_with_first_snapshot(tmp_path)
    first_run_id, first_packet_sha256 = _finalized_formal_run(workspace, first)
    second = _second_snapshot(workspace, store)
    second_run_id, second_packet_sha256 = _finalized_formal_run(workspace, second)

    first_binding = bind_formal_run(
        store,
        "MATTER-SNAP-1",
        first.snapshot_id,
        first_run_id,
        first_packet_sha256,
        workspace_root=workspace,
    )
    second_binding = bind_formal_run(
        store,
        "MATTER-SNAP-1",
        second.snapshot_id,
        second_run_id,
        second_packet_sha256,
        workspace_root=workspace,
    )

    assert list_formal_runs(
        store, "MATTER-SNAP-1", workspace_root=workspace
    ) == (first_binding, second_binding)
    assert (workspace / "runs" / first_run_id / "final-review-packet.json").is_file()
    assert (workspace / "runs" / second_run_id / "final-review-packet.json").is_file()


def test_formal_run_lineage_rejects_nonexistent_direct_wrong_snapshot_missing_and_hash_mismatch(
    tmp_path: Path,
) -> None:
    workspace, store, first = _matter_with_first_snapshot(tmp_path)
    first_run_id, first_packet_sha256 = _finalized_formal_run(workspace, first)
    direct_run_id, direct_packet_sha256 = _finalized_direct_run(workspace, first)
    second = _second_snapshot(workspace, store)
    second_run_id, second_packet_sha256 = _finalized_formal_run(workspace, second)

    invalid = (
        ("RUN-11111111111111111111", "a" * 64, first.snapshot_id),
        (first_run_id, "a" * 64, first.snapshot_id),
        (direct_run_id, direct_packet_sha256, first.snapshot_id),
        (second_run_id, second_packet_sha256, first.snapshot_id),
    )
    for run_id, packet_sha256, snapshot_id in invalid:
        with pytest.raises(ValueError, match="FORMAL_RUN_BINDING_RUN_INVALID"):
            bind_formal_run(
                store,
                "MATTER-SNAP-1",
                snapshot_id,
                run_id,
                packet_sha256,
                workspace_root=workspace,
            )

    store.create(matter_id="MATTER-OTHER", title="Other Matter")
    with pytest.raises(ValueError, match="FORMAL_RUN_BINDING_MATTER_MISMATCH"):
        bind_formal_run(
            store,
            "MATTER-OTHER",
            first.snapshot_id,
            first_run_id,
            first_packet_sha256,
            workspace_root=workspace,
        )

    packet_path = workspace / "runs" / first_run_id / "final-review-packet.json"
    packet_path.unlink()
    with pytest.raises(ValueError, match="FORMAL_RUN_BINDING_RUN_INVALID"):
        bind_formal_run(
            store,
            "MATTER-SNAP-1",
            first.snapshot_id,
            first_run_id,
            first_packet_sha256,
            workspace_root=workspace,
        )


def test_formal_run_lineage_rejects_duplicate_append_attempts(tmp_path: Path) -> None:
    workspace, store, first = _matter_with_first_snapshot(tmp_path)
    run_id, packet_sha256 = _finalized_formal_run(workspace, first)
    bind_formal_run(
        store,
        "MATTER-SNAP-1",
        first.snapshot_id,
        run_id,
        packet_sha256,
        workspace_root=workspace,
    )

    with pytest.raises(ValueError, match="FORMAL_RUN_BINDING_ALREADY_EXISTS"):
        bind_formal_run(
            store,
            "MATTER-SNAP-1",
            first.snapshot_id,
            run_id,
            packet_sha256,
            workspace_root=workspace,
        )


def test_formal_run_lineage_rejects_tampered_confidence_input_with_refreshed_packet(
    tmp_path: Path,
) -> None:
    workspace, store, first = _matter_with_first_snapshot(tmp_path)
    run_id, _packet_sha256 = _finalized_formal_run(workspace, first)
    run_directory = workspace / "runs" / run_id
    confidence = json.loads(
        (run_directory / "confidence-input.json").read_text(encoding="utf-8")
    )
    confidence["factors"]["source completeness"]["source"] = "reviewer:tamper"
    refreshed_packet_sha256 = _rewrite_finalized_artifact(
        run_directory, "confidence-input.json", confidence
    )

    with pytest.raises(ValueError, match="FORMAL_RUN_BINDING_RUN_INVALID"):
        bind_formal_run(
            store,
            "MATTER-SNAP-1",
            first.snapshot_id,
            run_id,
            refreshed_packet_sha256,
            workspace_root=workspace,
        )
