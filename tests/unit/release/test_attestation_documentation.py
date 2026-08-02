from pathlib import Path

README = Path("README.md")
REVIEWER = Path("docs/REVIEWER_WORKFLOW.md")
OFFLINE = Path("docs/OFFLINE_EXECUTION.md")


def test_process_attestation_guarantees_are_explicit_in_user_docs() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in (README, REVIEWER, OFFLINE)
    )

    for required in (
        "evidence-review/human-attestation",
        "PROCESS_ATTESTATION",
        "REVIEWED_AND_ACCEPTED_FOR_RELEASE",
        "human-attestation.json",
        "release candidate hash",
        "packet hash",
        "append-only",
        "cryptographic_identity_verified",
        "false",
    ):
        assert required in combined


def test_reviewer_docs_deny_cryptographic_identity_claims() -> None:
    reviewer = REVIEWER.read_text(encoding="utf-8")

    assert "not cryptographic proof of reviewer identity" in reviewer
    assert "legacy `ansim/human-acceptance`" in reviewer
    assert "cannot authorize a new release" in reviewer


def test_process_attestation_threat_model_is_explicit() -> None:
    reviewer = REVIEWER.read_text(encoding="utf-8")

    for required in (
        "Threat model and operational assumptions",
        "stale or mismatched release artifacts",
        "malicious reviewer",
        "stolen or copied JSON file",
        "external access control",
    ):
        assert required in reviewer


def test_offline_and_human_assurance_are_separate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")

    assert "APPLICATION_OFFLINE_GUARD" in offline
    assert "PROCESS_ATTESTATION" in offline
    assert "cryptographic_network_isolation_verified" in offline
    assert "cryptographic_identity_verified" in offline
    assert "independent assurance dimensions" in offline
