"""Deprecated compatibility boundary for legacy acceptance records.

Legacy `ansim/human-acceptance` files may be inspected, but they cannot
authorize a new release. Canonical release authorization uses
`evidence-review/human-attestation` through :mod:`evidence_review.release.attestation`.
"""

from __future__ import annotations

from pathlib import Path

from evidence_review.release.legacy_acceptance import (
    LEGACY_UNVERIFIED_ACCEPTANCE,
    LegacyAcceptanceSummary,
    inspect_legacy_acceptance,
)

__all__ = [
    "LEGACY_UNVERIFIED_ACCEPTANCE",
    "LegacyAcceptanceSummary",
    "inspect_legacy_acceptance",
    "validate_acceptance_record",
]


def validate_acceptance_record(
    path: Path,
    *,
    expected_candidate_hash: str,
    expected_packet_hash: str,
) -> dict[str, object]:
    """Fail closed: legacy records never authorize a canonical release."""
    del path, expected_candidate_hash, expected_packet_hash
    raise ValueError(
        "LEGACY_ACCEPTANCE_CANNOT_AUTHORIZE_RELEASE: "
        "use evidence-review/human-attestation"
    )
