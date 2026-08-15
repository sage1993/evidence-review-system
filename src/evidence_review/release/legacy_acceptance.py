"""Inspection-only support for legacy human acceptance records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Literal

from evidence_review.contracts.legacy_formats import LEGACY_HUMAN_ACCEPTANCE_FORMAT
from evidence_review.contracts.validation import (
    expect_int,
    expect_literal,
    expect_mapping,
    expect_sha256,
    expect_string,
)

LEGACY_UNVERIFIED_ACCEPTANCE: Final[
    Literal["LEGACY_UNVERIFIED_ACCEPTANCE"]
] = "LEGACY_UNVERIFIED_ACCEPTANCE"


@dataclass(frozen=True, slots=True)
class LegacyAcceptanceSummary:
    """Non-authorizing metadata extracted from one legacy record."""

    format: Literal["ansim/human-acceptance"]
    reviewer_id: str
    reviewed_at: datetime
    release_candidate_hash: str
    packet_hash: str
    warning: Literal["LEGACY_UNVERIFIED_ACCEPTANCE"]
    can_authorize_release: Literal[False]


def inspect_legacy_acceptance(path: Path) -> LegacyAcceptanceSummary:
    """Read legacy metadata without granting release authority."""
    payload = expect_mapping(
        json.loads(path.read_text(encoding="utf-8")),
        "legacy_acceptance",
    )
    expect_literal(
        payload.get("format"),
        "format",
        (LEGACY_HUMAN_ACCEPTANCE_FORMAT,),
    )
    version = expect_int(payload.get("version"), "version")
    if version != 1:
        raise ValueError(f"unsupported legacy acceptance version: {version}")
    reviewer_id = expect_string(payload.get("reviewer_id"), "reviewer_id")
    reviewed_at_text = expect_string(payload.get("reviewed_at"), "reviewed_at")
    try:
        reviewed_at = datetime.fromisoformat(reviewed_at_text)
    except ValueError as error:
        raise ValueError("reviewed_at must be ISO-8601") from error
    if reviewed_at.utcoffset() is None:
        raise ValueError("reviewed_at must include timezone")
    return LegacyAcceptanceSummary(
        format="ansim/human-acceptance",
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        release_candidate_hash=expect_sha256(
            payload.get("release_candidate_hash"),
            "release_candidate_hash",
        ),
        packet_hash=expect_sha256(payload.get("packet_hash"), "packet_hash"),
        warning=LEGACY_UNVERIFIED_ACCEPTANCE,
        can_authorize_release=False,
    )
