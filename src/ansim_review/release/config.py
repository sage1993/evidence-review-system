"""Product configuration for generic release artifact generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ansim_review.contracts.identifiers import validate_identifier
from ansim_review.contracts.legacy_formats import (
    LEGACY_EVIDENCE_DB_NAME,
    LEGACY_RELEASE_ID,
)


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


@dataclass(frozen=True, slots=True)
class ReleaseConfig:
    """Names and paths that identify one release product."""

    release_id: str = "evidence-review-v1.0"
    evidence_db_name: str = "evidence.sqlite"
    acceptance_record_name: str = "acceptance-record.json"

    def __post_init__(self) -> None:
        validate_identifier(self.release_id, "release_id")
        _validate_file_name(self.evidence_db_name, "evidence_db_name")
        _validate_file_name(
            self.acceptance_record_name,
            "acceptance_record_name",
        )

    def acceptance_path(self, workspace_root: Path) -> Path:
        return (
            workspace_root
            / "releases"
            / self.release_id
            / self.acceptance_record_name
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


def resolve_acceptance_record(workspace_root: Path, config: ReleaseConfig) -> Path:
    """Prefer the configured record and read the old release folder as fallback."""
    generic = config.acceptance_path(workspace_root)
    if generic.is_file():
        return generic
    legacy = (
        workspace_root
        / "releases"
        / LEGACY_RELEASE_ID
        / config.acceptance_record_name
    )
    if legacy.is_file():
        return legacy
    return generic


DEFAULT_RELEASE_CONFIG = ReleaseConfig()
