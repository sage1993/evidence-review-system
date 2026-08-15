from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.canonical_json import dump_bytes
from evidence_review.release.attestation import (
    PROCESS_ATTESTATION,
    REQUIRED_CHECK_IDS,
    REVIEWED_AND_ACCEPTED_FOR_RELEASE,
    attestation_document,
    decode_attestation,
    validate_attestation,
    write_attestation,
)


def _document(
    candidate_hash: str = "a" * 64,
    packet_hash: str = "b" * 64,
) -> dict[str, object]:
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


def test_attestation_decodes_strict_process_contract() -> None:
    decoded = decode_attestation(_document())

    assert decoded.assurance_level == PROCESS_ATTESTATION
    assert decoded.attestation == REVIEWED_AND_ACCEPTED_FOR_RELEASE
    assert decoded.reviewer_id == "reviewer@example.com"
    assert decoded.reviewed_at.utcoffset() is not None
    assert tuple(check.check_id for check in decoded.checks) == REQUIRED_CHECK_IDS


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("format", "ansim/human-acceptance", "unsupported format"),
        ("assurance_level", "CRYPTOGRAPHIC_SIGNATURE", "unsupported assurance_level"),
        ("attestation", "approved", "unsupported attestation"),
        ("reviewer_id", "", "reviewer_id"),
        ("reviewed_at", "2026-08-02T14:00:00", "timezone"),
        ("release_candidate_hash", "A" * 64, "lowercase SHA-256"),
        ("packet_hash", "not-a-hash", "lowercase SHA-256"),
    ],
)
def test_attestation_rejects_invalid_contract_fields(
    field: str,
    value: object,
    message: str,
) -> None:
    document = _document()
    document[field] = value

    with pytest.raises(ValueError, match=message):
        decode_attestation(document)


def test_attestation_rejects_signature_and_unknown_fields() -> None:
    document = _document()
    document["signature"] = "misleading"

    with pytest.raises(ValueError, match="unknown fields: signature"):
        decode_attestation(document)


def test_attestation_rejects_missing_and_duplicate_checks() -> None:
    missing = _document()
    checks = missing["checks"]
    assert isinstance(checks, list)
    checks.pop()
    with pytest.raises(ValueError, match="MISSING_ATTESTATION_CHECK"):
        decode_attestation(missing)

    duplicate = _document()
    duplicate_checks = duplicate["checks"]
    assert isinstance(duplicate_checks, list)
    duplicate_checks.append(dict(duplicate_checks[0]))
    with pytest.raises(ValueError, match="DUPLICATE_ATTESTATION_CHECK"):
        decode_attestation(duplicate)


def test_attestation_requires_every_check_to_pass_with_evidence() -> None:
    document = _document()
    checks = document["checks"]
    assert isinstance(checks, list)
    first = checks[0]
    assert isinstance(first, dict)
    first["status"] = "FAIL"
    with pytest.raises(ValueError, match="ATTESTATION_CHECK_NOT_PASSED"):
        decode_attestation(document)

    first["status"] = "PASS"
    first["evidence"] = ""
    with pytest.raises(ValueError, match="evidence"):
        decode_attestation(document)


def test_validate_attestation_binds_exact_candidate_and_packet_hashes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attestation.json"
    path.write_text(json.dumps(_document()), encoding="utf-8")

    validated = validate_attestation(
        path,
        expected_candidate_hash="a" * 64,
        expected_packet_hash="b" * 64,
    )
    assert validated.reviewer_id == "reviewer@example.com"

    with pytest.raises(ValueError, match="RELEASE_CANDIDATE_HASH_MISMATCH"):
        validate_attestation(
            path,
            expected_candidate_hash="c" * 64,
            expected_packet_hash="b" * 64,
        )
    with pytest.raises(ValueError, match="PACKET_HASH_MISMATCH"):
        validate_attestation(
            path,
            expected_candidate_hash="a" * 64,
            expected_packet_hash="c" * 64,
        )


def test_attestation_writer_is_canonical_and_append_only(tmp_path: Path) -> None:
    decoded = decode_attestation(_document())
    path = tmp_path / "attestations" / "reviewer.json"

    digest = write_attestation(path, decoded)

    expected = dump_bytes(attestation_document(decoded))
    assert path.read_bytes() == expected
    assert len(digest) == 64
    with pytest.raises(FileExistsError):
        write_attestation(path, decoded)
