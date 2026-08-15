"""Product configuration for generic release artifact generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.legacy_formats import LEGACY_EVIDENCE_DB_NAME


def _validate_file_name(value: str, field: str) -> None:
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or ":" in value
        or Path(value).name != value
    ):
        raise ValueError(f"{field} must be one file name")


def _validate_optional_reviewer_id(value: str | None) -> None:
    if value is not None and (not value or value != value.strip()):
        raise ValueError("expected_reviewer_id must be a non-blank exact identifier")


@dataclass(frozen=True, slots=True)
class ReleaseConfig:
    """Names, paths, and reviewer policy for one release product."""

    release_id: str = "evidence-review-v1.0"
    evidence_db_name: str = "evidence.sqlite"
    attestation_record_name: str = "human-attestation.json"
    expected_reviewer_id: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.release_id, "release_id")
        _validate_file_name(self.evidence_db_name, "evidence_db_name")
        _validate_file_name(
            self.attestation_record_name,
            "attestation_record_name",
        )
        _validate_optional_reviewer_id(self.expected_reviewer_id)

    def attestation_path(self, workspace_root: Path) -> Path:
        return (
            workspace_root
            / "releases"
            / self.release_id
            / self.attestation_record_name
        )


def resolve_evidence_database(workspace_root: Path, config: ReleaseConfig) -> Path:
    """Prefer the generic database name and read the old name only as fallback."""
    generic = workspace_root / "evidence" / config.evidence_db_name
    if generic.is_file():
        return generic
    legacy = workspace_root / "evidence" / LEGACY_EVIDENCE_DB_NAME
    if legacy.is_file():
        return legacy
    return generic


def resolve_attestation_record(workspace_root: Path, config: ReleaseConfig) -> Path:
    """Return only the canonical attestation path; legacy folders never authorize."""
    return config.attestation_path(workspace_root)


DEFAULT_RELEASE_CONFIG = ReleaseConfig()
