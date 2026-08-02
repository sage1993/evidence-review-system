from __future__ import annotations

import json
from pathlib import Path

import pytest

from ansim_review.release.acceptance import validate_acceptance_record
from ansim_review.release.attestation import validate_attestation
from ansim_review.release.legacy_acceptance import inspect_legacy_acceptance


def _legacy(candidate_hash: str = "a" * 64, packet_hash: str = "b" * 64) -> dict[str, object]:
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


def test_legacy_acceptance_is_inspection_only(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(_legacy()), encoding="utf-8")

    summary = inspect_legacy_acceptance(path)

    assert summary.format == "ansim/human-acceptance"
    assert summary.reviewer_id == "reviewer@example.com"
    assert summary.warning == "LEGACY_UNVERIFIED_ACCEPTANCE"
    assert summary.can_authorize_release is False


def test_legacy_acceptance_cannot_pass_new_or_old_authorization_entrypoints(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(_legacy()), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported format"):
        validate_attestation(
            path,
            expected_candidate_hash="a" * 64,
            expected_packet_hash="b" * 64,
        )
    with pytest.raises(ValueError, match="LEGACY_ACCEPTANCE_CANNOT_AUTHORIZE_RELEASE"):
        validate_acceptance_record(
            path,
            expected_candidate_hash="a" * 64,
            expected_packet_hash="b" * 64,
        )
