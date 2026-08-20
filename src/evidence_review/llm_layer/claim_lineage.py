"""Deterministic claim-to-issue lineage helpers."""

from __future__ import annotations

import re
from collections.abc import Sequence

_CLAIM_ISSUE_PATTERN = re.compile(r"^CL-(I\d+)(?:-|$)")


def claim_id_issue_id(claim_id: str) -> str | None:
    """Return the issue identifier encoded by a conventional claim id, if present."""
    match = _CLAIM_ISSUE_PATTERN.match(claim_id)
    return None if match is None else match.group(1)


def validate_claim_id_issue_binding(
    claim_id: str,
    issue_ids: Sequence[str],
    *,
    planned_issue_ids: Sequence[str] = (),
) -> None:
    """Reject claim ids whose encoded issue conflicts with declared lineage."""
    encoded_issue_id = claim_id_issue_id(claim_id)
    if encoded_issue_id is None:
        return
    planned = set(planned_issue_ids)
    if planned and encoded_issue_id not in planned:
        raise ValueError(
            f"UNKNOWN_CLAIM_ISSUE: claim {claim_id}: {encoded_issue_id}"
        )
    if encoded_issue_id not in set(issue_ids):
        declared = ", ".join(issue_ids) if issue_ids else "<none>"
        raise ValueError(
            "CLAIM_ISSUE_ID_MISMATCH: "
            f"claim {claim_id} encodes {encoded_issue_id} but declares {declared}"
        )
