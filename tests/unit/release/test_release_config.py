from __future__ import annotations

from pathlib import Path

import pytest

from ansim_review.release.config import (
    DEFAULT_RELEASE_CONFIG,
    ReleaseConfig,
    resolve_attestation_record,
    resolve_evidence_database,
)


def test_default_release_configuration_is_generic() -> None:
    assert DEFAULT_RELEASE_CONFIG.release_id == "evidence-review-v1.0"
    assert DEFAULT_RELEASE_CONFIG.evidence_db_name == "evidence.sqlite"
    assert DEFAULT_RELEASE_CONFIG.attestation_record_name == "human-attestation.json"


def test_custom_release_id_controls_attestation_path(tmp_path: Path) -> None:
    config = ReleaseConfig(release_id="project-alpha-v2")

    assert config.attestation_path(tmp_path) == (
        tmp_path / "releases/project-alpha-v2/human-attestation.json"
    )
    assert resolve_attestation_record(tmp_path, config) == config.attestation_path(tmp_path)


@pytest.mark.parametrize(
    "field",
    ["../evidence.sqlite", "nested/evidence.sqlite", "C:\\evidence.sqlite"],
)
def test_release_file_names_are_one_safe_component(field: str) -> None:
    with pytest.raises(ValueError, match="file name"):
        ReleaseConfig(evidence_db_name=field)
    with pytest.raises(ValueError, match="file name"):
        ReleaseConfig(attestation_record_name=field)


def test_generic_database_is_preferred_over_legacy_fallback(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    generic = evidence / "evidence.sqlite"
    legacy = evidence / "ansim-evidence.sqlite"
    legacy.write_bytes(b"legacy")

    assert resolve_evidence_database(tmp_path, DEFAULT_RELEASE_CONFIG) == legacy

    generic.write_bytes(b"generic")
    assert resolve_evidence_database(tmp_path, DEFAULT_RELEASE_CONFIG) == generic


def test_legacy_release_folder_never_supplies_attestation_authority(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "releases/ansim-v1.0/acceptance-record.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("{}", encoding="utf-8")

    resolved = resolve_attestation_record(tmp_path, DEFAULT_RELEASE_CONFIG)

    assert resolved == (
        tmp_path / "releases/evidence-review-v1.0/human-attestation.json"
    )
    assert not resolved.exists()
