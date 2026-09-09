import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from evidence_review.release.attestation import REQUIRED_CHECK_IDS
from evidence_review.release.builder import build_ansim_release, build_evidence_release
from evidence_review.release.config import ReleaseConfig

_RUN_ID = "RUN-0123456789ABCDEF0123"


def _workspace(root: Path) -> None:
    repository_root = Path(__file__).parents[3]
    shutil.copytree(
        repository_root / "src/evidence_review",
        root / "src/evidence_review",
    )
    shutil.copytree(
        repository_root / "src/ansim_review",
        root / "src/ansim_review",
    )
    (root / "evidence").mkdir()
    connection = sqlite3.connect(root / "evidence/evidence.sqlite")
    connection.execute("CREATE TABLE evidence(id TEXT PRIMARY KEY)")
    connection.commit()
    connection.close()
    (root / "rules/approved").mkdir(parents=True)
    (root / "rules/approved/R1.json").write_text("{}", encoding="utf-8")
    (root / "rules/manifests").mkdir()
    (root / "rules/manifests/active.json").write_text("{}", encoding="utf-8")
    (root / "formulas").mkdir()
    (root / "formulas/manifest.json").write_text("{}", encoding="utf-8")
    (root / "examples").mkdir()
    (root / "examples/sample-request.json").write_text("{}", encoding="utf-8")
    shutil.copytree(repository_root / "web_runtime", root / "web_runtime")
    (root / "tests/golden/questions").mkdir(parents=True)
    shutil.copy2(
        repository_root / "tests/golden/questions/ansim_cases.json",
        root / "tests/golden/questions/ansim_cases.json",
    )
    for name in ("ers-pdf", "ers-review"):
        shutil.copytree(
            repository_root / "skills" / name,
            root / "skills" / name,
        )
    (root / "README.md").write_text("# Release fixture\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs/OFFLINE_EXECUTION.md").write_text(
        "# Offline Execution\n",
        encoding="utf-8",
    )
    (root / "documentation-integrity.json").write_text(
        json.dumps(
            {
                "format": "evidence-review/documentation-integrity-config",
                "version": 1,
                "current_roots": [
                    "README.md",
                    "AGENTS.md",
                    "docs/OFFLINE_EXECUTION.md",
                    "skills",
                ],
                "historical_roots": [],
                "current_overrides": [],
                "historical_overrides": [],
                "generated_documents": [],
            }
        ),
        encoding="utf-8",
    )
    _run_local_packet(root)


def _attestation(
    candidate_hash: str,
    packet_hash: str,
    *,
    reviewer_id: str = "reviewer@example.com",
) -> dict[str, object]:
    return {
        "format": "evidence-review/human-attestation",
        "version": 1,
        "assurance_level": "PROCESS_ATTESTATION",
        "reviewer_id": reviewer_id,
        "reviewed_at": "2026-08-02T14:00:00+09:00",
        "attestation": "REVIEWED_AND_ACCEPTED_FOR_RELEASE",
        "release_candidate_hash": candidate_hash,
        "packet_hash": packet_hash,
        "checks": [
            {
                "check_id": item,
                "status": "PASS",
                "evidence": f"evidence/{item}",
            }
            for item in REQUIRED_CHECK_IDS
        ],
    }


def _legacy_acceptance(candidate_hash: str, packet_hash: str) -> dict[str, object]:
    return {
        "format": "ansim/human-acceptance",
        "version": 1,
        "reviewer_id": "reviewer@example.com",
        "reviewed_at": "2026-08-02T14:00:00+09:00",
        "signature": "reviewer@example.com:approved",
        "release_candidate_hash": candidate_hash,
        "packet_hash": packet_hash,
        "checks": [],
    }


def _run_local_packet(root: Path, *, run_id: str = _RUN_ID) -> Path:
    packet = root / "runs" / run_id / "final-review-packet.json"
    packet.parent.mkdir(parents=True, exist_ok=True)
    packet.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "human_decision": None,
                "status": "READY_FOR_HUMAN_REVIEW",
            }
        ),
        encoding="utf-8",
    )
    return packet


