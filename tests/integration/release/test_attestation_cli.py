from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from evidence_review.release.attestation import REQUIRED_CHECK_IDS


def _document(candidate_hash: str, packet_hash: str) -> dict[str, object]:
    return {
        "format": "evidence-review/human-attestation",
        "version": 1,
        "assurance_level": "PROCESS_ATTESTATION",
        "reviewer_id": "reviewer@example.com",
        "reviewed_at": "2026-08-02T14:00:00+09:00",
        "attestation": "REVIEWED_AND_ACCEPTED_FOR_RELEASE",
        "release_candidate_hash": candidate_hash,
        "packet_hash": packet_hash,
        "checks": [
            {
                "check_id": check_id,
                "status": "PASS",
                "evidence": f"evidence/{check_id}",
            }
            for check_id in REQUIRED_CHECK_IDS
        ],
    }


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "evidence_review", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_validate_attestation_cli_outputs_explicit_assurance(
    tmp_path: Path,
) -> None:
    candidate_hash = "a" * 64
    packet_hash = "b" * 64
    path = tmp_path / "human-attestation.json"
    path.write_text(
        json.dumps(_document(candidate_hash, packet_hash)),
        encoding="utf-8",
    )

    result = _run(
        "release",
        "validate-attestation",
        "--attestation",
        str(path),
        "--candidate-hash",
        candidate_hash,
        "--packet-hash",
        packet_hash,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["format"] == "evidence-review/human-attestation-status"
    assert payload["status"] == "VALID"
    assert payload["assurance_level"] == "PROCESS_ATTESTATION"
    assert payload["cryptographic_identity_verified"] is False
    assert payload["reviewer_id"] == "reviewer@example.com"


def test_release_validate_attestation_cli_rejects_hash_mismatch(
    tmp_path: Path,
) -> None:
    path = tmp_path / "human-attestation.json"
    path.write_text(
        json.dumps(_document("a" * 64, "b" * 64)),
        encoding="utf-8",
    )

    result = _run(
        "release",
        "validate-attestation",
        "--attestation",
        str(path),
        "--candidate-hash",
        "c" * 64,
        "--packet-hash",
        "b" * 64,
    )

    assert result.returncode == 2
    assert "RELEASE_CANDIDATE_HASH_MISMATCH" in result.stderr


def test_release_validate_attestation_help_is_available() -> None:
    result = _run("release", "validate-attestation", "--help")

    assert result.returncode == 0
    assert "--attestation" in result.stdout
    assert "--candidate-hash" in result.stdout
    assert "--packet-hash" in result.stdout