def test_release_rejects_packet_bound_to_a_different_run(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    selected_packet = _run_local_packet(root)
    selected_packet.write_text(
        json.dumps(
            {
                "run_id": "RUN-ABCDEF0123456789ABCD",
                "human_decision": None,
                "status": "READY_FOR_HUMAN_REVIEW",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="run_id"):
        build_evidence_release(root, tmp_path / "release", run_id=_RUN_ID)


def test_release_requires_explicit_run_local_packet_selection(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    packet = _run_local_packet(root)
    output = tmp_path / "release"

    with pytest.raises(ValueError, match="run_id"):
        build_evidence_release(root, output)

    manifest = build_evidence_release(root, output, run_id=_RUN_ID)

    assert manifest["run_id"] == _RUN_ID
    assert manifest["packet_hash"] == hashlib.sha256(packet.read_bytes()).hexdigest()
    assert (output / "final-review-packet.json").read_bytes() == packet.read_bytes()
    assert not output.joinpath("runs", "final-review-packet.json").exists()


def test_release_builder_script_requires_run_id_option() -> None:
    repository_root = Path(__file__).parents[3]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository_root / "src")

    completed = subprocess.run(
        [sys.executable, str(repository_root / "scripts" / "build_release.py"), "--help"],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--run-id" in completed.stdout


def test_release_blocks_until_exact_process_attestation_is_present(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    blocked_output = tmp_path / "blocked"
    blocked = build_ansim_release(root, blocked_output, run_id=_RUN_ID)
    assert blocked["format"] == "evidence-review/release"
    assert blocked["release"] == "evidence-review-v1.0"
    assert blocked["status"] == "BLOCKED"
    assert blocked["reason_codes"] == ["PROCESS_ATTESTATION_MISSING"]
    assert blocked["attestation_assurance"] == "PROCESS_ATTESTATION"
    assert blocked["cryptographic_identity_verified"] is False
    assert blocked["expected_reviewer_id"] is None
    assert blocked["attestation"] is None
    assert blocked["tag_allowed"] is False

    validation = json.loads(
        (blocked_output / "release-validation.json").read_text(encoding="utf-8")
    )
    assert validation["format"] == "evidence-review/release-validation"
    assert validation["status"] == "PASS"
    output_validation = validation["release_output"]
    assert output_validation["format"] == "evidence-review/release-output-validation"
    assert output_validation["status"] == "PASS"
    assert {item["archive"] for item in output_validation["archives"]} == {
        "codex-workspace.zip",
        "chatgpt-web-runtime.zip",
    }

    candidate_hash = blocked["candidate_hash"]
    packet_hash = blocked["packet_hash"]
    assert isinstance(candidate_hash, str)
    assert isinstance(packet_hash, str)

    legacy_dir = root / "releases/ansim-v1.0"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "acceptance-record.json").write_text(
        json.dumps(_legacy_acceptance(candidate_hash, packet_hash)),
        encoding="utf-8",
    )
    legacy_blocked = build_ansim_release(
        root,
        tmp_path / "legacy-blocked",
        run_id=_RUN_ID,
    )
    assert legacy_blocked["status"] == "BLOCKED"
    assert legacy_blocked["reason_codes"] == ["PROCESS_ATTESTATION_MISSING"]

    attestation_dir = root / "releases/evidence-review-v1.0"
    attestation_dir.mkdir(parents=True)
    (attestation_dir / "human-attestation.json").write_text(
        json.dumps(
            _attestation(
                str(legacy_blocked["candidate_hash"]),
                str(legacy_blocked["packet_hash"]),
            )
        ),
        encoding="utf-8",
    )
    ready = build_ansim_release(root, tmp_path / "ready", run_id=_RUN_ID)
    assert ready["status"] == "RELEASE_READY"
    assert ready["reason_codes"] == []
    assert ready["tag_allowed"] is True
    assert ready["attestation_assurance"] == "PROCESS_ATTESTATION"
    assert ready["cryptographic_identity_verified"] is False
    assert isinstance(ready["attestation"], dict)
    assert (tmp_path / "ready/human-attestation.json").is_file()
    assert not (tmp_path / "ready/acceptance-record.json").exists()


def test_release_rejects_stale_attestation_hashes(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    first = build_ansim_release(root, tmp_path / "first", run_id=_RUN_ID)
    attestation_dir = root / "releases/evidence-review-v1.0"
    attestation_dir.mkdir(parents=True)
    (attestation_dir / "human-attestation.json").write_text(
        json.dumps(_attestation("0" * 64, str(first["packet_hash"]))),
        encoding="utf-8",
    )

    blocked = build_ansim_release(root, tmp_path / "stale", run_id=_RUN_ID)

    assert blocked["status"] == "BLOCKED"
    assert blocked["reason_codes"] == ["PROCESS_ATTESTATION_INVALID"]
    assert blocked["tag_allowed"] is False


def test_release_rejects_configured_reviewer_identity_mismatch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    config = ReleaseConfig(expected_reviewer_id="reviewer-b@example.com")
    first = build_evidence_release(
        root,
        tmp_path / "first",
        run_id=_RUN_ID,
        config=config,
    )
    attestation_dir = root / "releases/evidence-review-v1.0"
    attestation_dir.mkdir(parents=True)
    (attestation_dir / "human-attestation.json").write_text(
        json.dumps(
            _attestation(
                str(first["candidate_hash"]),
                str(first["packet_hash"]),
                reviewer_id="reviewer-a@example.com",
            )
        ),
        encoding="utf-8",
    )

    blocked = build_evidence_release(
        root,
        tmp_path / "mismatch",
        run_id=_RUN_ID,
        config=config,
    )

    assert blocked["status"] == "BLOCKED"
    assert blocked["reason_codes"] == ["PROCESS_ATTESTATION_INVALID"]
    assert blocked["expected_reviewer_id"] == "reviewer-b@example.com"


def test_release_candidate_ignores_generated_python_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    _workspace(root)

    generated = (
        root
        / "src"
        / "evidence_review"
        / "packaging"
        / "__pycache__"
        / "generated.cpython-313.pyc"
    )
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_bytes(b"first-generated-bytecode")

    first = build_ansim_release(root, tmp_path / "first", run_id=_RUN_ID)

    generated.write_bytes(b"second-different-bytecode")

    egg_info = root / "src" / "evidence_review" / "noise.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text(
        "generated metadata",
        encoding="utf-8",
    )

    second = build_ansim_release(root, tmp_path / "second", run_id=_RUN_ID)

    assert first["candidate_hash"] == second["candidate_hash"]

def test_release_preflight_failure_leaves_no_final_output(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    (root / "evidence" / "evidence.sqlite").unlink()
    output = tmp_path / "release"

    with pytest.raises(FileNotFoundError):
        build_evidence_release(root, output, run_id=_RUN_ID)

    assert not output.exists()


def test_release_stage_failure_leaves_no_final_output_or_stage(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    output = tmp_path / "release"

    def fail_zip(source: Path, target: Path) -> None:
        raise OSError("injected build failure")

    import evidence_review.release.builder as builder

    monkeypatch.setattr(builder, "_zip_directory", fail_zip)
    with pytest.raises(OSError, match="injected build failure"):
        build_evidence_release(root, output, run_id=_RUN_ID)

    assert not output.exists()
    assert not list(tmp_path.glob(".release.stage-*"))
